# Architecture

```
            ┌────────────────────────── your machine ───────────────────────────┐
 browser ──▶│ ui (React)  ──HTTP──▶  core daemon  ──▶ libtorrent ──▶ BitTorrent  │──▶ swarm
 VLC/mpv ──▶│                        (aiohttp)        DHT · uTP · encryption     │
            └───────────────┬───────────────────────────────────────────────────┘
                            │ HTTPS, only to index sources the user added
                            ▼
               index node A ◀──pull sync──▶ index node B      (run by anyone, each with its own policy)
```

## Components

| dir | role | key modules |
|---|---|---|
| `protocol/` | the shared language: listing/rating validation, canonical JSON, ed25519 sign/verify | `listing.py`, `keys.py` |
| `core/` | daemon. One libtorrent session; local REST API; Range streaming; index-source client; publishing; seed uploads | `engine.py`, `api.py`, `streaming.py`, `sources.py`, `seeding.py`, `config.py` |
| `ui/` | single-page app that only calls the daemon API; also hashes files in the browser for the Create tab | `src/tabs/*`, `src/lib/maker.ts`, `src/api.ts` |
| `indexer/` | index node: SQLite + FTS5, publish/search/sync API, takedown, blocklists, reports, ratings, federation | `db.py`, `app.py`, `federation.py`, `policy.py` |

The daemon imports `protocol` to *verify* listings; the indexer imports it to *accept* them. Neither imports
the other.

## Key flows

**Discover → download.** UI → `GET /api/search` → daemon queries each enabled source in parallel → every returned
listing is re-verified with `protocol` (forged ones are dropped) → merged by `(publisher, infohash)`, newest `seq`
wins → user clicks Download → `POST /api/torrents {infohash}` → libtorrent fetches metadata over DHT → files appear.

**Stream.** `GET /stream/<infohash>/<file>?sig=…` with `Range`. Per read, the streamer sets rising piece
deadlines on the next ~24 MB (`set_piece_deadline`), waits for the pieces covering the requested bytes, reads them
from disk and writes them out. Closing the connection clears the deadlines. No whole-torrent sequential mode.

**Publish.** Daemon signs a listing with `publisher.key` (`POST /api/publish`) and POSTs it to a chosen source.
The node verifies the signature, applies its policy (allow-list, quota, blocklist) and stores it.

**Federate.** Each node periodically pulls `GET /v1/sync?since=<cursor>` from the peers its operator listed and
blocklists from the nodes its operator follows. Everything pulled is verified and filtered locally.

**Create a torrent (UI).** Files are hashed in the browser by `create-torrent`; the result is a `.torrent` and a
magnet. Optionally *Seed from this device*: `prepare → PUT each file → finish`, after which libtorrent re-verifies
every piece. See [torrent-maker.md](torrent-maker.md).

## Trust boundaries

| boundary | what crosses | rule |
|---|---|---|
| web page → daemon | API calls | token + Host check + Origin check; never trusted by default |
| index node → client | listings, ratings, badges | listings re-verified; ratings/badges shown as that node's claims |
| peer node → node | listings, blocklists | re-verified, filtered by *local* policy; peers trusted only for availability |
| torrent content → UI origin | file bytes | served as inert downloads unless video/audio/common image; `sandbox` CSP |
| browser → daemon (seed upload) | file bytes | written only under the download dir, never over existing files, verified by libtorrent |

## State on disk

`~/.config/swarm/` (override with `SWARM_CONFIG_DIR`): `token` (0600), `settings.json`, `publisher.key` (0600),
`publish_seq.json`, `state/resume/*.resume` (libtorrent resume data incl. metadata), `state/created/*.torrent`.
Downloads go to `download_dir` (default `~/Downloads/swarm`). Index nodes: one SQLite file (`--db`).

## Concurrency notes

The daemon is a single asyncio process; libtorrent runs its own threads. Blocking work (hashing a path for
`/api/create`, file reads while streaming) runs in the default executor. The indexer uses one SQLite connection
behind a lock inside the event loop, which is fine for thousands of listings and is the first thing to change for
a large node.
