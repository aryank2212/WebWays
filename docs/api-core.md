# Core daemon API

Base: `http://127.0.0.1:8781`. JSON in, JSON out. Errors: `{"error": {"code": "...", "message": "..."}}`.

**Auth.** Every `/api/*` call needs `Authorization: Bearer <token>` (`webways-core token` prints it; stored in
`~/.config/webways/token`). The `Host` header must be loopback or `--allow-host`; state-changing requests with a
mismatched `Origin` get `403`. `/stream/*` uses a per-file signature instead (below).
An infohash (`{key}`) is 40 lowercase hex (v1, also used for hybrid torrents) or 64 (v2-only).

## Status & settings

| call | notes |
|---|---|
| `GET /api/status` | `{version, download_rate, upload_rate, dht_nodes, torrents, encryption}` |
| `GET /api/settings` | `download_dir, listen_port, encryption, download_limit, upload_limit` (bytes/s, 0 = none) |
| `PUT /api/settings` | any subset. `download_dir` must be absolute; `encryption` is `enabled` or `forced`. `422` on invalid, nothing applied |

## Torrents

| call | body / result |
|---|---|
| `GET /api/torrents` | `{torrents: [Torrent]}` |
| `POST /api/torrents` | one of `{magnet}`, `{infohash, name?}`, `{torrent_b64}` → `201 Torrent` |
| `GET /api/torrents/{key}` | `Torrent` + `files: [{index, path, size, priority, progress, stream_url}]` |
| `POST /api/torrents/{key}/pause` · `/resume` | → `Torrent` |
| `DELETE /api/torrents/{key}?delete_files=1` | keeps files unless `delete_files=1` |
| `PUT /api/torrents/{key}/files/{i}/priority` | `{priority: 0-7}`; 0 skips the file |
| `POST /api/torrents/{key}/peers` | `{host: <IP literal>, port}`: connect to a known peer |
| `GET /api/torrents/{key}/torrent` | the `.torrent` (`application/x-bittorrent`). The original bytes for torrents created here; regenerated for others. `409` until metadata is known |

`Torrent` = `{infohash, name, state, progress, size, downloaded, download_rate, upload_rate, peers, seeds,
has_metadata, eta, error, save_path, magnet}`. `state`: `checking · metadata · downloading · finished · seeding ·
paused`.

## Creating and seeding

| call | notes |
|---|---|
| `POST /api/create` | Hash a path **on the daemon's machine** and seed it. `{path, comment?, trackers?: [url], webseeds?: [url], private?: bool, piece_size?: 0 or 2^n in [16 KiB, 64 MiB], version?: "v1"\|"v2"\|"hybrid" (default hybrid)}` → `201 Torrent`. **No trackers unless listed.** Tracker schemes `udp http https ws wss`; web seeds `http https` |
| `POST /api/seed/prepare` | `{torrent_b64}` → `201 {infohash, name, files: [{index, path, size}]}`. Validates the torrent, resolves every target path inside `download_dir`, checks free disk (needs total + 256 MiB). `409` if already added, `422` bad torrent/path escape, `429` >4 pending, `507` no space. Pending entries expire after 1 h |
| `PUT /api/seed/{key}/files/{index}` | raw bytes of that file. Must be exactly the declared size (`422` otherwise, nothing left behind). `409` if a file already exists at the target (never overwrites). Streams to `*.part`, then renames |
| `POST /api/seed/{key}/finish` | needs every file uploaded (`409` otherwise) → adds the torrent; libtorrent re-hashes. `201 Torrent`. Check `progress`: damaged uploads show `< 1.0` |
| `DELETE /api/seed/{key}` | abort: removes everything uploaded for it |

## Index sources & discovery

The client starts with **no** sources. Nothing is queried until you add one.

| call | notes |
|---|---|
| `GET /api/sources` | `{sources: [{url, name, enabled, takedown_contact}]}` |
| `POST /api/sources` | `{url, name?}`. http(s) only, no credentials. Fetches `/v1/node` to confirm it's a WebWays index → `201` |
| `PUT /api/sources` | `{url, enabled}` |
| `DELETE /api/sources?url=…` | |
| `GET /api/search?q=&tag=&limit=` | `{items: [{id, listing, sources, verified_by, rating}], errors: {url: message}}`. Listings failing signature verification are dropped. `verified_by`/`rating` are *claims by the named node* |
| `POST /api/report` | `{source, listing, category: copyright\|illegal\|malware\|spam\|other, detail?, contact?}` → forwarded to that node's operator |
| `POST /api/rate` | `{source, listing, score: 1-5}` signed with your identity |

## Identity & publishing

| call | notes |
|---|---|
| `GET /api/identity` | `{public_key: string \| null}` |
| `POST /api/identity` | create the ed25519 key (`409` if it exists) → `201` |
| `POST /api/publish` | `{infohash, title, description?, tags?, license, price?: {amount, currency}, withdrawn?, seq?, source?}`. `seq` auto-increments per infohash. With `source` it is also POSTed to that node. → `201 {listing, id, published}` |

## Streaming

`GET|HEAD /stream/{key}/{index}?sig=<hex>`: `sig` is `HMAC-SHA256(token, "key:index")[:32]`; `files[].stream_url` in
`GET /api/torrents/{key}` already contains it, so a media player never needs the master token.
Supports `Range` (`206`, suffix ranges, `416` when unsatisfiable; multi-range is ignored and the whole file is
served). Waits up to 45 s for metadata and aborts the transfer if no new piece arrives for 90 s. Only video, audio
and PNG/JPEG/GIF/WebP/AVIF keep their real type; everything else is `application/octet-stream` + `attachment`.

## Static UI

`GET /` serves `ui/dist/index.html` (and `/assets/*`) when built; otherwise a small JSON hint.
