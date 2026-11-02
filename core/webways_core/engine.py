"""Thin wrapper over libtorrent-rasterbar: one session, resume data, status snapshots."""
from __future__ import annotations

import asyncio
import logging
import re
import warnings
from pathlib import Path, PurePath
from typing import Any

import libtorrent as lt

from .config import Settings

warnings.filterwarnings("ignore", category=DeprecationWarning, module="libtorrent")
log = logging.getLogger("webways.engine")

_STATE = {
    lt.torrent_status.checking_files: "checking",
    lt.torrent_status.downloading_metadata: "metadata",
    lt.torrent_status.downloading: "downloading",
    lt.torrent_status.finished: "finished",
    lt.torrent_status.seeding: "seeding",
    lt.torrent_status.checking_resume_data: "checking",
}
_HEX = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
RESUME_INTERVAL = 60
_VERSIONS = {"v1": lt.create_torrent.v1_only, "v2": lt.create_torrent.v2_only, "hybrid": 0}
# Without save_info_dict, resume files for magnet-added torrents lack metadata and can never restart offline.
SAVE_FLAGS = lt.torrent_handle.save_info_dict


class EngineError(Exception):
    pass


def key_of(ih: "lt.info_hash_t") -> str:
    """v1 hex when there is one (what magnets and listings use), else full v2 hex."""
    return str(ih.v1) if ih.has_v1() else str(ih.v2)


class Engine:
    def __init__(self, settings: Settings, state_dir: Path, session_overrides: dict[str, Any] | None = None):
        self.settings, self.state_dir = settings, state_dir
        (state_dir / "resume").mkdir(parents=True, exist_ok=True)
        (state_dir / "created").mkdir(parents=True, exist_ok=True)
        self._overrides = session_overrides or {}
        self.session = lt.session(self._pack())
        self.handles: dict[str, lt.torrent_handle] = {}
        self._task: asyncio.Task | None = None
        # Outstanding save_resume_data requests per torrent. Alerts for one torrent arrive in request
        # order, so once this drains the last file written is the newest snapshot.
        self._outstanding: dict[str, int] = {}

    # -- lifecycle ----------------------------------------------------------
    def _pack(self) -> dict[str, Any]:
        s = self.settings
        enc = lt.enc_policy.forced if s.encryption == "forced" else lt.enc_policy.enabled
        pack: dict[str, Any] = {
            "user_agent": "webways/0.1 libtorrent/" + lt.__version__,
            "listen_interfaces": f"0.0.0.0:{s.listen_port},[::]:{s.listen_port}",
            "enable_dht": True, "enable_lsd": True, "enable_upnp": True, "enable_natpmp": True,
            "out_enc_policy": int(enc), "in_enc_policy": int(enc),
            "allowed_enc_level": int(lt.enc_level.rc4 if s.encryption == "forced" else lt.enc_level.both),
            "prefer_rc4": s.encryption == "forced",
            "download_rate_limit": s.download_limit, "upload_rate_limit": s.upload_limit,
            # A stream must never sit in the queue behind other torrents.
            "active_downloads": 1000, "active_seeds": 1000, "active_limit": 2000,
            "alert_mask": lt.alert.category_t.status_notification | lt.alert.category_t.error_notification,
        }
        pack.update(self._overrides)
        return pack

    def apply_settings(self) -> None:
        self.session.apply_settings(self._pack())

    async def start(self) -> None:
        for f in sorted((self.state_dir / "resume").glob("*.resume")):
            try:
                params = lt.read_resume_data(f.read_bytes())
                self._register(self.session.add_torrent(params))
            except Exception as exc:
                log.warning("skipping unreadable resume file %s: %s", f.name, exc)
        self._task = asyncio.create_task(self._pump())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        for h in self.handles.values():
            if h.is_valid() and h.status().has_metadata:
                self._request_save(h)
        for _ in range(100):                      # up to ~10 s for resume data to flush
            self._drain_alerts()
            if not any(self._outstanding.values()):
                break
            await asyncio.sleep(0.1)

    def _request_save(self, h: "lt.torrent_handle") -> None:
        key = key_of(h.info_hashes())
        self._outstanding[key] = self._outstanding.get(key, 0) + 1
        h.save_resume_data(SAVE_FLAGS)

    async def _pump(self) -> None:
        last_periodic = 0.0
        loop = asyncio.get_running_loop()
        while True:
            self._drain_alerts()
            if loop.time() - last_periodic > RESUME_INTERVAL:
                last_periodic = loop.time()
                for h in self.handles.values():
                    if h.is_valid() and h.need_save_resume_data():
                        self._request_save(h)
            await asyncio.sleep(0.5)

    def _drain_alerts(self) -> None:
        for a in self.session.pop_alerts():
            if isinstance(a, lt.save_resume_data_alert):
                key = key_of(a.handle.info_hashes())
                self._outstanding[key] = max(0, self._outstanding.get(key, 0) - 1)
                (self.state_dir / "resume" / f"{key}.resume").write_bytes(lt.write_resume_data_buf(a.params))
            elif isinstance(a, lt.save_resume_data_failed_alert):
                key = key_of(a.handle.info_hashes())
                self._outstanding[key] = max(0, self._outstanding.get(key, 0) - 1)
            elif isinstance(a, (lt.metadata_received_alert, lt.torrent_finished_alert)):
                self._request_save(a.handle)
            elif isinstance(a, lt.torrent_error_alert):
                log.warning("torrent error: %s", a.message())

    # -- adding / removing --------------------------------------------------
    def _register(self, h: "lt.torrent_handle") -> str:
        key = key_of(h.info_hashes())
        self.handles[key] = h
        return key

    def _params(self) -> "lt.add_torrent_params":
        p = lt.add_torrent_params()
        p.save_path = self.settings.download_dir
        Path(p.save_path).mkdir(parents=True, exist_ok=True)
        return p

    def add_infohash(self, infohash: str, name: str = "") -> str:
        if not _HEX.match(infohash):
            raise EngineError("infohash must be 40 or 64 lowercase hex characters")
        uri = f"magnet:?xt=urn:btih:{infohash}" if len(infohash) == 40 else f"magnet:?xt=urn:btmh:1220{infohash}"
        return self.add_magnet(uri, name)

    def add_magnet(self, uri: str, name: str = "") -> str:
        if not uri.startswith("magnet:?"):
            raise EngineError("not a magnet URI")
        try:
            p = lt.parse_magnet_uri(uri)
        except Exception as exc:
            raise EngineError(f"bad magnet URI: {exc}") from exc
        p.save_path = self._params().save_path
        if name and not p.name:
            p.name = name[:200]
        return self._add(p)

    def add_torrent_bytes(self, data: bytes) -> str:
        try:
            ti = lt.torrent_info(lt.bdecode(data))
        except Exception as exc:
            raise EngineError(f"not a valid .torrent file: {exc}") from exc
        p = self._params()
        p.ti = ti
        return self._add(p)

    def _add(self, p: "lt.add_torrent_params") -> str:
        key = key_of(p.info_hashes)
        if key in self.handles and self.handles[key].is_valid():
            return key
        return self._register(self.session.add_torrent(p))

    def remove(self, key: str, delete_files: bool = False) -> None:
        h = self.handle(key)
        self.session.remove_torrent(h, lt.session.delete_files if delete_files else 0)
        del self.handles[key]
        (self.state_dir / "resume" / f"{key}.resume").unlink(missing_ok=True)

    def pause(self, key: str) -> None:
        h = self.handle(key)
        h.unset_flags(lt.torrent_flags.auto_managed)
        h.pause()

    def resume(self, key: str) -> None:
        h = self.handle(key)
        h.set_flags(lt.torrent_flags.auto_managed)
        h.resume()

    def handle(self, key: str) -> "lt.torrent_handle":
        h = self.handles.get(key)
        if h is None or not h.is_valid():
            raise KeyError(key)
        return h

    def connect_peer(self, key: str, host: str, port: int) -> None:
        self.handle(key).connect_peer((host, port))

    # -- creating -----------------------------------------------------------
    def create_torrent(self, path: str, comment: str = "", *, trackers: tuple[str, ...] = (),
                       webseeds: tuple[str, ...] = (), private: bool = False, piece_size: int = 0,
                       version: str = "hybrid") -> str:
        """Hash `path` into a torrent, store it, and start seeding it. Blocking (CPU/IO).

        No trackers are added unless the caller lists them: peers are found through DHT/PEX.
        """
        src = Path(path).expanduser().resolve()
        if not src.exists():
            raise EngineError("path does not exist")
        if version not in _VERSIONS:
            raise EngineError("version must be v1, v2 or hybrid")
        if piece_size and not (piece_size & (piece_size - 1) == 0 and 16 * 1024 <= piece_size <= 64 * 1024 * 1024):
            raise EngineError("piece_size must be a power of two between 16 KiB and 64 MiB (or 0 for automatic)")
        for url in trackers:
            if not re.match(r"^(udp|http|https|wss?)://[^\s/]+", url):
                raise EngineError(f"bad tracker URL: {url[:80]}")
        for url in webseeds:
            if not re.match(r"^https?://[^\s/]+", url):
                raise EngineError(f"bad web seed URL: {url[:80]}")
        ct = lt.create_torrent(lt.list_files(str(src)), piece_size, _VERSIONS[version])
        ct.set_creator("webways")
        if comment:
            ct.set_comment(comment[:500])
        for i, url in enumerate(trackers):
            ct.add_tracker(url, i)
        for url in webseeds:
            ct.add_url_seed(url)
        if private:
            ct.set_priv(True)
        lt.set_piece_hashes(ct, str(src.parent))
        data = lt.bencode(ct.generate())
        ti = lt.torrent_info(lt.bdecode(data))
        key = key_of(ti.info_hashes())
        (self.state_dir / "created" / f"{key}.torrent").write_bytes(data)
        p = lt.add_torrent_params()
        p.ti, p.save_path = ti, str(src.parent)
        return self._add(p)

    def torrent_file(self, key: str) -> bytes:
        """The .torrent for a torrent we know the metadata of (original bytes when we made it)."""
        h = self.handle(key)
        saved = self.state_dir / "created" / f"{key}.torrent"
        if saved.exists():
            return saved.read_bytes()
        if not h.status().has_metadata:
            raise EngineError("metadata not available yet")
        return lt.bencode(lt.create_torrent(h.torrent_file()).generate())

    # -- inspection ---------------------------------------------------------
    def status(self, key: str) -> dict[str, Any]:
        h = self.handle(key)
        st = h.status()
        paused = bool(st.flags & lt.torrent_flags.paused) and not st.flags & lt.torrent_flags.auto_managed
        state = "paused" if paused else _STATE.get(st.state, "unknown")
        remaining = (st.total_wanted - st.total_wanted_done) if st.has_metadata else 0
        return {
            "infohash": key, "name": st.name or key, "state": state, "progress": round(st.progress, 4),
            "size": st.total_wanted if st.has_metadata else 0, "downloaded": st.total_wanted_done,
            "download_rate": st.download_payload_rate, "upload_rate": st.upload_payload_rate,
            "peers": st.num_peers, "seeds": st.num_seeds, "has_metadata": st.has_metadata,
            "eta": int(remaining / st.download_payload_rate) if st.download_payload_rate > 0 and remaining else None,
            "error": st.errc.message() if st.errc.value() else None, "save_path": st.save_path,
        }

    def files(self, key: str) -> list[dict[str, Any]]:
        h = self.handle(key)
        if not h.status().has_metadata:
            return []
        fs, prio, prog = h.torrent_file().layout(), h.get_file_priorities(), h.file_progress()
        out = []
        for i in range(fs.num_files()):
            if fs.file_flags(i) & lt.file_storage.flag_pad_file:
                continue
            size = fs.file_size(i)
            # always "/"-separated in the API, whatever the OS (libtorrent returns the native separator)
            out.append({"index": i, "path": PurePath(fs.file_path(i)).as_posix(), "size": size, "priority": prio[i],
                        "progress": round(prog[i] / size, 4) if size else 1.0})
        return out

    def set_file_priority(self, key: str, index: int, priority: int) -> None:
        h = self.handle(key)
        if not 0 <= priority <= 7:
            raise EngineError("priority must be 0-7")
        if not h.status().has_metadata or not 0 <= index < h.torrent_file().num_files():
            raise EngineError("no such file")
        h.file_priority(index, priority)

    def overview(self) -> dict[str, Any]:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            st = self.session.status()
        return {"download_rate": st.payload_download_rate, "upload_rate": st.payload_upload_rate,
                "dht_nodes": st.dht_nodes, "torrents": len(self.handles)}
