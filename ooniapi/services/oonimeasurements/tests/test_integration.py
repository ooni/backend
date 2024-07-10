import os
import time
import random

from multiprocessing import Process

import httpx
import pytest
import uvicorn


LISTEN_PORT = random.randint(30_000, 42_000)


@pytest.fixture
def server(clickhouse_server):
    os.environ["CLICKHOUSE_URL"] = clickhouse_server
    proc = Process(
        target=uvicorn.run,
        args=("oonimeasurements.main:app"),
        kwargs={"host": "127.0.0.1", "port": LISTEN_PORT, "log_level": "info"},
        daemon=True,
    )

    proc.start()
    # Give it as second to start
    time.sleep(1)
    yield
    proc.kill()
    # Note: coverage is not being calculated properly
    # TODO(art): https://pytest-cov.readthedocs.io/en/latest/subprocess-support.html
    proc.join()


@pytest.mark.skip("TODO(decfox): fix integration test")
def test_integration(server):
    with httpx.Client(base_url=f"http://127.0.0.1:{LISTEN_PORT}") as client:
        r = client.get("/version")
        assert r.status_code == 200
        # TODO(decfox): add dedicated endpoint for integration test
