"""SQLite store: listings (+FTS5), blocklist, takedown log, reports, ratings."""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from typing import Any, Iterable

from swarm_protocol import supersedes

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
  ord INTEGER PRIMARY KEY AUTOINCREMENT,   -- also the federation sync cursor
  id TEXT NOT NULL UNIQUE,
  infohash TEXT NOT NULL,
  publisher TEXT NOT NULL,
  license TEXT NOT NULL,
  seq INTEGER NOT NULL,
  created INTEGER NOT NULL,
  withdrawn INTEGER NOT NULL DEFAULT 0,
  received_at INTEGER NOT NULL,
  doc TEXT NOT NULL,
  UNIQUE (publisher, infohash)
);
CREATE INDEX IF NOT EXISTS listings_infohash ON listings(infohash);
CREATE VIRTUAL TABLE IF NOT EXISTS listings_fts USING fts5(title, description, tags, tokenize='unicode61 remove_diacritics 2');
CREATE TABLE IF NOT EXISTS tags (ord INTEGER NOT NULL, tag TEXT NOT NULL, PRIMARY KEY (ord, tag));
CREATE INDEX IF NOT EXISTS tags_tag ON tags(tag);
CREATE TABLE IF NOT EXISTS blocklist (
  ord INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL CHECK (kind IN ('infohash','publisher','listing')),
  value TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT 'local',    -- 'local' or the subscribed URL
  created INTEGER NOT NULL,
  UNIQUE (kind, value)
);
CREATE TABLE IF NOT EXISTS takedowns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at INTEGER NOT NULL, kind TEXT NOT NULL, value TEXT NOT NULL,
  notice_ref TEXT NOT NULL DEFAULT '', reason TEXT NOT NULL DEFAULT '', removed INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  listing TEXT NOT NULL, category TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '',
  contact TEXT NOT NULL DEFAULT '', at INTEGER NOT NULL, resolved INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS ratings (
  listing TEXT NOT NULL, rater TEXT NOT NULL, score INTEGER NOT NULL, created INTEGER NOT NULL,
  PRIMARY KEY (listing, rater)
);
CREATE TABLE IF NOT EXISTS verified (publisher TEXT PRIMARY KEY, name TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS peer_cursor (url TEXT PRIMARY KEY, cursor INTEGER NOT NULL);
"""

REPORT_CATEGORIES = ("copyright", "illegal", "malware", "spam", "other")


class Rejected(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def fts_query(text: str) -> str | None:
    """Turn user input into a safe FTS5 query: AND of quoted prefix tokens."""
    toks = re.findall(r"\w+", text, flags=re.UNICODE)[:12]
    return " ".join(f'"{t}"*' for t in toks) or None


class Store:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA foreign_keys=ON")
            self.db.executescript(SCHEMA)

    # -- blocklist ----------------------------------------------------------
    def block_reason(self, doc: dict, lid: str) -> str | None:
        with self.lock:
            row = self.db.execute(
                "SELECT kind, reason FROM blocklist WHERE (kind='infohash' AND value=?) "
                "OR (kind='publisher' AND value=?) OR (kind='listing' AND value=?) LIMIT 1",
                (doc["infohash"], doc["publisher"], lid)).fetchone()
        return f"blocked {row['kind']}: {row['reason']}".rstrip(": ") if row else None

    def add_block(self, kind: str, value: str, reason: str = "", source: str = "local") -> None:
        with self.lock:
            self.db.execute(
                "INSERT INTO blocklist(kind,value,reason,source,created) VALUES (?,?,?,?,?) "
                "ON CONFLICT(kind,value) DO UPDATE SET reason=excluded.reason, source=excluded.source "
                "WHERE excluded.source='local' OR blocklist.source=excluded.source",
                (kind, value, reason, source, int(time.time())))

    def remove_block(self, kind: str, value: str) -> bool:
        with self.lock:
            return self.db.execute("DELETE FROM blocklist WHERE kind=? AND value=?", (kind, value)).rowcount > 0

    def blocklist(self, *, local_only: bool, since: int = 0, limit: int = 1000) -> list[dict]:
        q = "SELECT ord, kind, value, reason, created, source FROM blocklist WHERE ord>?"
        if local_only:
            q += " AND source='local'"
        with self.lock:
            rows = self.db.execute(q + " ORDER BY ord LIMIT ?", (since, limit)).fetchall()
        return [dict(r) for r in rows]

    def replace_subscription(self, url: str, entries: Iterable[dict]) -> None:
        """Make the stored copy of one subscribed list match what the source now says."""
        keep = set()
        for e in entries:
            self.add_block(e["kind"], e["value"], e.get("reason", ""), source=url)
            keep.add((e["kind"], e["value"]))
            self._purge(e["kind"], e["value"])
        with self.lock:
            for r in self.db.execute("SELECT kind, value FROM blocklist WHERE source=?", (url,)).fetchall():
                if (r["kind"], r["value"]) not in keep:
                    self.remove_block(r["kind"], r["value"])

    # -- listings -----------------------------------------------------------
    def _where(self, kind: str) -> str:
        return {"infohash": "infohash=?", "publisher": "publisher=?", "listing": "id=?"}[kind]

    def _purge(self, kind: str, value: str) -> int:
        with self.lock:
            rows = self.db.execute(f"SELECT ord FROM listings WHERE {self._where(kind)}", (value,)).fetchall()
            for r in rows:
                self._delete_ord(r["ord"])
        return len(rows)

    def _delete_ord(self, ord_: int) -> None:
        self.db.execute("DELETE FROM listings_fts WHERE rowid=?", (ord_,))
        self.db.execute("DELETE FROM tags WHERE ord=?", (ord_,))
        self.db.execute("DELETE FROM listings WHERE ord=?", (ord_,))

    def upsert(self, doc: dict, lid: str, *, max_per_publisher: int) -> str:
        """Insert a *verified* listing. Returns 'inserted' | 'updated' | 'stale'."""
        with self.lock:
            reason = self.block_reason(doc, lid)
            if reason:
                raise Rejected("blocked", reason)
            old = self.db.execute("SELECT ord, doc FROM listings WHERE publisher=? AND infohash=?",
                                  (doc["publisher"], doc["infohash"])).fetchone()
            if old:
                if not supersedes(doc, json.loads(old["doc"])):
                    return "stale"
            else:
                n = self.db.execute("SELECT COUNT(*) FROM listings WHERE publisher=?", (doc["publisher"],)).fetchone()[0]
                if n >= max_per_publisher:
                    raise Rejected("quota", "publisher listing quota reached on this node")
            self.db.execute("BEGIN")
            try:
                if old:
                    self._delete_ord(old["ord"])
                cur = self.db.execute(
                    "INSERT INTO listings(id,infohash,publisher,license,seq,created,withdrawn,received_at,doc) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (lid, doc["infohash"], doc["publisher"], doc["license"], doc["seq"], doc["created"],
                     int(bool(doc.get("withdrawn"))), int(time.time()), json.dumps(doc, ensure_ascii=False)))
                ord_ = cur.lastrowid
                if not doc.get("withdrawn"):
                    self.db.execute("INSERT INTO listings_fts(rowid,title,description,tags) VALUES (?,?,?,?)",
                                    (ord_, doc["title"], doc["description"], " ".join(doc["tags"])))
                    self.db.executemany("INSERT INTO tags(ord,tag) VALUES (?,?)", [(ord_, t) for t in doc["tags"]])
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise
        return "updated" if old else "inserted"

    def _row(self, r: sqlite3.Row) -> dict[str, Any]:
        with self.lock:
            agg = self.db.execute("SELECT AVG(score) a, COUNT(*) n FROM ratings WHERE listing=?", (r["id"],)).fetchone()
            ver = self.db.execute("SELECT name, note FROM verified WHERE publisher=?", (r["publisher"],)).fetchone()
        return {"id": r["id"], "listing": json.loads(r["doc"]), "received_at": r["received_at"],
                "rating": {"average": round(agg["a"], 2) if agg["n"] else None, "count": agg["n"]},
                "verified": dict(ver) if ver else None}

    def get(self, lid: str) -> dict | None:
        with self.lock:
            r = self.db.execute("SELECT * FROM listings WHERE id=? AND withdrawn=0", (lid,)).fetchone()
        return self._row(r) if r else None

    def search(self, q: str = "", *, tag: str | None = None, license: str | None = None,
               publisher: str | None = None, infohash: str | None = None,
               limit: int = 25, offset: int = 0) -> list[dict]:
        limit, offset = max(1, min(limit, 100)), max(0, offset)
        where, args = ["l.withdrawn=0"], []
        join, order = "", "l.received_at DESC"
        if q.strip():
            m = fts_query(q)
            if m is None:
                return []
            join = "JOIN listings_fts f ON f.rowid=l.ord AND listings_fts MATCH ?"
            args.append(m)
            order = "bm25(listings_fts, 10.0, 1.0, 5.0)"
        if tag:
            where.append("EXISTS (SELECT 1 FROM tags t WHERE t.ord=l.ord AND t.tag=?)"); args.append(tag)
        for col, val in (("license", license), ("publisher", publisher), ("infohash", infohash)):
            if val:
                where.append(f"l.{col}=?"); args.append(val)
        sql = f"SELECT l.* FROM listings l {join} WHERE {' AND '.join(where)} ORDER BY {order} LIMIT ? OFFSET ?"
        with self.lock:
            rows = self.db.execute(sql, (*args, limit, offset)).fetchall()
        return [self._row(r) for r in rows]

    def feed(self, since: int, limit: int = 200) -> tuple[list[dict], int]:
        limit = max(1, min(limit, 500))
        with self.lock:
            rows = self.db.execute("SELECT ord, doc FROM listings WHERE ord>? ORDER BY ord LIMIT ?", (since, limit)).fetchall()
        return [json.loads(r["doc"]) for r in rows], (rows[-1]["ord"] if rows else since)

    def stats(self) -> dict:
        with self.lock:
            n = self.db.execute("SELECT COUNT(*) FROM listings WHERE withdrawn=0").fetchone()[0]
            p = self.db.execute("SELECT COUNT(DISTINCT publisher) FROM listings WHERE withdrawn=0").fetchone()[0]
        return {"listings": n, "publishers": p}

    # -- moderation ---------------------------------------------------------
    def takedown(self, kind: str, value: str, *, reason: str, notice_ref: str) -> int:
        """Remove matching listings, remember the block, and keep an audit record."""
        removed = self._purge(kind, value)
        self.add_block(kind, value, reason)
        with self.lock:
            self.db.execute("INSERT INTO takedowns(at,kind,value,notice_ref,reason,removed) VALUES (?,?,?,?,?,?)",
                            (int(time.time()), kind, value, notice_ref, reason, removed))
        return removed

    def takedown_log(self, limit: int = 200) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.db.execute("SELECT * FROM takedowns ORDER BY id DESC LIMIT ?", (limit,))]

    def add_report(self, listing: str, category: str, detail: str, contact: str) -> int:
        with self.lock:
            return self.db.execute("INSERT INTO reports(listing,category,detail,contact,at) VALUES (?,?,?,?,?)",
                                   (listing, category, detail, contact, int(time.time()))).lastrowid

    def reports(self, include_resolved: bool = False, limit: int = 200) -> list[dict]:
        q = "SELECT * FROM reports" + ("" if include_resolved else " WHERE resolved=0") + " ORDER BY id DESC LIMIT ?"
        with self.lock:
            return [dict(r) for r in self.db.execute(q, (limit,))]

    def resolve_report(self, rid: int) -> bool:
        with self.lock:
            return self.db.execute("UPDATE reports SET resolved=1 WHERE id=?", (rid,)).rowcount > 0

    def rate(self, listing: str, rater: str, score: int, created: int) -> bool:
        with self.lock:
            if not self.db.execute("SELECT 1 FROM listings WHERE id=? AND withdrawn=0", (listing,)).fetchone():
                return False
            self.db.execute(
                "INSERT INTO ratings(listing,rater,score,created) VALUES (?,?,?,?) "
                "ON CONFLICT(listing,rater) DO UPDATE SET score=excluded.score, created=excluded.created "
                "WHERE excluded.created>ratings.created", (listing, rater, score, created))
        return True

    def set_verified(self, publisher: str, name: str, note: str = "") -> None:
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO verified(publisher,name,note,at) VALUES (?,?,?,?)",
                            (publisher, name, note, int(time.time())))

    def unset_verified(self, publisher: str) -> bool:
        with self.lock:
            return self.db.execute("DELETE FROM verified WHERE publisher=?", (publisher,)).rowcount > 0

    def get_cursor(self, url: str) -> int:
        with self.lock:
            r = self.db.execute("SELECT cursor FROM peer_cursor WHERE url=?", (url,)).fetchone()
        return r["cursor"] if r else 0

    def set_cursor(self, url: str, cursor: int) -> None:
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO peer_cursor(url,cursor) VALUES (?,?)", (url, cursor))
