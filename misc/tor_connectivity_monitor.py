#!/usr/bin/env python3

"""
A simple script that connects to ooni.org over Tor and populates a table
on ClickHouse with:
  exit node IPaddr, HTTP status code, url, timing, cc, relay fingerprint

Dependencies: See debdeps comments
"""
from time import sleep, perf_counter
import functools

# debdeps: python3-clickhouse-driver
from clickhouse_driver import Client as Clickhouse
# debdeps: python3-requests
import requests

# debdeps: python3-stem python3-socks
from stem import StreamStatus
from stem.control import EventType, Controller, Signal

"""
CREATE TABLE tor_connectivity_check
(
    `test_time` DateTime DEFAULT now(),
    `exit_node_ipaddr` String,
    `fingerprint` String,
    `cc` String,
    `url` String,
    `status_code` Int,
    `timing` Float32
)
ENGINE = ReplacingMergeTree(test_time)
ORDER BY (test_time)
SETTINGS index_granularity = 1
"""

TOR_CONTROL_PORT = 9051
# DBURL = "clickhouse://localhost/default"
DBURL = "clickhouse://api:api@localhost/default"

exit_node_ipaddr = None
cc = None
fingerprint = None


def insert(d) -> None:
    click = Clickhouse.from_url(DBURL)
    settings = {"priority": 1, "max_execution_time": 300}
    query = """
    INSERT INTO tor_connectivity_check (exit_node_ipaddr, status_code, url,
    timing, cc, fingerprint)
    VALUES
    """
    rows = [d]
    click.execute(query, rows, types_check=True, settings=settings)


def stream_event(controller, event):
    global exit_node_ipaddr, fingerprint, cc
    if event.status != StreamStatus.SUCCEEDED:
        return
    if not event.circ_id:
        return

    circ = controller.get_circuit(event.circ_id)
    exit_fingerprint = circ.path[-1][0]
    exit_relay = controller.get_network_status(exit_fingerprint)
    exit_node_ipaddr = exit_relay.address
    fingerprint = exit_relay.fingerprint
    cc = controller.get_info("ip-to-country/%s" % exit_relay.address, "unknown")


def sample(controller, url: str) -> None:
    controller.authenticate()
    controller.signal(Signal.NEWNYM)

    stream_listener = functools.partial(stream_event, controller)
    controller.add_event_listener(stream_listener, EventType.STREAM)
    session = requests.session()
    session.proxies = {
        "http": "socks5h://localhost:9050",
        "https": "socks5h://localhost:9050",
    }

    t0 = perf_counter()
    try:
        response = session.get(url)
        timing = perf_counter() - t0
        status_code = response.status_code
    except Exception as e:
        print(e)
        status_code = 900
        timing = perf_counter() - t0

    d = dict(
        status_code=status_code,
        exit_node_ipaddr=exit_node_ipaddr,
        timing=timing,
        url=url,
        cc=cc,
        fingerprint=fingerprint,
    )
    print(d)
    insert(d)


def main():
    while True:
        try:
            with Controller.from_port(port=TOR_CONTROL_PORT) as controller:
                url = "https://ooni.org"
                sample(controller, url)

        except Exception as e:
            print(e)
            pass

        sleep(60)


if __name__ == "__main__":
    main()
