"""Pull-based federation: listings and (optionally) blocklists from operator-chosen URLs.

Everything a peer sends is re-verified locally and filtered through *this* node's
policy and blocklist; a peer is never trusted for anything but availability.
"""
from __future__ import annotations

import asyncio
import logging
import re

import aiohttp

from swarm_protocol import ProtocolError, verify_listing

from .db import Rejected, Store
from .policy import Policy

log = logging.getLogger("swarm.federation")
_HEX = re.compile(r"^[0-9a-f]{40}$|^[0-9a-f]{64}$")
_B64U = re.compile(r"^[A-Za-z0-9_-]{43}$")
_OK_VALUE = {"infohash": _HEX, "listing": re.compile(r"^[0-9a-f]{64}$"), "publisher": _B64U}
MAX_RESPONSE = 4 * 1024 * 1024
MAX_PAGES = 50


async def _get_json(session: aiohttp.ClientSession, url: str) -> dict:
    async with session.get(url) as resp:
        resp.raise_for_status()
        raw = await resp.content.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ValueError("response too large")
        import json
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("expected JSON object")
        return data


async def sync_peer(store: Store, policy: Policy, session: aiohttp.ClientSession, peer: str) -> dict:
    base = peer.rstrip("/")
    stats = {"inserted": 0, "updated": 0, "rejected": 0}
    cursor = store.get_cursor(base)
    for _ in range(MAX_PAGES):
        page = await _get_json(session, f"{base}/v1/sync?since={cursor}&limit=200")
        items, nxt = page.get("items"), page.get("next")
        if not isinstance(items, list) or not isinstance(nxt, int):
            raise ValueError("malformed sync page")
        for doc in items:
            try:
                lid = verify_listing(doc)
                if not policy.open_publish and doc["publisher"] not in policy.allowed_publishers:
                    raise Rejected("publisher_not_allowed", "")
                res = store.upsert(doc, lid, max_per_publisher=policy.max_listings_per_publisher)
                if res in stats:
                    stats[res] += 1
            except (ProtocolError, Rejected, TypeError, KeyError):
                stats["rejected"] += 1
        if nxt <= cursor or not items:
            break
        cursor = nxt
        store.set_cursor(base, cursor)
    return stats


async def sync_blocklist(store: Store, session: aiohttp.ClientSession, url: str) -> int:
    base = url.rstrip("/")
    entries, since = [], 0
    for _ in range(MAX_PAGES):
        page = await _get_json(session, f"{base}/v1/blocklist?since={since}")
        batch = page.get("entries")
        if not isinstance(batch, list):
            raise ValueError("malformed blocklist page")
        for e in batch:
            if isinstance(e, dict) and e.get("kind") in _OK_VALUE and isinstance(e.get("value"), str) \
                    and _OK_VALUE[e["kind"]].match(e["value"]):
                entries.append({"kind": e["kind"], "value": e["value"], "reason": str(e.get("reason", ""))[:200]})
        if not batch or not isinstance(page.get("next"), int) or page["next"] <= since:
            break
        since = page["next"]
    store.replace_subscription(base, entries)
    return len(entries)


async def run_forever(store: Store, policy: Policy) -> None:
    if not (policy.peers or policy.blocklist_subscriptions):
        return
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        while True:
            # Blocklists first, so a freshly blocked item is never re-imported from a peer.
            for url in policy.blocklist_subscriptions:
                try:
                    log.info("blocklist %s: %d entries", url, await sync_blocklist(store, session, url))
                except Exception as exc:
                    log.warning("blocklist %s failed: %s", url, exc)
            for peer in policy.peers:
                try:
                    log.info("peer %s: %s", peer, await sync_peer(store, policy, session, peer))
                except Exception as exc:
                    log.warning("peer %s failed: %s", peer, exc)
            await asyncio.sleep(policy.sync_interval)
