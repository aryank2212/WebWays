"""Signed listings and ratings (spec: docs/listing-spec.md)."""
from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

from .errors import ProtocolError
from .keys import Identity, b64u_decode, verify

VERSION = 1
LISTING_DOMAIN = b"swarm-listing-v1\x00"
RATING_DOMAIN = b"swarm-rating-v1\x00"
MAX_FUTURE_SKEW = 24 * 3600

_HEX_V1 = re.compile(r"^[0-9a-f]{40}$")
_HEX_V2 = re.compile(r"^[0-9a-f]{64}$")
_TAG = re.compile(r"^[a-z0-9][a-z0-9._+-]{0,31}$")
_CURRENCY = re.compile(r"^[A-Z]{3,5}$")
_LICENSE = re.compile(r"^[A-Za-z0-9.+:_-]{1,64}$")

_REQUIRED = {"v", "infohash", "title", "description", "tags", "license", "publisher", "created", "seq", "sig"}
_OPTIONAL = {"price", "withdrawn"}
_RATING_FIELDS = {"v", "listing", "rater", "score", "created", "sig"}


def canonical(obj: dict[str, Any]) -> bytes:
    """Deterministic JSON: sorted keys, no whitespace, UTF-8, no floats."""
    def check(x: Any) -> None:
        if isinstance(x, float):
            raise ProtocolError("floats are not allowed")
        if isinstance(x, dict):
            for k, v in x.items():
                if not isinstance(k, str):
                    raise ProtocolError("keys must be strings")
                check(v)
        elif isinstance(x, list):
            for v in x:
                check(v)
    check(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _unsigned(doc: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in doc.items() if k != "sig"}


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _str(doc: dict, key: str, lo: int, hi: int) -> str:
    val = doc[key]
    if not isinstance(val, str) or not lo <= len(val) <= hi:
        raise ProtocolError(f"{key} must be a string of {lo}-{hi} chars")
    if any(ord(c) < 32 and c not in "\n\t" for c in val):
        raise ProtocolError(f"{key} contains control characters")
    return val


def validate_listing(doc: Any, *, now: float | None = None) -> None:
    """Structural validation only; call verify_listing for the signature."""
    if not isinstance(doc, dict):
        raise ProtocolError("listing must be an object")
    keys = set(doc)
    if not _REQUIRED <= keys or keys - _REQUIRED - _OPTIONAL:
        raise ProtocolError("unexpected or missing fields")
    if doc["v"] != VERSION or isinstance(doc["v"], bool):
        raise ProtocolError("unsupported version")
    ih = doc["infohash"]
    if not (isinstance(ih, str) and (_HEX_V1.match(ih) or _HEX_V2.match(ih))):
        raise ProtocolError("infohash must be 40 (v1) or 64 (v2) lowercase hex chars")
    _str(doc, "title", 1, 200)
    _str(doc, "description", 0, 4000)
    tags = doc["tags"]
    if not isinstance(tags, list) or len(tags) > 16 or len(set(tags)) != len(tags):
        raise ProtocolError("tags must be a list of up to 16 unique tags")
    if not all(isinstance(t, str) and _TAG.match(t) for t in tags):
        raise ProtocolError("invalid tag")
    if not isinstance(doc["license"], str) or not _LICENSE.match(doc["license"]):
        raise ProtocolError("license must be an SPDX id or LicenseRef-*/custom tag")
    if len(b64u_decode(doc["publisher"])) != 32:
        raise ProtocolError("publisher must be a 32-byte ed25519 key")
    if not _is_int(doc["created"]) or doc["created"] < 0:
        raise ProtocolError("created must be a unix timestamp")
    if doc["created"] > (now if now is not None else time.time()) + MAX_FUTURE_SKEW:
        raise ProtocolError("created is too far in the future")
    if not _is_int(doc["seq"]) or not 0 <= doc["seq"] < 2**31:
        raise ProtocolError("seq must be a non-negative integer")
    if "price" in doc:
        p = doc["price"]
        if not (isinstance(p, dict) and set(p) == {"amount", "currency"}):
            raise ProtocolError("price must be {amount, currency}")
        if not _is_int(p["amount"]) or not 0 <= p["amount"] < 10**12:
            raise ProtocolError("price.amount must be an integer in minor units")
        if not isinstance(p["currency"], str) or not _CURRENCY.match(p["currency"]):
            raise ProtocolError("price.currency must be an uppercase code")
    if "withdrawn" in doc and doc["withdrawn"] is not True:
        raise ProtocolError("withdrawn, when present, must be true")


def listing_id(doc: dict[str, Any]) -> str:
    """Stable id = sha256 over the signed bytes (so any edit yields a new id)."""
    return hashlib.sha256(LISTING_DOMAIN + canonical(_unsigned(doc))).hexdigest()


def sign_listing(identity: Identity, *, infohash: str, title: str, description: str = "",
                 tags: list[str] | None = None, license: str, seq: int = 0,
                 price: dict | None = None, withdrawn: bool = False,
                 created: int | None = None) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "v": VERSION,
        "infohash": infohash.lower(),
        "title": title,
        "description": description,
        "tags": sorted(set(tags or [])),
        "license": license,
        "publisher": identity.public_key,
        "created": int(time.time()) if created is None else created,
        "seq": seq,
    }
    if price is not None:
        doc["price"] = price
    if withdrawn:
        doc["withdrawn"] = True
    doc["sig"] = identity.sign(LISTING_DOMAIN + canonical(doc))
    validate_listing(doc)
    return doc


def verify_listing(doc: Any, *, now: float | None = None) -> str:
    """Validate and verify a listing. Returns its id; raises ProtocolError."""
    validate_listing(doc, now=now)
    verify(doc["publisher"], doc["sig"], LISTING_DOMAIN + canonical(_unsigned(doc)))
    return listing_id(doc)


def supersedes(new: dict[str, Any], old: dict[str, Any]) -> bool:
    """Same (publisher, infohash): higher seq wins, created breaks ties."""
    return (new["seq"], new["created"]) > (old["seq"], old["created"])


# --- ratings ---------------------------------------------------------------

def sign_rating(identity: Identity, listing: str, score: int, created: int | None = None) -> dict[str, Any]:
    doc = {"v": VERSION, "listing": listing, "rater": identity.public_key, "score": score,
           "created": int(time.time()) if created is None else created}
    doc["sig"] = identity.sign(RATING_DOMAIN + canonical(doc))
    verify_rating(doc)
    return doc


def verify_rating(doc: Any) -> None:
    if not isinstance(doc, dict) or set(doc) != _RATING_FIELDS or doc["v"] != VERSION:
        raise ProtocolError("malformed rating")
    if not (isinstance(doc["listing"], str) and _HEX_V2.match(doc["listing"])):
        raise ProtocolError("rating.listing must be a listing id")
    if not _is_int(doc["score"]) or not 1 <= doc["score"] <= 5:
        raise ProtocolError("score must be 1-5")
    if not _is_int(doc["created"]) or doc["created"] < 0:
        raise ProtocolError("bad created")
    verify(doc["rater"], doc["sig"], RATING_DOMAIN + canonical(_unsigned(doc)))
