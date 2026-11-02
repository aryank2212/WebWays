"""webways-core serve | token"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from aiohttp import web

from .api import make_app
from .config import Settings, default_config_dir, load_token
from .engine import Engine


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="webways-core")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("token", help="print the local API token")
    s = sub.add_parser("serve", help="run the daemon")
    s.add_argument("--host", default="127.0.0.1", help="bind address (default: loopback only)")
    s.add_argument("--port", type=int, default=8781)
    s.add_argument("--ui-dir", type=Path, default=Path(__file__).resolve().parents[2] / "ui" / "dist")
    s.add_argument("--allow-host", action="append", default=[],
                   help="extra Host name to answer to when served behind a reverse proxy (repeatable)")
    args = ap.parse_args(argv)

    config_dir = default_config_dir()
    token = load_token(config_dir)
    if args.cmd == "token":
        print(token)
        return
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    settings_path = config_dir / "settings.json"
    settings = Settings.load(settings_path)
    settings.validate()
    engine = Engine(settings, config_dir / "state")
    app = make_app(settings=settings, config_dir=config_dir, engine=engine, token=token,
                   ui_dir=args.ui_dir, extra_hosts=set(args.allow_host))
    shown = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    print(f"webways-core listening on http://{args.host}:{args.port}\nopen: http://{shown}:{args.port}/#token={token}", flush=True)
    web.run_app(app, host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
