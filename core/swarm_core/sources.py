"""Index sources: user-managed list of federated index nodes, queried client-side.

Nothing a node returns is trusted: every listing is re-verified here, and node-supplied
fields (ratings, verified badges) are shown as claims attributed to that node.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

import aiohttp

from swarm_protocol import ProtocolError, listing_id, supersedes, verify_listing

from .config import Settings, normalize_source_url

MAX_RESPONSE = 2 * 1024 * 1024
TIMEOUT = aiohttp.ClientTimeout(total=8)


async def _fetch(session: aiohttp.ClientSession, method: str, url: str, **kw) -> Any:
    async with session.request(method, url, **kw) as resp:
        raw = await resp.content.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ValueError("response too large")
        try:
            body = json.loads(raw)
        except ValueError:
            body = None
        if resp.status >= 400:
            msg = (body or {}).get("error", {}).get("message") if isinstance(body, dict) else None
            raise ValueError(msg or f"HTTP {resp.status}")
        return body


class Sources:
    def __init__(self, settings: Settings, persist: Callable[[], None], session_factory=None):
        self.settings, self.persist = settings, persist
        self._session_factory = session_factory or (lambda: aiohttp.ClientSession(timeout=TIMEOUT))

    def list(self) -> list[dict]:
        return [dict(s) for s in self.settings.sources]

    async def add(self, url: str, name: str = "") -> dict:
        url = normalize_source_url(url)
        if any(s["url"] == url for s in self.settings.sources):
            raise ValueError("source already added")
        async with self._session_factory() as session:
            info = await _fetch(session, "GET", f"{url}/v1/node")
        if not isinstance(info, dict) or info.get("software") != "swarm-indexer":
            raise ValueError("that URL is not a swarm index node")
        entry = {"url": url, "name": (name or info.get("name") or url)[:80], "enabled": True,
                 "takedown_contact": str(info.get("takedown_contact", ""))[:200]}
        self.settings.sources.append(entry)
        self.persist()
        return entry

    def remove(self, url: str) -> bool:
        url = normalize_source_url(url)
        before = len(self.settings.sources)
        self.settings.sources = [s for s in self.settings.sources if s["url"] != url]
        self.persist()
        return len(self.settings.sources) != before

    def set_enabled(self, url: str, enabled: bool) -> bool:
        for s in self.settings.sources:
            if s["url"] == normalize_source_url(url):
                s["enabled"] = bool(enabled)
                self.persist()
                return True
        return False

    def find(self, url: str) -> dict:
        url = normalize_source_url(url)
        for s in self.settings.sources:
            if s["url"] == url:
                return s
        raise KeyError(url)

    async def search(self, q: str, tag: str = "", limit: int = 25) -> dict:
        sources = [s for s in self.settings.sources if s.get("enabled", True)]
        params = {"q": q, "limit": str(min(limit, 100))}
        if tag:
            params["tag"] = tag
        async with self._session_factory() as session:
            results = await asyncio.gather(
                *(_fetch(session, "GET", f"{s['url']}/v1/listings", params=params) for s in sources),
                return_exceptions=True)
        merged: dict[tuple[str, str], dict] = {}
        errors: dict[str, str] = {}
        for src, res in zip(sources, results):
            if isinstance(res, BaseException):
                errors[src["url"]] = str(res) or type(res).__name__
                continue
            for item in (res or {}).get("items", []) if isinstance(res, dict) else []:
                try:
                    doc = item["listing"]
                    verify_listing(doc)
                except (ProtocolError, KeyError, TypeError):
                    continue                      # forged or malformed: silently dropped
                k = (doc["publisher"], doc["infohash"])
                entry = merged.get(k)
                if entry is None or supersedes(doc, entry["listing"]):
                    entry = merged[k] = {"id": listing_id(doc), "listing": doc, "sources": [], "verified_by": [],
                                         "rating": None}
                elif listing_id(doc) != entry["id"]:
                    continue                      # an older revision from a lagging node
                entry["sources"].append({"name": src["name"], "url": src["url"]})
                ver = item.get("verified")
                if isinstance(ver, dict) and ver.get("name"):
                    entry["verified_by"].append({"node": src["name"], "name": str(ver["name"])[:100]})
                rating = item.get("rating")
                if isinstance(rating, dict) and rating.get("count") and entry["rating"] is None:
                    entry["rating"] = {"average": rating.get("average"), "count": rating.get("count"),
                                       "node": src["name"]}
        return {"items": [e for e in merged.values() if not e["listing"].get("withdrawn")], "errors": errors}

    async def post(self, source_url: str, path: str, body: dict) -> Any:
        src = self.find(source_url)
        async with self._session_factory() as session:
            return await _fetch(session, "POST", f"{src['url']}{path}", json=body)
