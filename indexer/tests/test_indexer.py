import aiohttp
import pytest
from aiohttp.test_utils import TestClient, TestServer

from webways_indexer.app import make_app
from webways_indexer.db import Store
from webways_indexer.federation import sync_blocklist, sync_peer
from webways_indexer.policy import Policy
from webways_protocol import Identity, listing_id, sign_listing, sign_rating

ADMIN = {"Authorization": "Bearer s3cret"}


def listing(ident, ih="ab" * 20, **kw):
    kw = {"title": "Big Buck Bunny", "description": "open movie", "tags": ["film"], "license": "CC-BY-3.0", **kw}
    return sign_listing(ident, infohash=ih, **kw)


@pytest.fixture
async def node():
    clients = []

    async def make(policy=None):
        store = Store()
        c = TestClient(TestServer(make_app(store, policy or Policy(name="t"), "s3cret")))
        await c.start_server()
        clients.append(c)
        return c, store

    yield make
    for c in clients:
        await c.close()


async def test_publish_search_get(node):
    c, _ = await node()
    ident = Identity.generate()
    doc = listing(ident)
    r = await c.post("/v1/listings", json=doc)
    assert r.status == 201
    lid = (await r.json())["id"]
    assert lid == listing_id(doc)
    got = await (await c.get("/v1/listings", params={"q": "bunn"})).json()
    assert [i["id"] for i in got["items"]] == [lid]
    assert (await (await c.get("/v1/listings", params={"tag": "nope"})).json())["items"] == []
    assert (await c.get(f"/v1/listings/{lid}")).status == 200
    assert (await c.get("/v1/listings/" + "0" * 64)).status == 404


async def test_rejects_tampered_and_garbage(node):
    c, _ = await node()
    doc = listing(Identity.generate())
    doc["title"] = "forged"
    assert (await c.post("/v1/listings", json=doc)).status == 422
    assert (await c.post("/v1/listings", data="not json")).status == 400
    assert (await c.post("/v1/listings", json=[1])).status == 400


async def test_fts_syntax_is_not_injectable(node):
    c, _ = await node()
    await c.post("/v1/listings", json=listing(Identity.generate()))
    for q in ['"', "AND OR NOT", "title:*", "bunny) OR (x", "NEAR(", "'; DROP TABLE listings;--"]:
        r = await c.get("/v1/listings", params={"q": q})
        assert r.status == 200


async def test_supersede_and_withdraw(node):
    c, _ = await node()
    ident = Identity.generate()
    v0, v1 = listing(ident), listing(ident, seq=1, title="Renamed")
    assert (await c.post("/v1/listings", json=v0)).status == 201
    assert (await c.post("/v1/listings", json=v1)).status == 200
    assert (await (await c.post("/v1/listings", json=v0)).json())["result"] == "stale"
    items = (await (await c.get("/v1/listings")).json())["items"]
    assert [i["listing"]["title"] for i in items] == ["Renamed"]
    w = listing(ident, seq=2, withdrawn=True)
    await c.post("/v1/listings", json=w)
    assert (await (await c.get("/v1/listings")).json())["items"] == []
    # the withdrawal still travels through the sync feed so peers drop it too
    feed = await (await c.get("/v1/sync")).json()
    assert feed["items"][-1].get("withdrawn") is True


async def test_takedown_removes_and_blocks(node):
    c, _ = await node()
    ident = Identity.generate()
    doc = listing(ident)
    await c.post("/v1/listings", json=doc)
    assert (await c.post("/v1/admin/takedown", json={"kind": "infohash", "value": doc["infohash"]})).status == 401
    r = await c.post("/v1/admin/takedown", headers=ADMIN, json={
        "kind": "infohash", "value": doc["infohash"], "reason": "dmca", "notice_ref": "N-1"})
    assert (await r.json())["removed"] == 1
    assert (await (await c.get("/v1/listings")).json())["items"] == []
    # the same infohash cannot come back under another publisher
    again = await c.post("/v1/listings", json=listing(Identity.generate()))
    assert again.status == 403 and (await again.json())["error"]["code"] == "blocked"
    log = await (await c.get("/v1/admin/takedowns", headers=ADMIN)).json()
    assert log["takedowns"][0]["notice_ref"] == "N-1"
    # counter-notice: lift the block
    await c.post("/v1/admin/unblock", headers=ADMIN, json={"kind": "infohash", "value": doc["infohash"]})
    assert (await c.post("/v1/listings", json=listing(ident))).status == 201


async def test_publisher_takedown_and_bad_target(node):
    c, _ = await node()
    ident = Identity.generate()
    await c.post("/v1/listings", json=listing(ident))
    await c.post("/v1/listings", json=listing(ident, ih="cd" * 20))
    r = await c.post("/v1/admin/takedown", headers=ADMIN, json={"kind": "publisher", "value": ident.public_key})
    assert (await r.json())["removed"] == 2
    bad = await c.post("/v1/admin/takedown", headers=ADMIN, json={"kind": "infohash", "value": "x' OR 1=1"})
    assert bad.status == 422


async def test_admin_disabled_without_token():
    c = TestClient(TestServer(make_app(Store(), Policy(), "")))
    await c.start_server()
    try:
        assert (await c.get("/v1/admin/reports", headers=ADMIN)).status == 404
    finally:
        await c.close()


async def test_allowlist_mode(node):
    ident, other = Identity.generate(), Identity.generate()
    c, _ = await node(Policy(open_publish=False, allowed_publishers={ident.public_key}))
    assert (await c.post("/v1/listings", json=listing(other))).status == 403
    assert (await c.post("/v1/listings", json=listing(ident))).status == 201


async def test_quota(node):
    ident = Identity.generate()
    c, _ = await node(Policy(max_listings_per_publisher=1))
    assert (await c.post("/v1/listings", json=listing(ident))).status == 201
    assert (await c.post("/v1/listings", json=listing(ident, ih="cd" * 20))).status == 429


async def test_reports_ratings_verified(node):
    c, _ = await node()
    ident = Identity.generate()
    doc = listing(ident)
    lid = (await (await c.post("/v1/listings", json=doc)).json())["id"]
    assert (await c.post("/v1/reports", json={"listing": lid, "category": "malware", "detail": "x"})).status == 201
    assert (await c.post("/v1/reports", json={"listing": lid, "category": "bogus"})).status == 422
    assert len((await (await c.get("/v1/admin/reports", headers=ADMIN)).json())["reports"]) == 1
    for score in (5, 3):
        assert (await c.post("/v1/ratings", json=sign_rating(Identity.generate(), lid, score))).status == 200
    rater = Identity.generate()
    await c.post("/v1/ratings", json=sign_rating(rater, lid, 1, created=100))
    await c.post("/v1/ratings", json=sign_rating(rater, lid, 5, created=200))  # same key: one vote, newest wins
    await c.post("/v1/admin/verify", headers=ADMIN, json={"publisher": ident.public_key, "name": "Blender"})
    item = await (await c.get(f"/v1/listings/{lid}")).json()
    assert item["rating"] == {"average": 4.33, "count": 3}
    assert item["verified"]["name"] == "Blender"


async def test_federation_pull_and_hostile_peer(node):
    a, a_store = await node()
    b, b_store = await node()
    ident = Identity.generate()
    good = listing(ident)
    await a.post("/v1/listings", json=good)
    # a hostile peer slips a forged listing and a blocked one straight into its own database
    forged = listing(Identity.generate(), ih="11" * 20)
    forged["title"] = "forged"
    a_store.db.execute("INSERT INTO listings(id,infohash,publisher,license,seq,created,withdrawn,received_at,doc) "
                       "VALUES ('f'||hex(randomblob(31)),?,?,?,0,0,0,0,?)",
                       (forged["infohash"], forged["publisher"], forged["license"], __import__("json").dumps(forged)))
    b_store.add_block("infohash", "22" * 20, "local decision")
    blocked = listing(Identity.generate(), ih="22" * 20)
    await a.post("/v1/listings", json=blocked)

    async with aiohttp.ClientSession() as s:
        stats = await sync_peer(b_store, Policy(), s, str(a.make_url("")))
    assert stats["inserted"] == 1 and stats["rejected"] == 2
    got = await (await b.get("/v1/listings")).json()
    assert [i["listing"]["title"] for i in got["items"]] == ["Big Buck Bunny"]
    async with aiohttp.ClientSession() as s:     # incremental: nothing new
        assert (await sync_peer(b_store, Policy(), s, str(a.make_url(""))))["inserted"] == 0


async def test_blocklist_subscription_follows_source(node):
    a, _ = await node()
    b, b_store = await node()
    ident = Identity.generate()
    doc = listing(ident)
    await b.post("/v1/listings", json=doc)
    await a.post("/v1/admin/takedown", headers=ADMIN, json={"kind": "infohash", "value": doc["infohash"], "reason": "r"})
    url = str(a.make_url(""))
    async with aiohttp.ClientSession() as s:
        assert await sync_blocklist(b_store, s, url) == 1
    assert (await (await b.get("/v1/listings")).json())["items"] == []
    assert (await b.post("/v1/listings", json=doc)).status == 403
    # source operator reverses the decision -> subscriber follows
    await a.post("/v1/admin/unblock", headers=ADMIN, json={"kind": "infohash", "value": doc["infohash"]})
    async with aiohttp.ClientSession() as s:
        await sync_blocklist(b_store, s, url)
    assert (await b.post("/v1/listings", json=doc)).status == 201


async def test_local_block_survives_unsubscribe(node):
    a, _ = await node()
    _, b_store = await node()
    ih = "33" * 20
    await a.post("/v1/admin/takedown", headers=ADMIN, json={"kind": "infohash", "value": ih})
    url = str(a.make_url(""))
    async with aiohttp.ClientSession() as s:
        await sync_blocklist(b_store, s, url)
    b_store.takedown("infohash", ih, reason="own decision", notice_ref="")
    b_store.replace_subscription(url.rstrip("/"), [])
    assert b_store.block_reason({"infohash": ih, "publisher": "p"}, "l") is not None
