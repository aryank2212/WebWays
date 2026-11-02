"""Smoke-test a built WebWays executable:   python scripts/smoke_exe.py path/to/WebWays.exe [--verbose]

Starts the daemon and an index node from the *packaged* app and checks what is most likely to break in a bundle:
the UI is embedded, libtorrent loads and can create/seed a torrent, bytes can be read back while libtorrent has the
file open, and the index node's SQLite has FTS5.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

exe = sys.argv[1]
tmp = Path(tempfile.mkdtemp(prefix="webways-smoke-"))
env = {**os.environ, "WEBWAYS_CONFIG_DIR": str(tmp / "cfg"), "WEBWAYS_ADMIN_TOKEN": "adm"}
procs: list[subprocess.Popen] = []
CORE, IDX = "http://127.0.0.1:18790", "http://127.0.0.1:18791"


def check(cond: bool, msg: str) -> None:
    print(("  ok - " if cond else "FAIL - ") + msg, flush=True)
    if not cond:
        raise SystemExit(1)


def call(url: str, token: str | None = None, body: dict | None = None) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"} if body is not None else {})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read()


def wait(url: str, token: str | None = None, timeout: float = 60) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            call(url, token)
            return
        except Exception:
            time.sleep(0.5)
    raise SystemExit(f"FAIL - {url} did not come up within {timeout}s")


try:
    out = subprocess.run([exe, "--version"], env=env, capture_output=True, text=True, timeout=90)
    check(out.returncode == 0 and "webways-core" in out.stdout, f"--version works: {out.stdout.strip()}")

    procs.append(subprocess.Popen([exe, "serve", "--port", "18790"], env=env,
                                  stdout=open(tmp / "core.log", "w"), stderr=subprocess.STDOUT))
    for _ in range(120):                                  # the token file appears on first start
        if (tmp / "cfg" / "token").exists():
            break
        time.sleep(0.25)
    token = (tmp / "cfg" / "token").read_text().strip()
    wait(CORE + "/api/status", token)
    st, body = call(CORE + "/api/status", token)
    check(st == 200 and json.loads(body)["version"], "daemon API answers")
    st, html = call(CORE + "/")
    check(st == 200 and b"<title>WebWays</title>" in html, "embedded web UI is served at /")
    asset = [a for a in html.decode().split('"') if a.startswith("/assets/") and a.endswith(".js")][0]
    check(call(CORE + asset)[0] == 200, "UI bundle asset is served")

    movie = tmp / "film.bin"
    movie.write_bytes(os.urandom(300_000))
    st, body = call(CORE + "/api/create", token, {"path": str(movie)})
    t = json.loads(body)
    check(st == 201 and len(t["infohash"]) == 40, "libtorrent (packaged) hashes a file into a torrent")
    for _ in range(80):
        t = json.loads(call(CORE + "/api/torrents/" + t["infohash"], token)[1])
        if t["state"] in ("seeding", "finished"):
            break
        time.sleep(0.5)
    check(t["state"] in ("seeding", "finished") and t["progress"] == 1.0, f"torrent verified and seeding ({t['state']})")
    st, got = call(CORE + t["files"][0]["stream_url"])
    check(st == 200 and got == movie.read_bytes(), "streamed bytes equal the source file (read while libtorrent holds it)")

    procs.append(subprocess.Popen([exe, "indexer", "serve", "--db", str(tmp / "idx.db"), "--port", "18791"], env=env,
                                  stdout=open(tmp / "idx.log", "w"), stderr=subprocess.STDOUT))
    wait(IDX + "/v1/node")
    check(json.loads(call(IDX + "/v1/node")[1])["software"] == "webways-indexer", "index node starts from the same exe")
    st, body = call(IDX + "/v1/listings?q=anything")
    check(st == 200 and json.loads(body) == {"items": []}, "index node full-text search works (SQLite FTS5 present)")
    print("SMOKE PASS")
finally:
    for p in procs:
        p.terminate()
    for p in procs:
        try:
            p.wait(15)
        except Exception:
            p.kill()
    if "--verbose" in sys.argv:
        for log in ("core.log", "idx.log"):
            f = tmp / log
            if f.exists():
                print(f"--- {log}\n" + f.read_text(errors="replace")[-3000:])
