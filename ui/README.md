# webways-ui

GPL-3.0-or-later. React + TypeScript single-page app. It talks **only** to the daemon's local API (never to index
nodes or the internet directly).

```
npm install
npm run build     # typecheck + build into ui/dist (served by the daemon at /)
npm run dev       # Vite dev server on :5173, proxying /api and /stream to a daemon on :8781
```

Open the address `webways-core serve` prints; it ends in `#token=…` (a URL fragment, never sent to a server). The page
stores the token in `sessionStorage` and removes it from the address bar.

Tabs: **Discover** (search added index sources, download/stream/rate/report) · **Downloads** (progress, files, play,
settings) · **Create** (drag-and-drop torrent/magnet creator + inspector, see
[../docs/torrent-maker.md](../docs/torrent-maker.md)) · **Publish** (identity, sign and send listings) · **Sources**.

Reused packages: `create-torrent`, `parse-torrent` (MIT). `vite.config.ts` aliases Node's `path` to
`src/lib/path-shim.ts` for them. Licenses: [../THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
Browser test: `../scripts/ui_e2e.js`.
