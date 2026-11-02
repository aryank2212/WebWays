"""Seed a browser-made torrent from files the user dropped into the UI.

The browser hashes the files and builds the .torrent itself (nothing leaves the machine for that).
To seed it, the files are then streamed to the daemon, which verifies them against the torrent:

    prepare (torrent bytes)  ->  PUT each file  ->  finish (adds the torrent; libtorrent re-hashes)

Everything is written under the download directory only, never over an existing file.
"""
from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePath

import libtorrent as lt
from aiohttp import web

from .engine import Engine, EngineError, key_of

MAX_PENDING = 4
PENDING_TTL = 3600
DISK_MARGIN = 256 * 1024 * 1024
CHUNK = 1024 * 1024


def _replace(src: Path, dst: Path) -> None:
    """os.replace, retried briefly: on Windows an antivirus scan or indexer can hold a just-written file."""
    for attempt in range(10):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.1 * (attempt + 1))


class SeedError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


@dataclass
class Pending:
    data: bytes
    files: dict[int, tuple[Path, int]]          # index -> (absolute target, size)
    created: float = field(default_factory=time.monotonic)
    uploaded: set[int] = field(default_factory=set)


class SeedStaging:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.pending: dict[str, Pending] = {}

    def _expire(self) -> None:
        for key in [k for k, p in self.pending.items() if time.monotonic() - p.created > PENDING_TTL]:
            self.cancel(key)

    def prepare(self, data: bytes) -> dict:
        try:
            ti = lt.torrent_info(lt.bdecode(data))
        except Exception as exc:
            raise SeedError(422, f"not a valid .torrent file: {exc}")
        key = key_of(ti.info_hashes())
        if key in self.engine.handles:
            raise SeedError(409, "this torrent is already in your client")
        self._expire()
        if key not in self.pending and len(self.pending) >= MAX_PENDING:
            raise SeedError(429, "too many uploads in progress")
        root = Path(self.engine.settings.download_dir).resolve()
        root.mkdir(parents=True, exist_ok=True)
        fs = ti.layout()
        files: dict[int, tuple[Path, int]] = {}
        for i in range(fs.num_files()):
            if fs.file_flags(i) & lt.file_storage.flag_pad_file:
                continue
            target = (root / fs.file_path(i)).resolve()
            if not target.is_relative_to(root) or target == root:
                raise SeedError(422, "torrent contains a path outside the download directory")
            files[i] = (target, fs.file_size(i))
        total = sum(size for _, size in files.values())
        if total + DISK_MARGIN > shutil.disk_usage(root).free:
            raise SeedError(507, "not enough free disk space for these files")
        if key in self.pending:
            self.cancel(key)
        self.pending[key] = Pending(data, files)
        return {"infohash": key, "name": ti.name(),
                "files": [{"index": i, "path": PurePath(fs.file_path(i)).as_posix(), "size": size} for i, (_, size) in files.items()]}

    async def put(self, request: web.Request, key: str, index: int) -> None:
        p = self.pending.get(key)
        if p is None or index not in p.files:
            raise SeedError(404, "no such pending file")
        target, size = p.files[index]
        if request.content_length is not None and request.content_length != size:
            raise SeedError(422, f"expected exactly {size} bytes")
        if target.exists() and index not in p.uploaded:
            raise SeedError(409, f"{target.name} already exists in the download directory; refusing to overwrite it")
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_name(target.name + ".part")
        received = 0
        try:
            with open(part, "wb") as fh:
                async for chunk in request.content.iter_chunked(CHUNK):
                    received += len(chunk)
                    if received > size:
                        raise SeedError(422, f"expected exactly {size} bytes")
                    fh.write(chunk)
            if received != size:
                raise SeedError(422, f"expected exactly {size} bytes, got {received}")
            _replace(part, target)
        except BaseException:
            part.unlink(missing_ok=True)
            raise
        p.uploaded.add(index)

    def finish(self, key: str) -> str:
        p = self.pending.get(key)
        if p is None:
            raise SeedError(404, "no such pending upload")
        missing = sorted(set(p.files) - p.uploaded)
        if missing:
            raise SeedError(409, f"{len(missing)} file(s) not uploaded yet")
        try:
            added = self.engine.add_torrent_bytes(p.data)
        except EngineError as exc:
            raise SeedError(422, str(exc))
        del self.pending[key]
        return added

    def cancel(self, key: str) -> bool:
        p = self.pending.pop(key, None)
        if p is None:
            return False
        for i in p.uploaded:
            p.files[i][0].unlink(missing_ok=True)
        for target, _ in p.files.values():
            target.with_name(target.name + ".part").unlink(missing_ok=True)
            for parent in target.parents:               # remove directories we emptied, never the root
                if parent == Path(self.engine.settings.download_dir).resolve():
                    break
                try:
                    parent.rmdir()
                except OSError:
                    break
        return True
