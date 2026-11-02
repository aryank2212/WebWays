import base64
import hashlib
import os
import shutil
from pathlib import Path

import libtorrent as lt
import pytest

from swarm_core.config import Settings
from swarm_core.engine import Engine

from .conftest import AUTH, loopback, wait_for


def make_torrent_bytes(root: Path, **kw) -> bytes:
    """Stand-in for what the browser's create-torrent produces: a plain v1 torrent."""
    ct = lt.create_torrent(lt.list_files(str(root)), 0, lt.create_torrent.v1_only)
    lt.set_piece_hashes(ct, str(root.parent))
    return lt.bencode(ct.generate())


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


@pytest.fixture
def folder(tmp_path):
    root = tmp_path / "src" / "album"
    (root / "disc1").mkdir(parents=True)
    (root / "a.bin").write_bytes(os.urandom(300_000))
    (root / "disc1" / "b.bin").write_bytes(os.urandom(120_000))
    (root / "empty.txt").write_bytes(b"")
    return root


async def test_create_has_no_trackers_unless_asked_and_options_roundtrip(daemon, make_engine, folder):
    c = await daemon(await make_engine("d"))
    r = await c.post("/api/create", json={"path": str(folder)}, headers=AUTH)
    assert r.status == 201
    key = (await r.json())["infohash"]
    raw = await (await c.get(f"/api/torrents/{key}/torrent", headers=AUTH)).read()
    ti = lt.torrent_info(lt.bdecode(raw))
    assert [t.url for t in ti.trackers()] == []                 # nothing is announced anywhere by default
    assert not ti.priv() and str(ti.info_hashes().v1) == key

    folder2 = folder.parent / "second"
    folder2.mkdir()
    (folder2 / "x.bin").write_bytes(os.urandom(50_000))
    r = await c.post("/api/create", headers=AUTH, json={
        "path": str(folder2), "trackers": ["udp://tracker.example:6969/announce"], "webseeds": ["https://cdn.example/x/"],
        "private": True, "piece_size": 32768, "version": "v1", "comment": "hello"})
    assert r.status == 201, await r.text()
    key2 = (await r.json())["infohash"]
    ti = lt.torrent_info(lt.bdecode(await (await c.get(f"/api/torrents/{key2}/torrent", headers=AUTH)).read()))
    assert [t.url for t in ti.trackers()] == ["udp://tracker.example:6969/announce"]
    assert ti.priv() and ti.piece_length() == 32768 and ti.comment() == "hello"
    assert [w["url"] for w in ti.web_seeds()] == ["https://cdn.example/x/"]
    assert not ti.info_hashes().has_v2()


@pytest.mark.parametrize("patch", [
    {"piece_size": 1000}, {"piece_size": 3 * 16384}, {"version": "v3"}, {"trackers": ["ftp://x"]},
    {"trackers": "udp://x"}, {"webseeds": ["javascript:alert(1)"]}, {"path": "/definitely/not/here"},
])
async def test_create_rejects_bad_options(daemon, make_engine, folder, patch):
    c = await daemon(await make_engine("d"))
    r = await c.post("/api/create", json={"path": str(folder), **patch}, headers=AUTH)
    assert r.status == 422


async def test_torrent_file_download_for_added_magnet(daemon, make_engine, folder):
    seeder = await make_engine("seed")
    key = seeder.create_torrent(str(folder))
    leech = await make_engine("leech")
    c = await daemon(leech)
    await c.post("/api/torrents", json={"infohash": key}, headers=AUTH)
    assert (await c.get(f"/api/torrents/{key}/torrent", headers=AUTH)).status == 409   # no metadata yet
    leech.connect_peer(key, "127.0.0.1", seeder.session.listen_port())
    assert await wait_for(lambda: leech.status(key)["has_metadata"])
    r = await c.get(f"/api/torrents/{key}/torrent", headers=AUTH)
    assert r.headers["Content-Type"] == "application/x-bittorrent"
    assert str(lt.torrent_info(lt.bdecode(await r.read())).info_hashes().v1) == key   # regenerated copy keeps the hash


async def test_seed_upload_flow(daemon, make_engine, folder, tmp_path):
    eng = await make_engine("dl")
    c = await daemon(eng)
    data = make_torrent_bytes(folder)
    prep = await c.post("/api/seed/prepare", json={"torrent_b64": b64(data)}, headers=AUTH)
    assert prep.status == 201
    info = await prep.json()
    assert {f["path"] for f in info["files"]} == {"album/a.bin", "album/disc1/b.bin", "album/empty.txt"}

    # finishing early is refused; wrong sizes are refused and leave nothing behind
    assert (await c.post(f"/api/seed/{info['infohash']}/finish", headers=AUTH)).status == 409
    first = info["files"][0]
    bad = await c.put(f"/api/seed/{info['infohash']}/files/{first['index']}", data=b"short", headers=AUTH)
    assert bad.status == 422
    dl = Path(eng.settings.download_dir)
    assert not list(dl.rglob("*.part")) and not (dl / first["path"]).exists()

    for f in info["files"]:
        content = (folder.parent / f["path"]).read_bytes()
        r = await c.put(f"/api/seed/{info['infohash']}/files/{f['index']}", data=content, headers=AUTH)
        assert r.status == 200, await r.text()
    done = await c.post(f"/api/seed/{info['infohash']}/finish", headers=AUTH)
    assert done.status == 201
    key = (await done.json())["infohash"]
    assert key == info["infohash"] == str(lt.torrent_info(lt.bdecode(data)).info_hashes().v1)
    assert await wait_for(lambda: eng.status(key)["state"] in ("seeding", "finished"), 30), eng.status(key)
    assert eng.status(key)["progress"] == 1.0                          # libtorrent verified every piece
    assert (dl / "album" / "disc1" / "b.bin").read_bytes() == (folder / "disc1" / "b.bin").read_bytes()
    # adding the same torrent again is a conflict
    assert (await c.post("/api/seed/prepare", json={"torrent_b64": b64(data)}, headers=AUTH)).status == 409


async def test_seed_upload_corrupt_content_is_not_seeded(daemon, make_engine, folder):
    eng = await make_engine("dl")
    c = await daemon(eng)
    info = await (await c.post("/api/seed/prepare", json={"torrent_b64": b64(make_torrent_bytes(folder))}, headers=AUTH)).json()
    for f in info["files"]:
        content = bytearray((folder.parent / f["path"]).read_bytes())
        if content:
            content[0] ^= 0xFF                                           # same size, wrong bytes
        await c.put(f"/api/seed/{info['infohash']}/files/{f['index']}", data=bytes(content), headers=AUTH)
    key = (await (await c.post(f"/api/seed/{info['infohash']}/finish", headers=AUTH)).json())["infohash"]
    assert await wait_for(lambda: eng.status(key)["state"] != "checking", 20)
    assert eng.status(key)["progress"] < 1.0                             # damaged pieces are detected, not served


async def test_seed_refuses_to_overwrite_existing_files(daemon, make_engine, folder):
    eng = await make_engine("dl")
    c = await daemon(eng)
    victim = Path(eng.settings.download_dir) / "album" / "a.bin"
    victim.parent.mkdir(parents=True)
    victim.write_bytes(b"precious user data")
    info = await (await c.post("/api/seed/prepare", json={"torrent_b64": b64(make_torrent_bytes(folder))}, headers=AUTH)).json()
    f = next(f for f in info["files"] if f["path"] == "album/a.bin")
    r = await c.put(f"/api/seed/{info['infohash']}/files/{f['index']}", data=b"x" * f["size"], headers=AUTH)
    assert r.status == 409 and victim.read_bytes() == b"precious user data"


async def test_seed_cancel_cleans_up(daemon, make_engine, folder):
    eng = await make_engine("dl")
    c = await daemon(eng)
    info = await (await c.post("/api/seed/prepare", json={"torrent_b64": b64(make_torrent_bytes(folder))}, headers=AUTH)).json()
    f = next(f for f in info["files"] if f["path"] == "album/disc1/b.bin")
    await c.put(f"/api/seed/{info['infohash']}/files/{f['index']}", data=(folder / "disc1" / "b.bin").read_bytes(), headers=AUTH)
    assert (await (await c.delete(f"/api/seed/{info['infohash']}", headers=AUTH)).json())["ok"] is True
    assert not list(Path(eng.settings.download_dir).rglob("*"))
    assert (await c.put(f"/api/seed/{info['infohash']}/files/{f['index']}", data=b"", headers=AUTH)).status == 404


async def test_seed_path_traversal_is_contained(daemon, make_engine, tmp_path):
    """A hostile .torrent naming '../..' paths must never write outside the download directory."""
    payload = b"evil" * 4096
    piece = 16384
    pieces = b"".join(hashlib.sha1(payload[i:i + piece]).digest() for i in range(0, len(payload), piece))
    meta = lt.bencode({"info": {"name": "x", "piece length": piece, "pieces": pieces,
                                "files": [{"length": len(payload), "path": ["..", "..", "escaped.bin"]}]}})
    eng = await make_engine("dl")
    c = await daemon(eng)
    r = await c.post("/api/seed/prepare", json={"torrent_b64": b64(meta)}, headers=AUTH)
    root = Path(eng.settings.download_dir).resolve()
    if r.status == 201:                        # libtorrent sanitised the path; prove it stays inside
        info = await r.json()
        f = info["files"][0]
        await c.put(f"/api/seed/{info['infohash']}/files/{f['index']}", data=payload, headers=AUTH)
    else:
        assert r.status == 422
    assert not (tmp_path / "escaped.bin").exists() and not (root.parent / "escaped.bin").exists()
    assert all(p.resolve().is_relative_to(root) for p in root.rglob("*"))


async def test_seed_disk_full_and_bad_input(daemon, make_engine, folder, monkeypatch):
    c = await daemon(await make_engine("dl"))
    assert (await c.post("/api/seed/prepare", json={"torrent_b64": "!!!"}, headers=AUTH)).status == 422
    assert (await c.post("/api/seed/prepare", json={"torrent_b64": b64(b"not a torrent")}, headers=AUTH)).status == 422
    monkeypatch.setattr(shutil, "disk_usage", lambda p: shutil._ntuple_diskusage(100, 100, 1))
    r = await c.post("/api/seed/prepare", json={"torrent_b64": b64(make_torrent_bytes(folder))}, headers=AUTH)
    assert r.status == 507
