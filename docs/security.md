# Local API security model

The daemon runs on the user's machine and can read and write files, so it is hardened against web
pages that try to reach it, not only against other programs.

- **Loopback by default.** `--host` must be changed deliberately to expose it.
- **Bearer token** (`~/.config/webways/token`, mode 0600) on every `/api/*` call, compared in constant time.
  The browser UI receives it in the URL *fragment*, which is never sent to a server, then strips it.
- **Host check** (`421`) defeats DNS-rebinding; add `--allow-host` only when serving through a reverse proxy.
- **Origin check** (`403`) on state-changing requests. No CORS headers are sent.
- **Stream URLs** carry an HMAC bound to `(infohash, file index)` so players can open them without
  the master token, and a leaked URL grants access to one file only.
- **Content from torrents is untrusted.** Only video/audio/common-image types are served with their
  own type; everything else is `application/octet-stream` + `attachment`, with `nosniff` and a
  `sandbox` CSP, so a malicious `.html`/`.svg` can't run on the UI's origin and read the token.
- **Listings from nodes are untrusted.** The client re-verifies every signature; node-supplied ratings
  and "verified" badges are shown as claims attributed to that node.
- **Transport encryption** (protocol encryption) is preferred by default; `forced` rejects plain peers.
  It hides content from passive observers but not the fact that you are using BitTorrent, and your IP
  is still visible to the swarm. Use a VPN if that matters.
- Publisher keys are stored unencrypted at `~/.config/webways/publisher.key` (0600). Losing the file
  loses the identity; leaking it lets anyone publish as you.

## Creator and seed upload

- Torrent creation in the browser reads files locally; nothing leaves the tab until the user presses
  *Seed from this device*, and then only to their own daemon.
- No trackers are added to created torrents by default (a tracker learns the IPs of everyone using the torrent).
- `/api/seed/*` writes files, so it is the most sensitive endpoint added after v0.1. It requires the API token and
  an allowed Host/Origin like every write, and additionally: each target path is resolved and must be inside the
  download directory; an existing file is never overwritten; uploads must match the declared size exactly and are
  written to `*.part` then renamed; free disk is checked first; at most 4 uploads may be pending and they expire
  after an hour; libtorrent re-hashes everything on `finish`, so modified bytes are not served as complete.
- Residual risk: a token holder can fill the download directory (bounded by the disk check) and can create files
  with names chosen by the torrent. Don't expose the daemon to untrusted users.

## Third-party code

Reused libraries are pinned and listed in `THIRD_PARTY_NOTICES.md`. A repository without a license is not reused
(see `docs/research/github-survey.md`). Run `npm audit` before releases.
