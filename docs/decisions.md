# Decision log

Short records of choices that shaped the code. Newest last.

### D1 — The project ships software, not an index
No default index source in the client; a fresh node is empty with no peers and no blocklist subscriptions.
*Why:* discovery is where legal exposure concentrates; each operator must own their policy.
*Consequence:* first-run UX needs an explicit "add a source" step (the Discover tab explains it).

### D2 — Signed listings, verified everywhere
ed25519, canonical JSON, domain-separated. Clients and nodes re-verify and never trust the sender.
*Rejected:* trusting TLS to the node (a compromised node could alter listings); JWS (canonicalisation pitfalls,
extra spec surface).

### D3 — Python instead of Go/Rust
libtorrent ships a prebuilt wheel; the dev machine had no Go/Rust and compiles caused hard resets; one language lets
the daemon and indexer share the signing code. The HTTP API and formats are language-neutral, so an indexer rewrite
is possible.

### D4 — Web UI first, Tauri later
Same toolchain constraint. The UI only calls the local API, so a Tauri (or Electron) shell wraps it unchanged.

### D5 — Local API hardened like a server
Bearer token, Host and Origin checks, per-file signed stream URLs, inert content types. A malicious web page or
torrent must not be able to drive the daemon or read the token.

### D6 — `protocol/` is Apache-2.0
So third parties can implement the format without copyleft questions. Core/UI GPL-3.0-or-later; indexer
AGPL-3.0-or-later so hosted forks stay open (as planned).

### D7 — Streaming with piece deadlines, not sequential mode
Sequential mode makes a torrent fetch strictly in order, which starves the swarm of rare pieces. Deadlines on the
read window give playback order locally while the rest of the torrent downloads normally.

### D8 — Creator: reuse `create-torrent` + `parse-torrent`, build only the glue
After a GitHub survey (docs/research/github-survey.md) the two MIT webtorrent libraries cover hashing and
magnet/torrent conversion in the browser. We wrote the drag/drop handling, UI, safety checks and the seed-upload
path. An unlicensed browser creator (Kimbatt/torrent-creator) was *not* used.

### D9 — Creator never adds trackers by default
`create-torrent` adds eight public trackers unless told otherwise; we override it (privacy; consistent with D1).

### D10 — Seeding browser-made torrents copies files into the download dir
A browser cannot hand the daemon a filesystem path. Copying is simple and safe (verified by libtorrent) but
needs 2× disk. Path-based creation remains available through `POST /api/create`.

### D11 — Takedown deletes, blocks and logs
A takedown removes the listing, blocks the infohash/listing/publisher against re-listing and federation re-import,
and writes an audit row. Subscribed blocklists mirror the source exactly; a local takedown always takes ownership of
an entry.

### D12 — Resume data must include metadata
libtorrent 2.x only stores the info dictionary with `save_info_dict`; without it, torrents added by magnet could
never restart offline. All saves use the flag, and shutdown waits for the *newest* snapshot per torrent.

### D13 — Renamed to WebWays (v0.3.0)
The working name "Swarm" collided with the BitTorrent term for a torrent's peers (confusing in docs and UI copy such
as "playing from the swarm") and with other software of that name. Everything that named the *project* was renamed,
including wire-level identifiers: the signature domain separators and the `/v1/node` software id. That was a
deliberate breaking change taken while there were no deployments and no published listings. Where "swarm" means the
group of peers, it is kept. Migration notes are in CHANGELOG.md. The old GitHub URL redirects, but redirects can be
broken by someone later creating a repository with the old name; update bookmarks and remotes.
