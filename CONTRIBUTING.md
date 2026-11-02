# Contributing

Thanks for helping. Short version: keep it tested, keep it documented, keep defaults private.

## Setup

```
make setup        # python venv (libtorrent wheel, aiohttp, cryptography, pytest) + npm install
make test         # 60 tests
make ui           # build the web UI
make e2e          # real-process smoke test
```

Small machine? Use `make ui-nice` and run tests with `nice -n 10`. Builds can spike RAM and I/O.

## Layout and licenses

`protocol/` Apache-2.0 · `core/`, `ui/` GPL-3.0-or-later · `indexer/` AGPL-3.0-or-later. By contributing you agree
your change is under the license of the directory it touches. Don't copy in code from projects without a
compatible license (a repository with no license file is *not* free to reuse).

## Ground rules

- **Look before you build.** If a maintained, compatible library does the job, reuse it and record it in
  `docs/research/` and `THIRD_PARTY_NOTICES.md` (`node scripts/gen_notices.js > THIRD_PARTY_NOTICES.md`).
- **Defaults stay private and inert:** no built-in index, no default trackers, nothing contacted until the user acts.
- **Never trust the network:** re-verify listings; treat torrent contents and node-supplied fields as hostile.
- **Tests with the change.** Bug fix → a test that fails without it. New API → entry in `docs/api-*.md`.
- **Document decisions** that someone might later reverse in `docs/decisions.md`; user-visible changes in
  `CHANGELOG.md`.
- Python: standard library first, type hints, short comments that explain *why*. UI: strict TypeScript, no
  unused code.

## Pull requests

Describe what changed and how you verified it. Include the output of `make test` and, for UI changes, either the
browser test or a screenshot. Security-relevant changes: say which part of `docs/security.md` they touch.

Please don't use issues for security problems: see [SECURITY.md](SECURITY.md).
