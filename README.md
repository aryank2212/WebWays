# Swarm

A BitTorrent client with streaming, plus an optional decentralized marketplace layer. The client is
useful on its own; the marketplace is a set of signed listings served by federated index nodes that
anyone can run. **The project ships software, not a canonical index**: the client starts with no
index sources and a fresh node starts empty.

```
protocol/   listing + rating format, ed25519 signing           (Apache-2.0)
core/       daemon: libtorrent, local REST API, HTTP streaming (GPL-3.0-or-later)
ui/         React + TypeScript front end, talks only to core   (GPL-3.0-or-later)
indexer/    federated index node: FTS search, moderation       (AGPL-3.0-or-later)
docs/       architecture, API references, listing spec, operator guide, security, decisions, research
scripts/    end-to-end tests, GitHub survey, notices generator
```

## Quick start

```
make setup            # venv + libtorrent wheel + npm deps (no compiler needed)
make ui               # build the web UI into ui/dist
make daemon           # prints http://127.0.0.1:8781/#token=...   open that
make test             # 60 unit/integration tests
make e2e              # real processes: indexer + 2 daemons, publish -> search -> stream -> takedown
```

Run an index node: `SWARM_ADMIN_TOKEN=... make indexer`, then see [docs/operators.md](docs/operators.md).
In the UI, *Sources* → add that node's URL, *Publish* → create an identity, seed a file and list it.

## Free torrent & magnet creator (built in)

The **Create** tab lets anyone drag files or a folder onto the page and get a magnet link and a `.torrent`, free,
no account. Hashing happens in the browser, no trackers are added unless you list them, and *Seed from this device*
starts sharing it through your own client. You can also drop a `.torrent` (or paste a magnet / info hash) to convert
and inspect it. It's built from existing MIT libraries (`create-torrent`, `parse-torrent`) found by surveying GitHub
first; details and the reuse-vs-build decision: [docs/torrent-maker.md](docs/torrent-maker.md),
[docs/research/github-survey.md](docs/research/github-survey.md).

## How the pieces fit

- **Streaming**: `GET /stream/<infohash>/<file>?sig=…` honours HTTP Range. Each read puts rising piece
  deadlines on the next ~24 MB so libtorrent fetches in playback order without forcing the whole torrent
  sequential. Works in the UI's player, VLC, mpv, anything that speaks HTTP.
- **Listings** are signed JSON ([docs/listing-spec.md](docs/listing-spec.md)). Clients re-verify every
  one, whichever node returned it.
- **Federation** is pull-based (`/v1/sync`), à la Mastodon relays but simpler: each node re-verifies and
  applies its own policy to everything it ingests.
- **Moderation** is per-operator: allow-list or open publishing, takedown with audit log, subscribable
  blocklists, user reports, ratings, operator-assigned verified badges.

## Status against the roadmap

| phase | state |
|---|---|
| 1 MVP: client + streaming | **Working.** Web UI served by the daemon. Tauri shell and mobile not started. |
| 1b Torrent/magnet creator | **Working.** Drag-and-drop in the UI, seed-from-browser, inspector. |
| 2 Listing spec + single node | **Working.** |
| 3 Federation + search | **Working** (pull sync, SQLite FTS5). No peer discovery: operators list peers by hand. |
| 4 Moderation + verification | **Basic.** Takedown, blocklists, reports, ratings, badges via API. No review UI, and "verified" is just an operator-set label with no proof workflow. |
| 5 Payments + mobile | **Not started.** `price` exists in the spec and UI but is informational; nothing is charged or enforced. |

## Where this deviates from the plan, and why

- **Python, not Go/Rust.** libtorrent ships as a prebuilt Python wheel, the dev box had no Go/Rust
  toolchain, and compiling large projects there has caused hard resets. One language also lets the daemon and
  indexer share the exact same signing code. The HTTP API and file formats are language-neutral, so an
  indexer rewrite is possible without touching clients.
- **Web UI instead of Tauri.** Same reason (no Rust). The UI only calls the local API, so wrapping it in
  Tauri later doesn't change it.
- **`protocol/` is Apache-2.0**, not GPL/AGPL, so third parties can implement the format without
  copyleft questions. Change it if you disagree.

## Documentation

Everything is indexed in [docs/README.md](docs/README.md): architecture, both API references, the listing spec,
operator guide, security model, decision log, testing guide, roadmap, research. Also
[CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), [CHANGELOG.md](CHANGELOG.md),
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Known limits

- Tested on loopback and in-process; not yet against the public DHT or at scale (see docs/testing.md).
- Linux only so far.
- The sync feed is unauthenticated and anything an index holds is public.
- Single-process indexer on SQLite: fine for thousands of listings, not for a global index.

## A note on the legal side

The design choices here (no default index, per-operator policy, takedown + audit trail, blocklists,
signed publisher identity) are meant to keep the software on the "tool" side of the line and to make
compliance workable for operators. They don't guarantee it. Discovery is the part courts have
scrutinised, so get advice from a lawyer in your jurisdiction before operating a public index or
launching any hosted marketplace, and before turning on payments.
