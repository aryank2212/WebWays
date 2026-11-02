"""Local REST API. The UI (and any other front end) talks only to this."""
from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import ipaddress
import json
import re
from pathlib import Path
from urllib.parse import quote, urlsplit

from aiohttp import web

from swarm_protocol import Identity, ProtocolError, listing_id, sign_listing, sign_rating

from . import __version__
from .config import Settings
from .engine import Engine, EngineError
from .seeding import SeedError, SeedStaging
from .sources import Sources
from .streaming import Streamer

K_SETTINGS = web.AppKey("settings", Settings)
K_SETTINGS_PATH = web.AppKey("settings_path", Path)
K_ENGINE = web.AppKey("engine", Engine)
K_SOURCES = web.AppKey("sources", Sources)
K_STREAMER = web.AppKey("streamer", Streamer)
K_TOKEN = web.AppKey("token", str)
K_CONFIG_DIR = web.AppKey("config_dir", Path)
K_HOSTS = web.AppKey("hosts", set)
K_UI = web.AppKey("ui_dir", Path)
K_SEED = web.AppKey("seed", SeedStaging)

_KEY = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
CSP = ("default-src 'self'; img-src 'self' data:; media-src 'self'; style-src 'self' 'unsafe-inline'; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")


def stream_sig(token: str, key: str, index: int) -> str:
    return hmac.new(token.encode(), f"{key}:{index}".encode(), hashlib.sha256).hexdigest()[:32]


def jerr(status: int, message: str, code: str = "error") -> web.Response:
    return web.json_response({"error": {"code": code, "message": message}}, status=status)


@web.middleware
async def security(request: web.Request, handler):
    app = request.app
    # DNS-rebinding defence: only answer to names that really mean this machine (or are allow-listed).
    host = urlsplit("//" + request.headers.get("Host", "")).hostname
    if host not in app[K_HOSTS]:
        return jerr(421, "unrecognised Host header", "bad_host")
    origin = request.headers.get("Origin")
    if origin and request.method not in ("GET", "HEAD", "OPTIONS"):
        if urlsplit(origin).netloc != request.headers.get("Host"):
            return jerr(403, "cross-origin request refused", "bad_origin")
    path = request.path
    if path.startswith("/api/"):
        given = request.headers.get("Authorization", "")
        if not given.startswith("Bearer ") or not hmac.compare_digest(given[7:], app[K_TOKEN]):
            return jerr(401, "missing or invalid API token", "unauthorized")
    elif path.startswith("/stream/"):
        m = re.fullmatch(r"/stream/([0-9a-f]{40}|[0-9a-f]{64})/(\d+)", path)
        sig = request.query.get("sig", "")
        if not m or not hmac.compare_digest(sig, stream_sig(app[K_TOKEN], m[1], int(m[2]))):
            return jerr(403, "invalid stream signature", "bad_sig")
    try:
        resp = await handler(request)
    except web.HTTPException as exc:
        if path.startswith(("/api/", "/stream/")):
            return jerr(exc.status, exc.text or exc.reason, "http_error")
        raise
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    if not path.startswith("/stream/"):
        resp.headers.setdefault("Content-Security-Policy", CSP)
    return resp


async def body(request: web.Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="body must be JSON")
    if not isinstance(data, dict):
        raise web.HTTPBadRequest(text="body must be a JSON object")
    return data


def key_param(request: web.Request) -> str:
    key = request.match_info["key"]
    if not _KEY.match(key):
        raise web.HTTPBadRequest(text="bad infohash")
    return key


def torrent_json(request: web.Request, key: str) -> dict:
    s = request.app[K_ENGINE].status(key)
    s["magnet"] = f"magnet:?xt=urn:btih:{key}&dn={quote(s['name'])}" if len(key) == 40 else None
    return s


# -- status / settings ------------------------------------------------------

async def status(request: web.Request) -> web.Response:
    return web.json_response({"version": __version__, **request.app[K_ENGINE].overview(),
                              "encryption": request.app[K_SETTINGS].encryption})


async def get_settings(request: web.Request) -> web.Response:
    s = request.app[K_SETTINGS]
    return web.json_response({k: getattr(s, k) for k in ("download_dir", "listen_port", "encryption",
                                                         "download_limit", "upload_limit")})


async def put_settings(request: web.Request) -> web.Response:
    app, data = request.app, await body(request)
    s = app[K_SETTINGS]
    old = {k: getattr(s, k) for k in ("download_dir", "listen_port", "encryption", "download_limit", "upload_limit")}
    try:
        for k in old:
            if k in data:
                setattr(s, k, data[k])
        if not isinstance(s.download_dir, str) or not Path(s.download_dir).is_absolute():
            raise ValueError("download_dir must be an absolute path")
        s.validate()
        Path(s.download_dir).mkdir(parents=True, exist_ok=True)
    except (ValueError, TypeError, OSError) as exc:
        for k, v in old.items():
            setattr(s, k, v)
        return jerr(422, str(exc), "invalid_settings")
    s.save(app[K_SETTINGS_PATH])
    app[K_ENGINE].apply_settings()
    return await get_settings(request)


# -- torrents -----------------------------------------------------------------

async def list_torrents(request: web.Request) -> web.Response:
    eng = request.app[K_ENGINE]
    items = [torrent_json(request, k) for k in list(eng.handles) if eng.handles[k].is_valid()]
    return web.json_response({"torrents": items})


async def add_torrent(request: web.Request) -> web.Response:
    eng, data = request.app[K_ENGINE], await body(request)
    try:
        if "magnet" in data:
            key = eng.add_magnet(str(data["magnet"]))
        elif "infohash" in data:
            key = eng.add_infohash(str(data["infohash"]).lower(), str(data.get("name", "")))
        elif "torrent_b64" in data:
            key = eng.add_torrent_bytes(base64.b64decode(str(data["torrent_b64"]), validate=True))
        else:
            return jerr(422, "give one of: magnet, infohash, torrent_b64", "invalid_request")
    except (EngineError, binascii.Error) as exc:
        return jerr(422, str(exc), "invalid_torrent")
    return web.json_response(torrent_json(request, key), status=201)


async def get_torrent(request: web.Request) -> web.Response:
    key = key_param(request)
    try:
        info = torrent_json(request, key)
    except KeyError:
        return jerr(404, "no such torrent", "not_found")
    token = request.app[K_TOKEN]
    info["files"] = [{**f, "stream_url": f"/stream/{key}/{f['index']}?sig={stream_sig(token, key, f['index'])}"}
                     for f in request.app[K_ENGINE].files(key)]
    return web.json_response(info)


async def torrent_action(request: web.Request) -> web.Response:
    key, eng = key_param(request), request.app[K_ENGINE]
    try:
        {"pause": eng.pause, "resume": eng.resume}[request.match_info["action"]](key)
    except KeyError:
        return jerr(404, "no such torrent", "not_found")
    return web.json_response(torrent_json(request, key))


async def delete_torrent(request: web.Request) -> web.Response:
    key = key_param(request)
    try:
        request.app[K_ENGINE].remove(key, delete_files=request.query.get("delete_files") == "1")
    except KeyError:
        return jerr(404, "no such torrent", "not_found")
    return web.json_response({"ok": True})


async def add_peer(request: web.Request) -> web.Response:
    """Manually connect a torrent to a known peer (IP literal + port)."""
    key, data = key_param(request), await body(request)
    try:
        host = str(ipaddress.ip_address(str(data.get("host", ""))))
        port = int(data.get("port", 0))
        if not 1 <= port <= 65535:
            raise ValueError("port out of range")
        request.app[K_ENGINE].connect_peer(key, host, port)
    except KeyError:
        return jerr(404, "no such torrent", "not_found")
    except (ValueError, TypeError) as exc:
        return jerr(422, f"host must be an IP address and port 1-65535 ({exc})", "invalid_request")
    return web.json_response({"ok": True})


async def file_priority(request: web.Request) -> web.Response:
    key, data = key_param(request), await body(request)
    try:
        request.app[K_ENGINE].set_file_priority(key, int(request.match_info["index"]), int(data.get("priority", -1)))
    except KeyError:
        return jerr(404, "no such torrent", "not_found")
    except (EngineError, ValueError, TypeError) as exc:
        return jerr(422, str(exc), "invalid_request")
    return web.json_response({"ok": True})


def _str_list(value, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value) or len(value) > 50:
        raise ValueError(f"{field} must be a list of up to 50 strings")
    return tuple(v.strip() for v in value if v.strip())


async def create_torrent(request: web.Request) -> web.Response:
    """Hash a path on the daemon's machine and seed it. Options: comment, trackers, webseeds,
    private, piece_size, version (v1|v2|hybrid). No trackers are added unless you list them."""
    eng, data = request.app[K_ENGINE], await body(request)
    try:
        opts = dict(comment=str(data.get("comment", "")), trackers=_str_list(data.get("trackers"), "trackers"),
                    webseeds=_str_list(data.get("webseeds"), "webseeds"), private=bool(data.get("private", False)),
                    piece_size=int(data.get("piece_size", 0)), version=str(data.get("version", "hybrid")))
        key = await asyncio.get_running_loop().run_in_executor(
            None, lambda: eng.create_torrent(str(data.get("path", "")), **opts))
    except (EngineError, OSError, RuntimeError, ValueError, TypeError) as exc:
        return jerr(422, str(exc), "invalid_request")
    return web.json_response(torrent_json(request, key), status=201)


async def download_torrent_file(request: web.Request) -> web.Response:
    key = key_param(request)
    try:
        data = request.app[K_ENGINE].torrent_file(key)
    except KeyError:
        return jerr(404, "no such torrent", "not_found")
    except EngineError as exc:
        return jerr(409, str(exc), "no_metadata")
    return web.Response(body=data, content_type="application/x-bittorrent",
                        headers={"Content-Disposition": f'attachment; filename="{key}.torrent"'})


def _seed_error(exc: SeedError) -> web.Response:
    return jerr(exc.status, str(exc), "seed_error")


async def seed_prepare(request: web.Request) -> web.Response:
    data = await body(request)
    try:
        raw = base64.b64decode(str(data.get("torrent_b64", "")), validate=True)
        return web.json_response(request.app[K_SEED].prepare(raw), status=201)
    except binascii.Error:
        return jerr(422, "torrent_b64 must be base64", "invalid_request")
    except SeedError as exc:
        return _seed_error(exc)


async def seed_put(request: web.Request) -> web.Response:
    try:
        await request.app[K_SEED].put(request, key_param(request), int(request.match_info["index"]))
    except SeedError as exc:
        return _seed_error(exc)
    return web.json_response({"ok": True})


async def seed_finish(request: web.Request) -> web.Response:
    try:
        key = request.app[K_SEED].finish(key_param(request))
    except SeedError as exc:
        return _seed_error(exc)
    return web.json_response(torrent_json(request, key), status=201)


async def seed_cancel(request: web.Request) -> web.Response:
    return web.json_response({"ok": request.app[K_SEED].cancel(key_param(request))})


async def stream(request: web.Request) -> web.StreamResponse:
    m = re.fullmatch(r"/stream/([0-9a-f]{40}|[0-9a-f]{64})/(\d+)", request.path)
    return await request.app[K_STREAMER].handle(request, m[1], int(m[2]))


# -- sources / discovery --------------------------------------------------------

async def list_sources(request: web.Request) -> web.Response:
    return web.json_response({"sources": request.app[K_SOURCES].list()})


async def add_source(request: web.Request) -> web.Response:
    data = await body(request)
    try:
        entry = await request.app[K_SOURCES].add(str(data.get("url", "")), str(data.get("name", "")))
    except (ValueError, OSError) as exc:
        return jerr(422, str(exc) or "could not reach that node", "invalid_source")
    except Exception as exc:  # aiohttp client errors
        return jerr(502, f"could not reach that node: {type(exc).__name__}", "unreachable")
    return web.json_response(entry, status=201)


async def update_source(request: web.Request) -> web.Response:
    data = await body(request)
    try:
        ok = request.app[K_SOURCES].set_enabled(str(data.get("url", "")), bool(data.get("enabled")))
    except ValueError as exc:
        return jerr(422, str(exc))
    return web.json_response({"ok": ok}, status=200 if ok else 404)


async def remove_source(request: web.Request) -> web.Response:
    try:
        ok = request.app[K_SOURCES].remove(request.query.get("url", ""))
    except ValueError as exc:
        return jerr(422, str(exc))
    return web.json_response({"ok": ok}, status=200 if ok else 404)


async def search(request: web.Request) -> web.Response:
    q = request.query
    return web.json_response(await request.app[K_SOURCES].search(
        q.get("q", "")[:200], q.get("tag", ""), min(int(q.get("limit", 25) or 25), 100)))


async def report(request: web.Request) -> web.Response:
    data = await body(request)
    try:
        res = await request.app[K_SOURCES].post(str(data.get("source", "")), "/v1/reports", {
            "listing": data.get("listing"), "category": data.get("category"),
            "detail": data.get("detail", ""), "contact": data.get("contact", "")})
    except KeyError:
        return jerr(404, "unknown source", "not_found")
    except Exception as exc:
        return jerr(502, str(exc) or type(exc).__name__, "upstream_error")
    return web.json_response(res or {"ok": True})


# -- identity / publishing --------------------------------------------------------

def _key_path(request: web.Request) -> Path:
    return request.app[K_CONFIG_DIR] / "publisher.key"


async def get_identity(request: web.Request) -> web.Response:
    p = _key_path(request)
    return web.json_response({"public_key": Identity.load(p).public_key if p.exists() else None})


async def create_identity(request: web.Request) -> web.Response:
    p = _key_path(request)
    if p.exists():
        return jerr(409, "identity already exists", "exists")
    return web.json_response({"public_key": Identity.load_or_create(p).public_key}, status=201)


def _next_seq(request: web.Request, infohash: str) -> int:
    log = request.app[K_CONFIG_DIR] / "publish_seq.json"
    seqs = json.loads(log.read_text()) if log.exists() else {}
    seqs[infohash] = seqs.get(infohash, -1) + 1
    log.write_text(json.dumps(seqs))
    return seqs[infohash]


async def publish(request: web.Request) -> web.Response:
    """Sign a listing with the local identity; post it to `source` if given, else just return it."""
    data, p = await body(request), _key_path(request)
    if not p.exists():
        return jerr(409, "create an identity first", "no_identity")
    ident = Identity.load(p)
    ih = str(data.get("infohash", "")).lower()
    try:
        doc = sign_listing(ident, infohash=ih, title=str(data.get("title", "")),
                           description=str(data.get("description", "")), tags=list(data.get("tags", [])),
                           license=str(data.get("license", "")), price=data.get("price"),
                           withdrawn=bool(data.get("withdrawn")),
                           seq=int(data["seq"]) if "seq" in data else _next_seq(request, ih))
    except (ProtocolError, TypeError, ValueError) as exc:
        return jerr(422, str(exc), "invalid_listing")
    result = None
    if data.get("source"):
        try:
            result = await request.app[K_SOURCES].post(str(data["source"]), "/v1/listings", doc)
        except KeyError:
            return jerr(404, "unknown source", "not_found")
        except Exception as exc:
            return jerr(502, str(exc) or type(exc).__name__, "upstream_error")
    return web.json_response({"listing": doc, "id": listing_id(doc), "published": result}, status=201)


async def rate(request: web.Request) -> web.Response:
    data, p = await body(request), _key_path(request)
    if not p.exists():
        return jerr(409, "create an identity first", "no_identity")
    try:
        doc = sign_rating(Identity.load(p), str(data.get("listing", "")), int(data.get("score", 0)))
        res = await request.app[K_SOURCES].post(str(data.get("source", "")), "/v1/ratings", doc)
    except (ProtocolError, ValueError) as exc:
        return jerr(422, str(exc), "invalid_rating")
    except KeyError:
        return jerr(404, "unknown source", "not_found")
    except Exception as exc:
        return jerr(502, str(exc) or type(exc).__name__, "upstream_error")
    return web.json_response(res or {"ok": True})


# -- app factory -------------------------------------------------------------------

def make_app(*, settings: Settings, config_dir: Path, engine: Engine, token: str,
             ui_dir: Path | None = None, extra_hosts: set[str] | None = None) -> web.Application:
    app = web.Application(middlewares=[security], client_max_size=8 * 1024 * 1024)
    settings_path = config_dir / "settings.json"
    app[K_SETTINGS], app[K_SETTINGS_PATH], app[K_ENGINE], app[K_TOKEN] = settings, settings_path, engine, token
    app[K_CONFIG_DIR] = config_dir
    app[K_HOSTS] = {"127.0.0.1", "localhost", "::1"} | (extra_hosts or set())
    app[K_SOURCES] = Sources(settings, lambda: settings.save(settings_path))
    app[K_STREAMER] = Streamer(engine)
    app[K_SEED] = SeedStaging(engine)
    app.add_routes([
        web.get("/api/status", status),
        web.get("/api/settings", get_settings), web.put("/api/settings", put_settings),
        web.get("/api/torrents", list_torrents), web.post("/api/torrents", add_torrent),
        web.post("/api/create", create_torrent),
        web.get("/api/torrents/{key}", get_torrent),
        web.post("/api/torrents/{key}/{action:pause|resume}", torrent_action),
        web.delete("/api/torrents/{key}", delete_torrent),
        web.post("/api/torrents/{key}/peers", add_peer),
        web.get("/api/torrents/{key}/torrent", download_torrent_file),
        web.post("/api/seed/prepare", seed_prepare),
        web.put("/api/seed/{key}/files/{index:\\d+}", seed_put),
        web.post("/api/seed/{key}/finish", seed_finish),
        web.delete("/api/seed/{key}", seed_cancel),
        web.put("/api/torrents/{key}/files/{index:\\d+}/priority", file_priority),
        web.get("/api/sources", list_sources), web.post("/api/sources", add_source),
        web.put("/api/sources", update_source), web.delete("/api/sources", remove_source),
        web.get("/api/search", search), web.post("/api/report", report), web.post("/api/rate", rate),
        web.get("/api/identity", get_identity), web.post("/api/identity", create_identity),
        web.post("/api/publish", publish),
        web.route("*", "/stream/{key}/{index}", stream),
    ])
    if ui_dir and (ui_dir / "index.html").exists():
        async def index(_: web.Request) -> web.FileResponse:
            return web.FileResponse(ui_dir / "index.html")
        app.router.add_get("/", index)
        if (ui_dir / "assets").is_dir():
            app.router.add_static("/assets", ui_dir / "assets")
    else:
        async def hello(_: web.Request) -> web.Response:
            return web.json_response({"swarm": __version__, "ui": "not built; see ui/README.md"})
        app.router.add_get("/", hello)
    app.on_startup.append(lambda a: a[K_ENGINE].start())
    app.on_cleanup.append(lambda a: a[K_ENGINE].stop())
    return app
