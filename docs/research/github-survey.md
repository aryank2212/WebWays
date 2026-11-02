# "Look on GitHub first": survey and decision

**Brief:** before building a free drag-and-drop magnet/torrent creator, fetch GitHub, find as many existing tools
as possible, and only create what can't be found.

**Method:** 14 repository searches plus individual inspection of the promising or already-used projects, using the
GitHub API (unauthenticated). Reproduce with `python3 scripts/research/github_survey.py`; the dated raw output is in
[github-survey-data.md](github-survey-data.md). Selection criteria: (1) a license we can legally reuse inside
GPL-3.0-or-later / AGPL-3.0-or-later code, (2) maintained, (3) runs in a browser or in our Python daemon,
(4) does something we'd otherwise have to write.

## Findings

| project | license | active? | what it is | decision |
|---|---|---|---|---|
| [webtorrent/create-torrent](https://github.com/webtorrent/create-torrent) | MIT | yes (2026-10) | creates `.torrent` from File/Blob in the browser or Node; v1 | **reused** (npm `create-torrent@6.1.3`). Does the hashing and bencoding in the tab. Overridden: it adds 8 public trackers by default, we pass an explicit empty list |
| [webtorrent/parse-torrent](https://github.com/webtorrent/parse-torrent) | MIT | yes (2026-10) | parse `.torrent`/magnet/info hash; build magnets | **reused** (`parse-torrent@11.0.24`) for magnet generation and the inspector. Its `path` import needed a small browser shim (`ui/src/lib/path-shim.ts`) |
| `magnet-uri`, `bencode`, `uint8-util`, … | MIT/ISC | yes | transitive deps of the two above | reused transitively; listed in THIRD_PARTY_NOTICES.md |
| [arvidn/libtorrent](https://github.com/arvidn/libtorrent) | BSD-3-Clause (GitHub's detector reports `NOASSERTION`; the LICENSE file text was checked by hand) | yes | the engine we already use | **reused** for server-side creation (`POST /api/create`: v1/v2/hybrid, trackers, web seeds, private) |
| [rndusr/torf](https://github.com/rndusr/torf) | GPL-3.0 | yes | Python module to create/edit torrents and magnets | evaluated, **not adopted**: license-compatible but duplicates libtorrent's creator, which is already a dependency. Would be the first choice if we ever need *editing* existing torrents |
| [alexpdev/torrentfile](https://github.com/alexpdev/torrentfile) | Apache-2.0 | yes | v1/v2/hybrid creator, checker, editor (Python) | evaluated, **not adopted**: same reason. Candidate for editing/checking features |
| [kz26/dottorrent](https://github.com/kz26/dottorrent) (+ `-gui`, `-cli`) | MIT / GPL-3.0 | no (2023) | Python library + PyQt GUI | not adopted: unmaintained, desktop-only GUI |
| [torf-gui](https://github.com/SavageCore/torf-gui) | GPL-3.0 | yes | PyQt desktop GUI on torf | not adopted: desktop toolkit, not embeddable in our web UI. A useful reference for option naming |
| [pobrn/mktorrent](https://github.com/pobrn/mktorrent) | GPL-2.0-or-later (per its COPYING; GitHub's detector shows none) | stale (2022) | C command-line creator | not adopted: command-line only, nothing to embed in a web UI |
| [AnimMouse/torrent-webseed-creator](https://github.com/AnimMouse/torrent-webseed-creator) | MPL-2.0 | yes | GitHub-Actions based web-seed torrents | not adopted: different workflow. Informed our web-seed option |
| [Kimbatt/torrent-creator](https://github.com/Kimbatt/torrent-creator) | **none** (no LICENSE file) | yes (2026-10) | browser torrent creator (Svelte/TS) | **cannot be reused.** No license means all rights reserved; copying or bundling it would infringe. Used only to confirm the idea works in a browser. Option: ask the author to add a license |
| many small GitHub-hosted magnet/torrent converters | mostly none | stale | tiny scripts | ignored |

## What we found *missing*, so what we built

No maintained, permissively licensed project provided a **drag-and-drop UI that creates a torrent and then seeds it
through a local client**. So we built only that glue, on top of the reused libraries:

- drop zone with folder walking (`webkitGetAsEntry`), junk filtering that mirrors the library's rule;
- options UI with privacy-first defaults (no trackers);
- converter/inspector UI;
- the seed-upload protocol and its safety checks (`core/webways_core/seeding.py`);
- the browser `path` shim.

Roughly: ~300 lines of UI, ~150 lines of browser helpers, ~150 lines of daemon code. The hashing, bencoding, magnet
encoding/decoding and the torrent engine are all reused.

## Caveats

- Search results depend on GitHub's ranking and the queries used; "I found nothing" is not proof nothing exists.
  The script and data are in the repo so the search can be extended and repeated.
- License findings come from GitHub's detector plus a look at the repository root for unlicensed candidates.
  Verify a license yourself before depending on it.
- Reused packages are pinned (`create-torrent@6.1.3`, `parse-torrent@11.0.24`) and covered by tests; upgrade
  deliberately, re-running `scripts/ui_e2e.js`.
