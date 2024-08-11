import os
import time
import random

from multiprocessing import Process

import httpx
import pytest
import uvicorn


LISTEN_PORT = random.randint(30_000, 42_000)


@pytest.fixture
def server(alembic_migration):
    os.environ["POSTGRESQL_URL"] = alembic_migration
    proc = Process(
        target=uvicorn.run,
        args=("oonirun.main:app",),
        kwargs={"host": "127.0.0.1", "port": LISTEN_PORT, "log_level": "debug"},
        daemon=True,
    )
    proc.start()
    # Give it as second to start
    time.sleep(1)
    yield
    proc.kill()
    # Note: coverage is not being calculated properly
    # TODO(decfox): https://pytest-cov.readthedocs.io/en/latest/subprocess-support.html
    proc.join()


@pytest.mark.skip("TODO(decfox): fix integration test")
def test_integration(server):
    with httpx.Client(base_url=f"http://127.0.0.1:{LISTEN_PORT}") as client:
        r = client.get("/version")
        assert r.status_code == 200
        r = client.get("/api/v2/incidents/search")
        j = r.json()
        assert isinstance(j["incidents"], list)
