# Running an index node

An index node stores signed listings, answers searches, and (optionally) pulls from other nodes.
**The project ships software, not an index.** A fresh node is empty, has no peers and subscribes to
no blocklist; the operator decides everything below.

```
export SWARM_ADMIN_TOKEN="$(openssl rand -hex 24)"     # admin API is disabled without it
PYTHONPATH=protocol:indexer .venv/bin/python -m swarm_indexer serve \
    --db index.db --config node.toml [--peer https://other.example] [--blocklist https://other.example]
```

Put it behind a TLS reverse proxy for public use. The node binds to loopback by default.

## `node.toml`

```toml
name = "Example Index"
description = "Public-domain and CC-licensed video"
takedown_contact = "abuse@example.org"      # shown in /v1/node and in every client's Sources tab
open_publish = false                        # true: any signed publisher may list; false: allow-list only
allowed_publishers = ["<base64url key>"]
max_listings_per_publisher = 1000
peers = []                                  # nodes to pull listings from
blocklist_subscriptions = []                # nodes whose takedown decisions you follow
sync_interval = 300
```

## Moderation tools

Everything under `/v1/admin/*` needs `Authorization: Bearer $SWARM_ADMIN_TOKEN`.

| action | call |
|---|---|
| **Takedown** (e.g. a DMCA notice) | `POST /v1/admin/takedown {kind: infohash\|listing\|publisher, value, reason, notice_ref}` |
| Counter-notice / reinstate | `POST /v1/admin/unblock {kind, value}` (listing must then be re-published) |
| Audit trail | `GET /v1/admin/takedowns` |
| Reports from users | `GET /v1/admin/reports`, `POST /v1/admin/reports/{id}/resolve` |
| Verified-publisher badge | `POST /v1/admin/verify {publisher, name, note}` or `{publisher, revoke: true}` |

A takedown **deletes** the matching listings, **blocks** the infohash/listing/publisher so it cannot be
re-listed here or arrive through federation, and writes an audit row. Blocking by `infohash` stops
the same torrent being re-listed under a different publisher key.

## Blocklists

`GET /v1/blocklist` publishes this operator's *own* decisions (entries received from subscriptions are
not re-broadcast, so errors don't cascade). Subscribing is pull-based: the subscriber mirrors the
source's list exactly. If the source lifts an entry, the subscriber's copy is lifted too. A local
takedown always takes ownership of an entry, so unsubscribing never silently unblocks something you
blocked yourself.

## Federation

Peers are pulled over `GET /v1/sync?since=<cursor>`. Every listing is re-verified locally and run
through *this* node's allow-list, quotas and blocklist. A hostile or buggy peer can waste bandwidth;
it cannot inject forged or blocked content.

## Limits worth knowing

- Takedown removes the *listing*; it can't remove data from the BitTorrent swarm.
- The sync feed has no auth: anything a node holds, it will hand to any peer. Don't store anything
  you wouldn't publish.
- Rate limiting is per client IP, in memory. Behind a reverse proxy, apply limits there as well.
- Not a legal service: have a process for notices and counter-notices, and get advice for your
  jurisdiction before running a public node.
