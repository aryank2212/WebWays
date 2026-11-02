# swarm-core

GPL-3.0-or-later. The daemon: libtorrent + local REST API + HTTP streaming + index-source client + publishing.

```
make daemon        # prints http://127.0.0.1:8781/#token=...   (open it; serves ui/dist if built)
swarm-core token   # print the API token
```

Flags: `--host` (default loopback), `--port`, `--ui-dir`, `--allow-host` (behind a reverse proxy).
Config dir: `~/.config/swarm` or `$SWARM_CONFIG_DIR`.

- API: [../docs/api-core.md](../docs/api-core.md) · security model: [../docs/security.md](../docs/security.md)
- Modules: `engine.py` (session, resume data, creation), `api.py` (routes, security middleware),
  `streaming.py` (Range + piece deadlines), `sources.py` (index sources, search, verification),
  `seeding.py` (upload staging), `config.py`.
- Tests: `core/tests` (25) use real libtorrent sessions on loopback.
