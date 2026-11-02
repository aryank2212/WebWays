# swarm-indexer

AGPL-3.0-or-later. A federated index node: signed listings in, full-text search out, with operator-controlled
moderation. **Ships empty; no default peers or blocklists.**

```
export SWARM_ADMIN_TOKEN="$(openssl rand -hex 24)"
PYTHONPATH=protocol:indexer python -m swarm_indexer serve --db index.db --config node.toml
```

- API: [../docs/api-indexer.md](../docs/api-indexer.md)
- Running one (policy file, takedowns, blocklists, federation): [../docs/operators.md](../docs/operators.md)
- Modules: `app.py` (HTTP), `db.py` (SQLite/FTS5, moderation state), `federation.py` (pull sync), `policy.py`, `cli.py`.
- Tests: `indexer/tests` (13).

AGPL note: if you run a modified node as a public service, you must offer your users the modified source.
