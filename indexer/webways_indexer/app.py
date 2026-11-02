"""HTTP API of an index node. See docs/indexer-api.md."""
from __future__ import annotations

import hmac
import re
import time
from collections import defaultdict, deque

from aiohttp import web

from webways_protocol import ProtocolError, verify_listing, verify_rating

from .db import REPORT_CATEGORIES, Rejected, Store
from .policy import Policy

MAX_BODY = 64 * 1024
_HEX = re.compile(r"^[0-9a-f]{40}$|^[0-9a-f]{64}$")
_B64U = re.compile(r"^[A-Za-z0-9_-]{43}$")
_VALUE_CHECK = {"infohash": _HEX, "listing": re.compile(r"^[0-9a-f]{64}$"), "publisher": _B64U}

STORE = web.AppKey("store", Store)
POLICY = web.AppKey("policy", Policy)
ADMIN = web.AppKey("admin_token", str)
HITS = web.AppKey("hits", dict)


def _json_error(status: int, code: str, message: str) -> web.Response:
    return web.json_response({"error": {"code": code, "message": message}}, status=status)


async def read_json(request: web.Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text='{"error":{"code":"bad_json","message":"body must be JSON"}}',
                                 content_type="application/json")
    if not isinstance(data, dict):
        raise web.HTTPBadRequest(text='{"error":{"code":"bad_json","message":"body must be an object"}}',
                                 content_type="application/json")
    return data


@web.middleware
async def guard(request: web.Request, handler):
    """Rate-limit writes per client IP and map errors to a JSON envelope."""
    if request.method == "POST":
        pol: Policy = request.app[POLICY]
        hits = request.app[HITS].setdefault(request.remote or "?", deque())
        now = time.monotonic()
        while hits and now - hits[0] > 60:
            hits.popleft()
        if len(hits) >= pol.post_rate_per_minute and not request.path.startswith("/v1/admin/"):
            return _json_error(429, "rate_limited", "too many requests")
        hits.append(now)
    try:
        resp = await handler(request)
    except web.HTTPException as exc:
        if exc.content_type == "application/json":
            raise
        return _json_error(exc.status, "http_error", exc.reason or "error")
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers.setdefault("Access-Control-Allow-Origin", "*")  # read API is public data
    return resp


def require_admin(request: web.Request) -> None:
    token = request.app[ADMIN]
    if not token:
        raise web.HTTPNotFound()
    given = request.headers.get("Authorization", "")
    if not given.startswith("Bearer ") or not hmac.compare_digest(given[7:], token):
        raise web.HTTPUnauthorized(headers={"WWW-Authenticate": "Bearer"})


def _int(request: web.Request, name: str, default: int) -> int:
    try:
        return int(request.query.get(name, default))
    except ValueError:
        raise web.HTTPBadRequest(text=f"{name} must be an integer")


# -- public ---------------------------------------------------------------

async def node_info(request: web.Request) -> web.Response:
    pol: Policy = request.app[POLICY]
    return web.json_response({
        "software": "webways-indexer", "protocol": 1, "name": pol.name, "description": pol.description,
        "takedown_contact": pol.takedown_contact, "open_publish": pol.open_publish,
        "stats": request.app[STORE].stats(),
    })


async def publish(request: web.Request) -> web.Response:
    store, pol = request.app[STORE], request.app[POLICY]
    doc = await read_json(request)
    try:
        lid = verify_listing(doc)
    except ProtocolError as exc:
        return _json_error(422, "invalid_listing", str(exc))
    if not pol.open_publish and doc["publisher"] not in pol.allowed_publishers:
        return _json_error(403, "publisher_not_allowed", "this node only lists approved publishers")
    try:
        result = store.upsert(doc, lid, max_per_publisher=pol.max_listings_per_publisher)
    except Rejected as exc:
        return _json_error(403 if exc.code == "blocked" else 429, exc.code, exc.message)
    return web.json_response({"id": lid, "result": result}, status=201 if result == "inserted" else 200)


async def search(request: web.Request) -> web.Response:
    q = request.query
    items = request.app[STORE].search(
        q.get("q", "")[:200], tag=q.get("tag"), license=q.get("license"), publisher=q.get("publisher"),
        infohash=q.get("infohash"), limit=_int(request, "limit", 25), offset=_int(request, "offset", 0))
    return web.json_response({"items": items})


async def get_listing(request: web.Request) -> web.Response:
    item = request.app[STORE].get(request.match_info["id"])
    if not item:
        return _json_error(404, "not_found", "no such listing")
    return web.json_response(item)


async def sync(request: web.Request) -> web.Response:
    items, nxt = request.app[STORE].feed(_int(request, "since", 0), _int(request, "limit", 200))
    return web.json_response({"items": items, "next": nxt})


async def public_blocklist(request: web.Request) -> web.Response:
    # Only this operator's own decisions are exported; subscribed entries are not re-broadcast.
    rows = request.app[STORE].blocklist(local_only=True, since=_int(request, "since", 0))
    return web.json_response({"entries": [{"kind": r["kind"], "value": r["value"], "reason": r["reason"],
                                           "created": r["created"]} for r in rows],
                              "next": rows[-1]["ord"] if rows else _int(request, "since", 0)})


async def report(request: web.Request) -> web.Response:
    body = await read_json(request)
    lid, cat = body.get("listing"), body.get("category")
    if not (isinstance(lid, str) and re.fullmatch(r"[0-9a-f]{64}", lid)) or cat not in REPORT_CATEGORIES:
        return _json_error(422, "invalid_report", f"listing id and category in {list(REPORT_CATEGORIES)} required")
    detail, contact = str(body.get("detail", ""))[:1000], str(body.get("contact", ""))[:200]
    return web.json_response({"report": request.app[STORE].add_report(lid, cat, detail, contact)}, status=201)


async def rate(request: web.Request) -> web.Response:
    body = await read_json(request)
    try:
        verify_rating(body)
    except ProtocolError as exc:
        return _json_error(422, "invalid_rating", str(exc))
    if not request.app[STORE].rate(body["listing"], body["rater"], body["score"], body["created"]):
        return _json_error(404, "not_found", "no such listing")
    return web.json_response({"ok": True})


# -- operator -------------------------------------------------------------

async def admin_takedown(request: web.Request) -> web.Response:
    """Remove listings and block re-listing. Body: {kind, value, reason, notice_ref}."""
    require_admin(request)
    b = await read_json(request)
    kind, value = b.get("kind"), b.get("value")
    if kind not in _VALUE_CHECK or not isinstance(value, str) or not _VALUE_CHECK[kind].match(value):
        return _json_error(422, "invalid_target", "kind must be infohash|listing|publisher with a well-formed value")
    n = request.app[STORE].takedown(kind, value, reason=str(b.get("reason", ""))[:500],
                                    notice_ref=str(b.get("notice_ref", ""))[:200])
    return web.json_response({"removed": n})


async def admin_unblock(request: web.Request) -> web.Response:
    """Reinstate after a successful counter-notice: lifts the block (listings must be re-published)."""
    require_admin(request)
    b = await read_json(request)
    ok = request.app[STORE].remove_block(str(b.get("kind")), str(b.get("value")))
    return web.json_response({"unblocked": ok})


async def admin_reports(request: web.Request) -> web.Response:
    require_admin(request)
    return web.json_response({"reports": request.app[STORE].reports(request.query.get("all") == "1")})


async def admin_resolve(request: web.Request) -> web.Response:
    require_admin(request)
    ok = request.app[STORE].resolve_report(int(request.match_info["id"]))
    return web.json_response({"resolved": ok})


async def admin_takedown_log(request: web.Request) -> web.Response:
    require_admin(request)
    return web.json_response({"takedowns": request.app[STORE].takedown_log()})


async def admin_verify(request: web.Request) -> web.Response:
    require_admin(request)
    b = await read_json(request)
    pub = b.get("publisher")
    if not isinstance(pub, str) or not _B64U.match(pub):
        return _json_error(422, "invalid_publisher", "publisher must be a base64url ed25519 key")
    store = request.app[STORE]
    if b.get("revoke"):
        return web.json_response({"revoked": store.unset_verified(pub)})
    store.set_verified(pub, str(b.get("name", ""))[:100] or pub[:8], str(b.get("note", ""))[:300])
    return web.json_response({"ok": True})


def make_app(store: Store, policy: Policy, admin_token: str = "") -> web.Application:
    app = web.Application(middlewares=[guard], client_max_size=MAX_BODY)
    app[STORE], app[POLICY], app[ADMIN], app[HITS] = store, policy, admin_token, {}
    app.add_routes([
        web.get("/v1/node", node_info),
        web.post("/v1/listings", publish),
        web.get("/v1/listings", search),
        web.get("/v1/listings/{id:[0-9a-f]{64}}", get_listing),
        web.get("/v1/sync", sync),
        web.get("/v1/blocklist", public_blocklist),
        web.post("/v1/reports", report),
        web.post("/v1/ratings", rate),
        web.post("/v1/admin/takedown", admin_takedown),
        web.post("/v1/admin/unblock", admin_unblock),
        web.get("/v1/admin/reports", admin_reports),
        web.post("/v1/admin/reports/{id:\\d+}/resolve", admin_resolve),
        web.get("/v1/admin/takedowns", admin_takedown_log),
        web.post("/v1/admin/verify", admin_verify),
    ])
    return app
