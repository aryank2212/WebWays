# The torrent & magnet creator

A free tool built into the app (Create tab): drop files or a folder, get a `.torrent` and a magnet link.
No account, no fee, no limit imposed by us.

## What it does

1. **Create** — drag files or a folder onto the drop zone (or *Choose files* / *Choose folder*). Pick options,
   press *Create torrent*. Output: info hash, magnet link (copy), `.torrent` (download).
2. **Seed** — *Seed from this device* copies the files into your client's download folder and starts sharing.
   A magnet or `.torrent` only *describes* files; nobody can download until someone seeds.
3. **List** — *List it on an index…* jumps to the Publish tab with the info hash filled in.
4. **Convert / inspect** — drop a `.torrent`, or paste a magnet link or bare info hash, to get the other form,
   see the name, size, files and trackers, or add it straight to your client.

## Options

| option | default | notes |
|---|---|---|
| name | folder name, or the file name, or `my-files` for loose files | what downloaders see; for multi-file torrents it is the top-level folder |
| comment | empty | stored in the `.torrent` |
| piece size | automatic | 256 KiB … 16 MiB. Automatic picks by total size (capped at 4 MiB) |
| trackers | **none** | one URL per line (`udp/http/https/ws/wss`). Without any, peers are found through DHT/PEX |
| web seeds | none | `http(s)` URLs of a plain web copy (BEP 19) |
| private | off | sets the private flag (DHT/PEX off; you need a tracker) |

Hidden system files (`.DS_Store`, `Thumbs.db`-style junk) are skipped at pick time, and the list says how many.

## Privacy: how it differs from the library default

The library we use, `create-torrent`, silently adds **eight public trackers** when no tracker option is given.
We pass an explicit empty list, so **no tracker is contacted or recorded unless you add one**. Reason: a tracker
learns the IP address of everyone using the torrent. The magnet you get has no `tr=` parameter in that case.
(A test asserts this.)

Hashing happens locally in the browser tab. Nothing is sent anywhere until you press *Seed from this device*, and
then it goes only to **your own** daemon.

## How seeding works

```
browser                               daemon (your machine, or a server you run)
  create-torrent hashes files
  POST /api/seed/prepare {torrent} ──▶  parse; resolve every file path inside download_dir; check disk
                                    ◀──  {infohash, files:[{index,path,size}]}
  PUT /api/seed/{key}/files/{i} ────▶  stream to  <path>.part ; size must match exactly ; rename
  …one request per file…
  POST /api/seed/{key}/finish ──────▶  add torrent; libtorrent re-hashes everything
```

Safety properties (each covered by a test in `core/tests/test_creator.py`):

- paths are resolved and must stay inside the download directory (a hostile `.torrent` with `../..` can't escape);
- an existing file is **never overwritten** (`409`);
- a wrong-sized upload is refused and its partial file removed;
- if bytes were altered in transit, libtorrent's verification leaves `progress < 1.0` instead of seeding bad data;
- aborting (`DELETE /api/seed/{key}`) removes what was copied; abandoned uploads expire after an hour;
- disk space is checked first (total size + 256 MiB headroom).

Files are **copied**, so seeding needs room for a second copy. To seed a file where it already is without
copying, use `POST /api/create` with its path on the daemon's machine (note: that torrent is built by libtorrent,
so its info hash differs from one built in the browser).

## Interoperability

The browser-made torrent is a standard v1 torrent. `scripts/ui_e2e.js` proves in a real browser that the daemon
seeds it under the *same* info hash and that a second daemon downloads 100% of it. `POST /api/create` can also
make v2 and hybrid torrents, which the browser library cannot.

## Limits

- Hashing runs in the page: very large inputs (many GB) take a while and keep the tab busy, and a closed tab
  cancels it. For big jobs use `POST /api/create` (runs in the daemon).
- Dropped *folders* rely on the browser's directory-entry API (Chrome, Edge, Firefox, Safari all support it).
  Where it isn't available the drop falls back to a flat file list; *Choose folder* always keeps paths.
- No v2/hybrid output from the browser; no editing of existing `.torrent` files (inspect only).
- Only create torrents of content you have the right to distribute.

## Code map

`ui/src/tabs/Create.tsx` (UI) · `ui/src/lib/maker.ts` (drop/walk, junk filter, create, parse, magnet) ·
`ui/src/lib/path-shim.ts` (browser stand-in for Node `path`) · `core/swarm_core/seeding.py` (upload staging) ·
`core/swarm_core/engine.py::create_torrent` (server-side creation).
Reused libraries: see [research/github-survey.md](research/github-survey.md) and
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
