"""webways-indexer serve --db index.db [--config node.toml]"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import tomllib

from aiohttp import web

from .app import make_app
from .db import Store
from .federation import run_forever
from .policy import Policy


def load_policy(path: str | None) -> Policy:
    if not path:
        return Policy()
    with open(path, "rb") as fh:
        cfg = tomllib.load(fh)
    pol = Policy()
    for key, val in cfg.items():
        if not hasattr(pol, key):
            raise SystemExit(f"unknown config key: {key}")
        setattr(pol, key, set(val) if key == "allowed_publishers" else val)
    return pol


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="webways-indexer")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--db", default="index.db")
    s.add_argument("--config", help="TOML policy file")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8780)
    s.add_argument("--peer", action="append", default=[], help="URL of a node to pull listings from (repeatable)")
    s.add_argument("--blocklist", action="append", default=[], help="URL of a node whose blocklist to follow (repeatable)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    policy = load_policy(args.config)
    policy.peers += args.peer
    policy.blocklist_subscriptions += args.blocklist
    # The admin token comes from the environment so it never lands in shell history or `ps`.
    token = os.environ.get("WEBWAYS_ADMIN_TOKEN", "")
    if not token:
        logging.warning("WEBWAYS_ADMIN_TOKEN not set: takedown/verification endpoints are disabled")

    async def start(app: web.Application):
        task = asyncio.create_task(run_forever(app["store_"], policy))
        yield
        task.cancel()

    store = Store(args.db)
    app = make_app(store, policy, token)
    app["store_"] = store
    app.cleanup_ctx.append(start)
    web.run_app(app, host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
