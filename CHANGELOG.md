# Changelog

Format: [Keep a Changelog](https://keepachangelog.com). Versions are pre-1.0; the API may change.

## [0.3.0] - 2026-11-02

### Changed
- **Project renamed from "Swarm" to "WebWays".** The GitHub repository is now `aryank2212/webways`
  (the old `swarm-torrent` URL redirects). "Swarm" is still used where it means the BitTorrent term for the group of
  peers sharing a torrent.
- Python packages: `swarm_protocol` → `webways_protocol`, `swarm_indexer` → `webways_indexer`,
  `swarm_core` → `webways_core`; commands `swarm-core`/`swarm-indexer` → `webways-core`/`webways-indexer`.
- Environment variables: `SWARM_ADMIN_TOKEN` → `WEBWAYS_ADMIN_TOKEN`, `SWARM_CONFIG_DIR` → `WEBWAYS_CONFIG_DIR`.

### Breaking (pre-1.0, no known deployments)
- **Signed-listing domain separators changed** (`swarm-listing-v1` → `webways-listing-v1`, `swarm-rating-v1` →
  `webways-rating-v1`). Listings and ratings signed by 0.2.x do **not** verify under 0.3.0 and must be re-signed
  (re-publish). The listing format itself (`"v": 1`) is unchanged.
- `/v1/node` now reports `"software": "webways-indexer"`; a 0.3.0 client will not add a 0.2.x node as a source and
  vice versa.
- Default config directory `~/.config/swarm` → `~/.config/webways`; default download directory
  `~/Downloads/swarm` → `~/Downloads/webways`. To keep an existing install:
  `mv ~/.config/swarm ~/.config/webways` and, if you use the default download directory, set `download_dir` in
  `settings.json` to the old location (or move the folder). Your `publisher.key` moves with the directory, so your
  publisher identity is preserved.
- Torrents created by 0.2.x record `created by: swarm`; new ones record `webways`. This is metadata only and does not
  change info hashes of existing torrents.

## [0.2.0] - 2026-11-02

### Added
- **Create tab:** free drag-and-drop torrent & magnet creator. Drop files or a folder; get info hash, magnet link
  and `.torrent`. Options: name, comment, piece size, trackers, web seeds, private flag. Built on the MIT
  libraries `create-torrent` and `parse-torrent` (found via a GitHub survey; see `docs/research/`).
- **Convert / inspect:** drop a `.torrent` or paste a magnet link / info hash to convert it and see its contents.
- **Seed from this device:** `POST /api/seed/prepare`, `PUT /api/seed/{key}/files/{i}`, `POST /api/seed/{key}/finish`,
  `DELETE /api/seed/{key}`. Safe staging: paths contained, no overwrite, exact sizes, disk check, libtorrent verifies.
- `POST /api/create` options: `trackers`, `webseeds`, `private`, `piece_size`, `version` (v1/v2/hybrid).
- `GET /api/torrents/{key}/torrent` downloads the `.torrent`.
- `POST /api/torrents/{key}/peers` to connect a known peer.
- Publish tab can be pre-filled from the Create tab.
- Documentation set under `docs/`, `THIRD_PARTY_NOTICES.md`, `CONTRIBUTING.md`, `SECURITY.md`, CI workflow,
  reproducible GitHub survey script.
- Browser end-to-end test `scripts/ui_e2e.js`.

### Changed
- Created torrents contain **no trackers** unless the user lists them (the underlying library's eight built-in
  public trackers are overridden).
- Files that are hidden system junk are skipped when picked, and the UI says how many.

### Fixed
- Resume data now includes torrent metadata (libtorrent `save_info_dict`), so magnet-added torrents restart offline.
- Shutdown waits for the newest resume snapshot per torrent (stale snapshots previously could win a race).
- Queued torrents no longer display as "paused".

## [0.1.0] - 2026-11-02

### Added
- Daemon (libtorrent, REST API, HTTP Range streaming), web UI, signed-listing protocol, federated index node with
  full-text search, takedown/blocklists/reports/ratings/verified badges, end-to-end smoke test.
