# Roadmap & status

| phase | state | notes |
|---|---|---|
| 1 MVP: client + streaming | **working** | web UI served by the daemon. Tauri shell and mobile not started |
| 1b Creator tool | **working** | drag-and-drop creator, converter/inspector, seed-from-browser (v0.2.0) |
| 2 Listing spec + single node | **working** | |
| 3 Federation + search | **working** | pull sync, FTS5. Peers are configured by hand; no discovery |
| 4 Moderation + verification | **basic** | takedown, blocklists, reports, ratings, operator badges via API. No review UI; "verified" is an operator label with no proof workflow |
| 5 Payments + mobile | **not started** | `price` is informational only; nothing is charged or enforced |

## Next candidates (unordered)

- Review UI for reports and takedowns; notice/counter-notice templates.
- Publisher verification workflow (e.g. proof via DNS TXT / well-known file), shown as a claim per node.
- Peer discovery between nodes (signed node announcements) while keeping "no default peers".
- Tauri shell; with it, pass real file paths so seeding needs no copy.
- Hybrid/v2 torrent creation in the browser (needs a v2 hasher; none found on GitHub, see survey).
- Magnet-handler registration (`magnet:` opens the app).
- Windows/macOS support and packaging.
- Payments (Stripe Connect / Lightning) with the torrent as delivery layer.
