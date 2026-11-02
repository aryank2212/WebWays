import asyncio
import base64
import json
import time

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from swarm_core.config import Settings
from swarm_core.engine import Engine
from swarm_core.streaming import content_type, parse_range
from swarm_indexer.app import make_app as make_indexer
from swarm_indexer.db import Store
from swarm_indexer.policy import Policy
from swarm_protocol import Identity, sign_listing

from .conftest import AUTH, TOKEN, loopback, wait_for


def test_parse_range():
    assert parse_range(None, 100) is None
    assert parse_range("bytes=0-9", 100) == (0, 9)
    assert parse_range("bytes=90-", 100) == (90, 99)
    assert parse_range("bytes=-10", 100) == (90, 99)
    assert parse_range("bytes=50-500", 100) == (50, 99)
    assert parse_range("bytes=0-1,5-6", 100) is None          # multi-range: serve whole file
    assert parse_range("bytes=abc", 100) is None
    for bad in ("bytes=100-", "bytes=10-5", "bytes=-0"):
        with pytest.raises(ValueError):
            parse_range(bad, 100)


def test_content_type_allowlist():
    assert content_type("a/b.mp4") == "video/mp4"
    assert content_type("x.mp3").startswith("audio/")
    for risky in ("x.html", "x.svg", "x.js", "x.xml", "x.exe", "noext"):
        assert content_type(risky) == "application/octet-stream"


def test_no_default_sources():
    assert Settings().sources == []


async def test_auth_host_and_origin(daemon, make_engine):
    c = await daemon(await make_engine("d"))
    assert (await c.get("/api/status")).status == 401
    assert (await c.get("/api/status", headers={"Authorization": "Bearer nope"})).status == 401
    assert (await c.get("/api/status", headers=AUTH)).status == 200
    assert (await c.get("/api/status", headers={**AUTH, "Host": "evil.example"})).status == 421   # DNS rebinding
    r = await c.post("/api/torrents", json={}, headers={**AUTH, "Origin": "http://evil.example"})
    assert r.status == 403
    assert (await c.get("/stream/" + "a" * 40 + "/0?sig=bad")).status == 403


async def test_stream_while_downloading(daemon, make_engine, payload):
    seeder = await make_engine("seed")
    key = seeder.create_torrent(str(payload))
    # throttle the leecher so the torrent is provably incomplete while we stream from the middle
    leecher = await make_engine("leech", download_limit=1_500_000)
    leecher.apply_settings()
    c = await daemon(leecher)
    r = await c.post("/api/torrents", json={"infohash": key}, headers=AUTH)
    assert r.status == 201
    leecher.connect_peer(key, "127.0.0.1", seeder.session.listen_port())
    assert await wait_for(lambda: leecher.status(key)["has_metadata"])

    info = await (await c.get(f"/api/torrents/{key}", headers=AUTH)).json()
    movie = next(f for f in info["files"] if f["path"].endswith("movie.mp4"))
    expected = (payload / "movie.mp4").read_bytes()

    start, end = 4_000_000, 4_300_000
    t0 = time.monotonic()
    r = await c.get(movie["stream_url"], headers={"Range": f"bytes={start}-{end}"})
    body = await r.read()
    assert r.status == 206
    assert r.headers["Content-Range"] == f"bytes {start}-{end}/{len(expected)}"
    assert r.headers["Content-Type"] == "video/mp4"
    assert body == expected[start:end + 1]
    assert time.monotonic() - t0 < 25
    assert leecher.status(key)["progress"] < 1.0, "range must be served before the whole torrent is done"

    # suffix range, HEAD, and unsatisfiable range
    r = await c.get(movie["stream_url"], headers={"Range": "bytes=-1000"})
    assert await r.read() == expected[-1000:]
    r = await c.head(movie["stream_url"])
    assert r.status == 200 and r.headers["Content-Length"] == str(len(expected))
    r = await c.get(movie["stream_url"], headers={"Range": f"bytes={len(expected)}-"})
    assert r.status == 416

    # a hostile html file must never be rendered inline on this origin
    page = next(f for f in info["files"] if f["path"].endswith("page.html"))
    r = await c.get(page["stream_url"])
    assert r.status == 200
    assert r.headers["Content-Type"] == "application/octet-stream"
    assert r.headers["Content-Disposition"] == "attachment"
    assert "sandbox" in r.headers["Content-Security-Policy"]
    # signature is bound to the file index
    assert (await c.get(page["stream_url"].replace("/1?", "/0?").replace("/0?", "/0?"))).status in (200, 403)
    other = movie["stream_url"].replace(f"/{movie['index']}?", f"/{page['index']}?")
    assert (await c.get(other)).status == 403


async def test_torrent_lifecycle_and_resume(daemon, make_engine, payload, tmp_path):
    seeder = await make_engine("seed")
    key = seeder.create_torrent(str(payload / "movie.mp4"))
    eng = Engine(Settings(download_dir=str(tmp_path / "dl")), tmp_path / "dl-state", loopback())
    await eng.start()
    c = await daemon(eng)
    assert (await c.post("/api/torrents", json={"magnet": "http://x"}, headers=AUTH)).status == 422
    assert (await c.post("/api/torrents", json={"infohash": "XYZ"}, headers=AUTH)).status == 422
    assert (await c.post("/api/torrents", json={"infohash": key}, headers=AUTH)).status == 201
    eng.connect_peer(key, "127.0.0.1", seeder.session.listen_port())
    assert await wait_for(lambda: eng.status(key)["state"] in ("seeding", "finished"), 40)
    assert (await (await c.post(f"/api/torrents/{key}/pause", headers=AUTH)).json())["state"] == "paused"
    await c.post(f"/api/torrents/{key}/resume", headers=AUTH)
    assert (await (await c.get(f"/api/torrents/{key}", headers=AUTH)).json())["files"][0]["progress"] == 1.0
    assert (await c.put(f"/api/torrents/{key}/files/0/priority", json={"priority": 9}, headers=AUTH)).status == 422
    assert (await c.post(f"/api/torrents/{key}/peers", json={"host": "example.com", "port": 1}, headers=AUTH)).status == 422
    assert (await c.post(f"/api/torrents/{key}/peers", json={"host": "127.0.0.1", "port": 99999}, headers=AUTH)).status == 422
    assert (await c.post(f"/api/torrents/{key}/peers", json={"host": "127.0.0.1", "port": 6881}, headers=AUTH)).status == 200
    await eng.stop()

    # restart: the torrent comes back from resume data, already complete
    eng2 = Engine(Settings(download_dir=str(tmp_path / "dl")), tmp_path / "dl-state", loopback())
    await eng2.start()
    assert key in eng2.handles
    assert await wait_for(lambda: eng2.status(key)["state"] in ("seeding", "finished"), 20), eng2.status(key)
    eng2.remove(key, delete_files=True)
    assert key not in eng2.handles
    assert not list((tmp_path / "dl-state" / "resume").glob("*.resume"))
    await eng2.stop()


async def test_settings_validation(daemon, make_engine):
    c = await daemon(await make_engine("s"))
    assert (await c.put("/api/settings", json={"encryption": "none"}, headers=AUTH)).status == 422
    assert (await c.put("/api/settings", json={"download_dir": "relative/path"}, headers=AUTH)).status == 422
    assert (await (await c.get("/api/settings", headers=AUTH)).json())["encryption"] == "enabled"


async def test_publish_search_download_loop(daemon, make_engine, payload, tmp_path):
    """Publisher signs a listing -> index node -> client searches via its sources -> downloads."""
    node_store = Store()
    node = TestClient(TestServer(make_indexer(node_store, Policy(name="test-node"), "adm")))
    await node.start_server()
    try:
        seeder = await make_engine("seed")
        key = seeder.create_torrent(str(payload / "movie.mp4"))
        leecher = await make_engine("leech")
        c = await daemon(leecher, config_dir=tmp_path / "cfg-leech")
        pub = await daemon(seeder, config_dir=tmp_path / "cfg-pub")

        node_url = str(node.make_url("")).rstrip("/")
        # fresh client has no sources at all
        assert (await (await c.get("/api/sources", headers=AUTH)).json())["sources"] == []
        assert (await c.post("/api/sources", json={"url": "ftp://x"}, headers=AUTH)).status == 422
        assert (await c.post("/api/sources", json={"url": node_url}, headers=AUTH)).status == 201

        # publisher side (publishing also goes through a source the publisher has chosen)
        assert (await pub.post("/api/sources", json={"url": node_url}, headers=AUTH)).status == 201
        assert (await pub.post("/api/publish", json={"infohash": key}, headers=AUTH)).status == 409
        assert (await pub.post("/api/identity", headers=AUTH)).status == 201
        bad = await pub.post("/api/publish", json={"infohash": key, "title": "", "license": "CC0-1.0"}, headers=AUTH)
        assert bad.status == 422
        r = await pub.post("/api/publish", headers=AUTH, json={
            "infohash": key, "title": "Test Movie", "description": "random bytes", "tags": ["demo"],
            "license": "CC0-1.0", "source": node_url})
        assert r.status == 201, await r.text()

        # client side
        res = await (await c.get("/api/search?q=movie", headers=AUTH)).json()
        assert [i["listing"]["title"] for i in res["items"]] == ["Test Movie"]
        assert res["items"][0]["sources"][0]["name"] == "test-node"
        assert (await c.post("/api/torrents", json={"infohash": res["items"][0]["listing"]["infohash"]},
                             headers=AUTH)).status == 201
        leecher.connect_peer(key, "127.0.0.1", seeder.session.listen_port())
        assert await wait_for(lambda: leecher.status(key)["state"] in ("seeding", "finished"), 40)

        # republishing bumps seq automatically; withdrawing removes it from search
        await pub.post("/api/publish", json={"infohash": key, "title": "Test Movie v2", "license": "CC0-1.0",
                                             "source": node_url}, headers=AUTH)
        res = await (await c.get("/api/search?q=movie", headers=AUTH)).json()
        assert res["items"][0]["listing"]["title"] == "Test Movie v2"
        await pub.post("/api/publish", json={"infohash": key, "title": "Test Movie v2", "license": "CC0-1.0",
                                             "withdrawn": True, "source": node_url}, headers=AUTH)
        assert (await (await c.get("/api/search?q=movie", headers=AUTH)).json())["items"] == []

        # reports go to the chosen node's operator
        lid = r_id = (await r.json())["id"]
        rep = await c.post("/api/report", json={"source": node_url, "listing": lid, "category": "spam"}, headers=AUTH)
        assert rep.status == 200
        assert (await node.get("/v1/admin/reports", headers={"Authorization": "Bearer adm"})).status == 200
    finally:
        await node.close()


async def test_search_drops_forged_listings_from_hostile_node(daemon, make_engine):
    ident = Identity.generate()
    good = sign_listing(ident, infohash="ab" * 20, title="Genuine", license="CC0-1.0")
    forged = dict(good, title="Free Money", infohash="cd" * 20)      # signature no longer matches
    wrong_key = dict(good, publisher=Identity.generate().public_key)

    async def info(_):
        return web.json_response({"software": "swarm-indexer", "name": "evil", "takedown_contact": ""})

    async def listings(_):
        wrap = lambda d: {"id": "0" * 64, "listing": d, "verified": {"name": "Totally Official"},
                          "rating": {"average": 5.0, "count": 999}}
        return web.json_response({"items": [wrap(forged), wrap(wrong_key), wrap(good), {"junk": 1}, "x"]})

    app = web.Application()
    app.add_routes([web.get("/v1/node", info), web.get("/v1/listings", listings)])
    evil = TestClient(TestServer(app))
    await evil.start_server()
    try:
        c = await daemon(await make_engine("h"))
        assert (await c.post("/api/sources", json={"url": str(evil.make_url(""))}, headers=AUTH)).status == 201
        items = (await (await c.get("/api/search?q=x", headers=AUTH)).json())["items"]
        assert [i["listing"]["title"] for i in items] == ["Genuine"]
        # claims made by a node are attributed to that node, never presented as fact
        assert items[0]["verified_by"] == [{"node": "evil", "name": "Totally Official"}]
    finally:
        await evil.close()


async def test_dead_source_reported_not_fatal(daemon, make_engine):
    c = await daemon(await make_engine("h"))
    c.server.app[__import__("swarm_core.api", fromlist=["K_SETTINGS"]).K_SETTINGS].sources.append(
        {"url": "http://127.0.0.1:9", "name": "down", "enabled": True})
    res = await (await c.get("/api/search?q=x", headers=AUTH)).json()
    assert res["items"] == [] and "http://127.0.0.1:9" in res["errors"]
