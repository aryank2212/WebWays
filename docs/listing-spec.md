# Listing specification (v1)

A **listing** is a small JSON object, signed by its publisher, that points at a torrent by infohash.
Nodes and clients store and forward listings; they never need to trust the party that delivered one,
because the signature binds every field to the publisher's key.

## Fields

| field | type | rules |
|---|---|---|
| `v` | int | must be `1` |
| `infohash` | string | 40 lowercase hex (BitTorrent v1) or 64 (v2) |
| `title` | string | 1–200 chars, no control characters |
| `description` | string | 0–4000 chars |
| `tags` | string[] | ≤16 unique; each `[a-z0-9][a-z0-9._+-]{0,31}` |
| `license` | string | SPDX id or `LicenseRef-*`; `[A-Za-z0-9.+:_-]{1,64}` |
| `publisher` | string | base64url (no padding) ed25519 public key, 32 bytes |
| `created` | int | unix seconds; rejected if >24 h in the future |
| `seq` | int | 0 ≤ seq < 2³¹; revision counter |
| `price` | object, optional | `{amount: int (minor units), currency: "USD"}`. Floats are never allowed. |
| `withdrawn` | `true`, optional | tombstone: the publisher retracts the listing |
| `sig` | string | base64url ed25519 signature |

Unknown fields are rejected, so a signature always covers everything a reader will see. New fields
mean a new `v`.

## Signing

```
message = "swarm-listing-v1\0" || canonical(listing without "sig")
sig     = ed25519_sign(publisher_private_key, message)
```

`canonical` is JSON with sorted keys, no whitespace, UTF-8 (not ASCII-escaped), and no floats. The
domain prefix stops a listing signature from being replayed as any other kind of signed object.

`id = sha256(message)` in hex. Any edit yields a new id.

## Revisions and withdrawal

Within one `(publisher, infohash)` pair the listing with the higher `(seq, created)` wins. To retract,
publish a higher `seq` with `"withdrawn": true`. Nodes keep the tombstone so it propagates to peers.
A withdrawal removes the listing from search but cannot remove the torrent itself from the swarm.

## Ratings

```
{v:1, listing:<id>, rater:<pubkey>, score:1..5, created:<int>, sig}
message = "swarm-rating-v1\0" || canonical(rating without "sig")
```

One vote per key per listing (newest wins). A key is free to create, so ratings are weak evidence on
their own; nodes may weight or ignore them by policy.

## What a signature does and doesn't prove

It proves the holder of `publisher`'s key made this listing and nothing was altered. It does **not**
prove the publisher owns the content, that the torrent matches the description, or that the person
is who they claim. "Verified publisher" is a claim an individual node operator makes about a key
(see `docs/operators.md`); clients show it attributed to that node.
