# Index node API

Base: whatever the operator serves (default `http://127.0.0.1:8780`). Errors:
`{"error": {"code", "message"}}`. Read endpoints are public and send `Access-Control-Allow-Origin: *`.
POSTs are rate limited per client IP (default 30/min; admin calls exempt). Bodies are capped at 64 KiB.

## Public

| call | notes |
|---|---|
| `GET /v1/node` | `{software: "webways-indexer", protocol, name, description, takedown_contact, open_publish, stats}` |
| `POST /v1/listings` | a signed listing ([spec](listing-spec.md)). `201` new, `200` updated/stale, `422` invalid, `403` blocked or publisher not allowed, `429` quota |
| `GET /v1/listings?q=&tag=&license=&publisher=&infohash=&limit=&offset=` | full-text search (FTS5; user input is tokenised and quoted, never passed as query syntax). `limit` ≤ 100 |
| `GET /v1/listings/{id}` | one listing + rating aggregate + verified badge. `404` for unknown or withdrawn |
| `GET /v1/sync?since=<cursor>&limit=` | change feed for peers: listings in insertion order, **including withdrawals**; returns `{items, next}` |
| `GET /v1/blocklist?since=` | this operator's *own* takedown decisions `{entries: [{kind, value, reason, created}], next}` |
| `POST /v1/reports` | `{listing, category, detail?, contact?}` |
| `POST /v1/ratings` | signed rating; one per key per listing |

Result items: `{id, listing, received_at, rating: {average, count}, verified: {name, note} | null}`.

## Operator (`Authorization: Bearer $WEBWAYS_ADMIN_TOKEN`)

Disabled (`404`) when the token isn't set.

| call | body |
|---|---|
| `POST /v1/admin/takedown` | `{kind: infohash\|listing\|publisher, value, reason?, notice_ref?}` → `{removed: n}`. Deletes, blocks, logs |
| `POST /v1/admin/unblock` | `{kind, value}` |
| `GET /v1/admin/takedowns` | audit log |
| `GET /v1/admin/reports[?all=1]` · `POST /v1/admin/reports/{id}/resolve` | user reports |
| `POST /v1/admin/verify` | `{publisher, name, note?}` or `{publisher, revoke: true}` |

See [operators.md](operators.md) for policy and moderation semantics.
