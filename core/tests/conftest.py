import asyncio
import os
import time
import warnings

import pytest
from aiohttp.test_utils import TestClient, TestServer

warnings.filterwarnings("ignore", category=DeprecationWarning)

from swarm_core.api import make_app, stream_sig  # noqa: E402
from swarm_core.config import Settings  # noqa: E402
from swarm_core.engine import Engine  # noqa: E402

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def loopback():
    return {"listen_interfaces": "127.0.0.1:0", "enable_dht": False, "enable_lsd": False, "enable_upnp": False,
            "enable_natpmp": False, "allow_multiple_connections_per_ip": True,
            "ignore_limits_on_local_network": False}


@pytest.fixture
def make_engine(tmp_path):
    engines = []

    async def make(name, **settings):
        eng = Engine(Settings(download_dir=str(tmp_path / name), **settings), tmp_path / f"{name}-state", loopback())
        await eng.start()
        engines.append(eng)
        return eng

    yield make
    for e in engines:
        asyncio.get_event_loop_policy()  # engines are stopped by the loop teardown; sessions free on GC


@pytest.fixture
def payload(tmp_path):
    """A 6 MB random 'movie' plus a hostile html file, laid out as a directory torrent."""
    root = tmp_path / "share"
    root.mkdir()
    (root / "movie.mp4").write_bytes(os.urandom(6_000_000))
    (root / "page.html").write_text("<script>alert(1)</script>")
    return root


@pytest.fixture
async def daemon(tmp_path):
    clients = []

    async def make(engine, settings=None, config_dir=None):
        cfg = config_dir or tmp_path / "cfg"
        app = make_app(settings=settings or engine.settings, config_dir=cfg, engine=engine, token=TOKEN)
        app.on_startup.clear()      # tests start/stop engines themselves
        app.on_cleanup.clear()
        c = TestClient(TestServer(app))
        await c.start_server()
        clients.append(c)
        return c

    yield make
    for c in clients:
        await c.close()


async def wait_for(pred, timeout=30, step=0.1):
    t = time.monotonic()
    while time.monotonic() - t < timeout:
        if pred():
            return True
        await asyncio.sleep(step)
    return False
