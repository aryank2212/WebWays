# Security policy

## Reporting a vulnerability

Please report privately using GitHub's *Report a vulnerability* (Security → Advisories) on this repository rather
than opening a public issue. Include what you did, what you expected, what happened, and the version/commit.
You'll get an acknowledgement and we'll agree a disclosure timeline with you.

## Scope

In scope: the daemon's local API (auth bypass, DNS rebinding/CSRF, path traversal, arbitrary file read/write,
stream-origin XSS), the index node API (signature/blocklist bypass, injection, DoS amplification), the seed-upload
path, signature verification, and key handling.

Out of scope: BitTorrent protocol weaknesses (report to libtorrent), the privacy limits already documented
(your IP is visible to peers; protocol encryption doesn't hide that you use BitTorrent), content hosted by third-party
index operators.

The threat model is in [docs/security.md](docs/security.md).

## Supported versions

Pre-1.0: only the latest release receives fixes.
