"""HTTP Range streaming of a file inside a torrent while it is still downloading.

For each read we put rising piece deadlines on the pieces just ahead of the read
position, so libtorrent fetches them in playback order without forcing the whole
torrent into sequential mode (which would hurt swarm health).
"""
from __future__ import annotations

import asyncio
import mimetypes
import time
from pathlib import Path

import libtorrent as lt
from aiohttp import web

from .engine import Engine

CHUNK = 256 * 1024
WINDOW_BYTES = 24 * 1024 * 1024
MAX_WINDOW_PIECES = 256
METADATA_TIMEOUT = 45
STALL_TIMEOUT = 90

# Only these are served with their real type. A torrent can contain anything, and this origin
# also serves the UI, so e.g. an .html or .svg must never be rendered inline here.
_SAFE_TYPES = ("video/", "audio/")
_SAFE_IMAGE = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/avif"}


def content_type(path: str) -> str:
    guess = mimetypes.guess_type(path)[0] or ""
    if guess.startswith(_SAFE_TYPES) or guess in _SAFE_IMAGE:
        return guess
    return "application/octet-stream"


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """Return (start, end) inclusive, or None to serve the whole file. Raises ValueError if unsatisfiable."""
    if not header or not header.startswith("bytes=") or "," in header:
        return None
    spec = header[6:].strip()
    a, _, b = spec.partition("-")
    if not (a.isdigit() or a == "") or not (b.isdigit() or b == "") or (a == "" and b == ""):
        return None                              # malformed: ignore the header, serve everything
    if a == "":
        n = int(b)
        if n <= 0:
            raise ValueError("unsatisfiable")
        return max(0, size - n), size - 1
    start = int(a)
    end = int(b) if b else size - 1
    if start >= size or start < 0 or end < start:
        raise ValueError("unsatisfiable")
    return start, min(end, size - 1)


def _read_at(path: Path, pos: int, n: int) -> bytes:
    with open(path, "rb") as fh:
        fh.seek(pos)
        return fh.read(n)


class Streamer:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.active: dict[str, int] = {}

    async def handle(self, request: web.Request, key: str, index: int) -> web.StreamResponse:
        try:
            h = self.engine.handle(key)
        except KeyError:
            raise web.HTTPNotFound(text="no such torrent")
        deadline = time.monotonic() + METADATA_TIMEOUT
        while not h.status().has_metadata:
            if time.monotonic() > deadline:
                raise web.HTTPGatewayTimeout(text="metadata not available yet")
            await asyncio.sleep(0.25)
        ti = h.torrent_file()
        fs = ti.layout()
        if not 0 <= index < fs.num_files() or fs.file_flags(index) & lt.file_storage.flag_pad_file:
            raise web.HTTPNotFound(text="no such file")
        size, rel = fs.file_size(index), fs.file_path(index)
        path = Path(h.status().save_path) / rel
        try:
            rng = parse_range(request.headers.get("Range"), size)
        except ValueError:
            raise web.HTTPRequestRangeNotSatisfiable(headers={"Content-Range": f"bytes */{size}"})
        start, end = rng if rng else (0, size - 1)
        ctype = content_type(rel)
        headers = {
            "Content-Type": ctype, "Accept-Ranges": "bytes", "Content-Length": str(end - start + 1 if size else 0),
            "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store",
            "Content-Security-Policy": "sandbox; default-src 'none'",
            "Content-Disposition": "inline" if ctype != "application/octet-stream" else "attachment",
        }
        if rng:
            headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        resp = web.StreamResponse(status=206 if rng else 200, headers=headers)
        if request.method == "HEAD" or size == 0:
            return resp
        if h.get_file_priorities()[index] == 0:
            h.file_priority(index, 4)
        if h.status().flags & lt.torrent_flags.paused:
            self.engine.resume(key)
        await resp.prepare(request)
        self.active[key] = self.active.get(key, 0) + 1
        loop = asyncio.get_running_loop()
        try:
            pos = start
            while pos <= end:
                n = min(CHUNK, end - pos + 1)
                await self._ready(h, ti, fs, index, pos, end, n)
                data = await loop.run_in_executor(None, self._read_complete, path, pos, n)
                await resp.write(data)
                pos += n
            await resp.write_eof()
        finally:
            self.active[key] -= 1
            if self.active[key] <= 0 and h.is_valid():
                h.clear_piece_deadlines()
        return resp

    @staticmethod
    def _read_complete(path: Path, pos: int, n: int) -> bytes:
        for _ in range(40):          # the OS may not show the freshly written bytes immediately
            data = _read_at(path, pos, n)
            if len(data) == n:
                return data
            time.sleep(0.05)
        raise ConnectionError("file shorter than expected")

    async def _ready(self, h, ti, fs, index: int, pos: int, end: int, n: int) -> None:
        pl, base = ti.piece_length(), fs.file_offset(index)
        first, need_last = (base + pos) // pl, (base + pos + n - 1) // pl
        window = min((base + end) // pl, first + min(MAX_WINDOW_PIECES, max(4, WINDOW_BYTES // pl)))
        missing_before, last_progress = None, time.monotonic()
        while True:
            missing = [p for p in range(first, need_last + 1) if not h.have_piece(p)]
            if not missing:
                return
            if missing_before is None or len(missing) < missing_before:
                missing_before, last_progress = len(missing), time.monotonic()
            elif time.monotonic() - last_progress > STALL_TIMEOUT:
                raise ConnectionError("stalled: no peers are providing the next pieces")
            for i, p in enumerate(range(first, window + 1)):
                if not h.have_piece(p):
                    h.set_piece_deadline(p, 100 + i * 150)
            await asyncio.sleep(0.1)
