# Testing

```
make test        # 60 pytest tests, ~20 s: protocol, indexer, core (real libtorrent sessions on loopback)
make e2e         # real processes: indexer + two daemons; publish → search → stream → download → takedown
make ui          # typecheck + production build of the UI
```

Browser test of the Create tab (needs Playwright and Chrome; paths are examples):

```
.venv/bin/python scripts/e2e.py --keep          # prints the temp dir; leaves the stack running
NODE_PATH=/path/to/node_modules CHROME=/usr/bin/google-chrome node scripts/ui_e2e.js
# then stop the processes listed in <tmpdir>/pids
```

## What is covered

| area | tests |
|---|---|
| listing/rating format | validation matrix, tampering, wrong key, unicode canonicalisation, floats/bools rejected, key file mode |
| indexer | publish/search/get, FTS5 injection attempts, supersede/withdraw, takedown (+re-list blocked, counter-notice), allow-list, quotas, reports/ratings/badges, federation pull incl. a hostile peer with forged and blocked items, blocklist subscription follow/lift, local block surviving unsubscribe |
| daemon security | 401 without token, 421 bad Host, 403 bad Origin, 403 bad stream signature, signature bound to file index |
| streaming | Range from the middle of a half-downloaded torrent (bytes compared to source), suffix range, HEAD, 416, hostile `.html` served as an inert download |
| lifecycle | add by infohash, pause/resume, priorities, **restart from resume data**, remove with files |
| discovery loop | publish → index → search → download; republish bumps `seq`; withdrawal hides; report reaches the operator; forged listings from a hostile node are dropped; dead source reported, not fatal |
| creator | no trackers by default; tracker/webseed/private/piece-size/version round-trip; bad options rejected; `.torrent` download; seed upload flow; corrupt upload detected; no overwrite; cancel cleanup; path traversal contained; disk-full |
| browser | `scripts/ui_e2e.js`: folder → torrent with no `tr=`; junk skipped; `.torrent` download; seed with identical info hash; second daemon downloads 100%; explicit tracker; invalid tracker rejected; drop file; drop `.torrent` into the inspector; bare hash → magnet; no console errors |

## What is *not* covered (be honest about it)

- the public DHT / real trackers / NAT traversal (everything runs on loopback with manually-added peers);
- more than a handful of peers, large torrents (> a few hundred MB), or long-running soak;
- playback in a real media player (bytes are verified, not decoding);
- non-Linux platforms; browsers other than Chrome;
- indexer under load (single SQLite connection);
- anything CI doesn't run: the browser test (`scripts/ui_e2e.js`) is run by hand. The GitHub Actions workflow (tests, UI build, real-process e2e) passed on a clean Ubuntu runner on 2026-11-02.
