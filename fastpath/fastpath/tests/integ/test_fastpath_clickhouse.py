"""
What happens to measurements between the HTTP API and ClickHouse, in the
fastpath image as deployed: they land in ooni.fastpath, a full queue answers
503 at once, and stopping the container drains the queue.
"""

import secrets
import subprocess
import threading
import time
from pathlib import Path

import pytest
import requests

MSMT = (
    Path(__file__).parent.parent
    / "data"
    / "20250527233111.802678_ID_webconnectivity_5a37ec909dbf14e3.json"
).read_bytes()


def new_uid() -> str:
    # Unique, and dated like the measurement so fastpath doesn't flag it
    return f"20250527233111.802678_ID_webconnectivity_{secrets.token_hex(8)}"


def post(fastpath_service, uid):
    return requests.post(f"{fastpath_service}/{uid}", data=MSMT, timeout=10)


def count_rows(clickhouse, uids) -> int:
    rows = clickhouse.execute(
        "SELECT count(DISTINCT measurement_uid) FROM fastpath WHERE measurement_uid IN %(uids)s",
        {"uids": list(uids)},
    )
    return rows[0][0]


def is_up(fastpath_service) -> bool:
    try:
        return requests.get(fastpath_service, timeout=2).ok
    except requests.RequestException:
        return False


def wait_for_rows(clickhouse, uids, timeout=120) -> int:
    deadline = time.monotonic() + timeout
    while True:
        n = count_rows(clickhouse, uids)
        if n == len(uids) or time.monotonic() > deadline:
            return n
        time.sleep(1)


@pytest.fixture
def paused_clickhouse(compose, docker_compose_command):
    """Pause ClickHouse: fastpath's inserts hang, as when it stops answering"""
    # By container ID: with podman, docker compose unpause leaves it paused
    engine = docker_compose_command.split()[0]
    cid = compose(
        "ps", "-a", "-q", "clickhouse-server", capture_output=True, text=True
    ).stdout.strip()
    subprocess.run([engine, "pause", cid], check=True, stdout=subprocess.DEVNULL)
    paused = [True]

    def unpause():
        if paused[0]:
            subprocess.run([engine, "unpause", cid], check=True, stdout=subprocess.DEVNULL)
            paused[0] = False

    yield unpause
    unpause()


def test_measurement_lands_in_clickhouse(fastpath_service, clickhouse):
    uid = new_uid()
    assert post(fastpath_service, uid).status_code == 200
    assert wait_for_rows(clickhouse, [uid]) == 1


def test_full_queue_answers_503_at_once(fastpath_service, clickhouse, paused_clickhouse):
    # With ClickHouse paused, each worker hangs on an insert and the queue
    # (NUM_WORKERS * 50 = 500) fills. FASTPATH_QUEUE_PUT_TIMEOUT=0 then
    # refuses measurements at once, so ooniprobe can send them elsewhere.
    accepted = []
    for _ in range(1000):
        uid = new_uid()
        t0 = time.monotonic()
        resp = post(fastpath_service, uid)
        elapsed = time.monotonic() - t0
        if resp.status_code == 503:
            assert elapsed < 1, f"a full queue took {elapsed:.1f}s to answer"
            break
        assert resp.status_code == 200
        accepted.append(uid)
    else:
        pytest.fail("the queue never filled: 1000 measurements accepted")

    assert len(accepted) >= 500

    # Every measurement fastpath accepted reaches ClickHouse once it answers
    paused_clickhouse()
    assert wait_for_rows(clickhouse, accepted) == len(accepted)


def test_stop_drains_the_queue(fastpath_service, clickhouse, compose, paused_clickhouse, docker_services):
    # Measurements still queued when the container is stopped are written
    # before it exits (ooni/backend#1326), within the stop timeout that
    # ooni/devops sets (stop_grace_period here)
    uids = [new_uid() for _ in range(50)]
    for uid in uids:
        assert post(fastpath_service, uid).status_code == 200

    stop = threading.Thread(target=compose, args=("stop", "fastpath"))
    stop.start()
    time.sleep(3)
    paused_clickhouse()
    stop.join(timeout=150)
    assert not stop.is_alive(), "fastpath didn't stop within its stop timeout"

    assert count_rows(clickhouse, uids) == len(uids)

    # Leave fastpath running for the other tests
    compose("start", "fastpath")
    docker_services.wait_until_responsive(
        timeout=60, pause=0.5, check=lambda: is_up(fastpath_service)
    )
