"""End-to-end smoke test with real processes: indexer + publisher daemon + client daemon.

    .venv/bin/python scripts/e2e.py [--keep]     (--keep leaves the stack running for the UI check)

Uses a private temp dir and loopback only; DHT/UPnP are irrelevant because peers are added by hand.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
KEEP = "--keep" in sys.argv


def http(method, url, token=None, body=None, headers=None):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read(), r.headers


def j(*a, **k):
    status, raw, _ = http(*a, **k)
    return json.loads(raw)


def wait_up(url, timeout=20):
    t = time.time()
    while time.time() - t < timeout:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except urllib.error.HTTPError:
            return
        except Exception:
            time.sleep(0.2)
    raise SystemExit(f"{url} did not come up")


def main():
    tmp = Path(tempfile.mkdtemp(prefix="webways-e2e-"))
    env = {**os.environ, "PYTHONPATH": ":".join(str(ROOT / d) for d in ("protocol", "indexer", "core")),
           "PYTHONWARNINGS": "ignore"}
    procs = []

    def spawn(*args, **extra):
        p = subprocess.Popen([PY, "-m", *args], env={**env, **extra}, stdout=open(tmp / f"{args[0]}-{len(procs)}.log", "w"),
                             stderr=subprocess.STDOUT)
        procs.append(p)
        return p

    try:
        spawn("webways_indexer", "serve", "--db", str(tmp / "idx.db"), "--port", "18780", WEBWAYS_ADMIN_TOKEN="adm")
        for name, port, listen in (("pub", 18782, 16891), ("cli", 18781, 16881)):
            cfg = tmp / name
            cfg.mkdir()
            (cfg / "settings.json").write_text(json.dumps({"download_dir": str(tmp / f"{name}-dl"), "listen_port": listen}))
            (cfg / "token").write_text(f"tok-{name}\n")
            os.chmod(cfg / "token", 0o600)
            spawn("webways_core", "serve", "--port", str(port), WEBWAYS_CONFIG_DIR=str(cfg))
        for u in ("http://127.0.0.1:18780/v1/node", "http://127.0.0.1:18781/", "http://127.0.0.1:18782/"):
            wait_up(u)
        PUB, CLI, IDX = "http://127.0.0.1:18782", "http://127.0.0.1:18781", "http://127.0.0.1:18780"
        tp, tc = "tok-pub", "tok-cli"

        movie = tmp / "film.mp4"
        movie.write_bytes(os.urandom(5_000_000))

        print("publisher: create torrent, identity, sources, publish")
        t = j("POST", f"{PUB}/api/create", tp, {"path": str(movie)})
        key = t["infohash"]
        j("POST", f"{PUB}/api/sources", tp, {"url": IDX})
        j("POST", f"{PUB}/api/identity", tp)
        j("POST", f"{PUB}/api/publish", tp, {"infohash": key, "title": "Open Film", "description": "random bytes",
                                            "tags": ["demo", "film"], "license": "CC0-1.0", "source": IDX})

        print("client: fresh (no sources), add source, search, stream")
        assert j("GET", f"{CLI}/api/sources", tc)["sources"] == []
        j("POST", f"{CLI}/api/sources", tc, {"url": IDX})
        items = j("GET", f"{CLI}/api/search?q=film", tc)["items"]
        assert [i["listing"]["title"] for i in items] == ["Open Film"], items
        j("POST", f"{CLI}/api/torrents", tc, {"infohash": items[0]["listing"]["infohash"]})
        j("POST", f"{CLI}/api/torrents/{key}/peers", tc, {"host": "127.0.0.1", "port": 16891})
        for _ in range(100):
            info = j("GET", f"{CLI}/api/torrents/{key}", tc)
            if info["files"]:
                break
            time.sleep(0.2)
        url = CLI + info["files"][0]["stream_url"]
        status, body, hdr = http("GET", url, headers={"Range": "bytes=2000000-2000999"})
        assert status == 206 and body == movie.read_bytes()[2000000:2001000], "range bytes differ"
        print(f"  206 OK, {len(body)} bytes match; progress {info['progress']:.2f}")
        for _ in range(100):
            if j("GET", f"{CLI}/api/torrents/{key}", tc)["state"] in ("seeding", "finished"):
                break
            time.sleep(0.3)
        got = next((tmp / "cli-dl").rglob("film.mp4"))
        assert got.read_bytes() == movie.read_bytes(), "downloaded file differs"
        print("  full download matches source")

        if not KEEP:
            print("operator: takedown, then client no longer finds it")
            j("POST", f"{IDX}/v1/admin/takedown", "adm", {"kind": "infohash", "value": key, "reason": "e2e", "notice_ref": "T-1"})
            assert j("GET", f"{CLI}/api/search?q=film", tc)["items"] == []
        print("E2E PASS")
        if KEEP:
            print(f"kept running; tmp={tmp}; client UI: {CLI}/#token={tc}")
            (tmp / "pids").write_text(" ".join(str(p.pid) for p in procs))
            procs.clear()
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(10)
            except Exception:
                p.kill()
        if not KEEP:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
