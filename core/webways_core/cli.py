"""webways-core serve | token"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import urllib.request
import webbrowser
from pathlib import Path

from aiohttp import web

from .api import make_app
from . import __version__
from .config import Settings, default_config_dir, default_ui_dir, load_token
from .engine import Engine


def already_running(host: str, port: int, token: str) -> bool:
    """True if a WebWays daemon with this token is already answering on host:port."""
    req = urllib.request.Request(f"http://{host}:{port}/api/status", headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def app_main() -> None:
    """Entry point for double-click use (`webways`, WebWays.exe): serve and open the browser."""
    main(["serve", "--open", *sys.argv[1:]])


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="webways-core")
    ap.add_argument("--version", action="version", version=f"webways-core {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("token", help="print the local API token")
    s = sub.add_parser("serve", help="run the daemon")
    s.add_argument("--host", default="127.0.0.1", help="bind address (default: loopback only)")
    s.add_argument("--port", type=int, default=8781)
    s.add_argument("--ui-dir", type=Path, default=default_ui_dir())
    s.add_argument("--allow-host", action="append", default=[],
                   help="extra Host name to answer to when served behind a reverse proxy (repeatable)")
    s.add_argument("--open", action="store_true", help="open the UI in your browser once the daemon is up")
    args = ap.parse_args(argv)

    config_dir = default_config_dir()
    token = load_token(config_dir)
    if args.cmd == "token":
        print(token)
        return
    shown = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    url = f"http://{shown}:{args.port}/#token={token}"
    if args.open and already_running(shown, args.port, token):      # before building an engine: no second session
        print("WebWays is already running; opening it.", flush=True)
        webbrowser.open(url)
        return
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    settings_path = config_dir / "settings.json"
    settings = Settings.load(settings_path)
    settings.validate()
    engine = Engine(settings, config_dir / "state")
    app = make_app(settings=settings, config_dir=config_dir, engine=engine, token=token,
                   ui_dir=args.ui_dir, extra_hosts=set(args.allow_host))
    if args.open:
        async def open_browser(_: web.Application) -> None:
            # on_startup runs just before the socket opens, so give the server a moment first
            asyncio.get_running_loop().call_later(1.0, webbrowser.open, url)
        app.on_startup.append(open_browser)
    print(f"webways-core listening on http://{args.host}:{args.port}\nopen: {url}", flush=True)
    try:
        web.run_app(app, host=args.host, port=args.port, print=None)
    except OSError as exc:
        raise SystemExit(f"Cannot listen on {args.host}:{args.port}: {exc.strerror or exc}. "
                         "Is another program using that port? Try --port 8782.")


if __name__ == "__main__":
    main()
