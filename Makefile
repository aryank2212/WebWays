PY := .venv/bin/python

setup:
	python3 -m venv .venv
	.venv/bin/pip install libtorrent aiohttp cryptography pytest pytest-asyncio
	cd ui && npm install

test:
	.venv/bin/pytest -q

e2e:
	$(PY) scripts/e2e.py

ui:
	cd ui && npm run build

# Low-priority variants for small machines: builds can spike RAM and I/O.
ui-nice:
	cd ui && NODE_OPTIONS=--max-old-space-size=1024 nice -n 15 npm run build

daemon:
	PYTHONPATH=protocol:indexer:core $(PY) -m webways_core serve

indexer:
	PYTHONPATH=protocol:indexer:core WEBWAYS_ADMIN_TOKEN=$${WEBWAYS_ADMIN_TOKEN:?set WEBWAYS_ADMIN_TOKEN} $(PY) -m webways_indexer serve

.PHONY: setup test e2e ui ui-nice daemon indexer
