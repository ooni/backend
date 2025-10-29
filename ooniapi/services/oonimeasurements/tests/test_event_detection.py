from typing import Dict, Any
import httpx
from datetime import datetime, UTC
import pytest


def getj(
    client: httpx.Client, url: str, params: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    resp = client.get(url, params=params)
    assert (
        resp.status_code == 200
    ), f"Unexpected status code: {resp.status_code}. {resp.content}"
    return resp.json()


# reasonable default since and until for the testing data
since = datetime(2025, 10, 1, tzinfo=UTC)
until = datetime(2025, 11, 1, tzinfo=UTC)


def getjsu(client, url, params={}):
    # use this default since and until
    # since the testing data has a fixed date that might
    # become "obsolete" in the future for the default
    # '30 days ago' since and until limits
    params["since"] = since
    params["until"] = until
    return getj(client, url, params)


def test_changepoint_list_basic(client):
    resp = getjsu(
        client,
        "/api/v1/detector/chagepoints",
    )

    assert "results" in resp, resp
    assert len(resp["results"]) > 0, resp["results"]


def normalize_asn(asn: int | str):
    if isinstance(asn, int):
        return asn
    if isinstance(asn, str) and asn.upper().startswith("AS"):
        asn = asn.upper().strip("AS")

    return int(asn)


def parse_dt(dt: str) -> datetime:
    return datetime.fromisoformat(dt)


@pytest.mark.parametrize(
    "filter_param, filter_value",
    [
        ("probe_asn", 8048),
        ("probe_asn", "AS8048"),  # filter asn by string is also valid
        ("probe_asn", "8048"),
        ("probe_cc", "VE"),
        ("domain", "google.com"),
    ],
)
def test_changepoint_filter_basic(client, filter_param, filter_value):

    resp = getjsu(
        client, "/api/v1/detector/chagepoints", params={filter_param: filter_value}
    )

    assert len(resp["results"]) > 0, "No results to validate"

    if filter_param == "probe_asn":
        normalize = normalize_asn
    else:
        normalize = id

    if filter_param == "probe_asn":
        for r in resp["results"]:
            assert r[filter_param] == normalize(filter_value), r


@pytest.mark.parametrize(
    "since_param, until_param, expect_emtpy",
    [
        (since, until, False),
        (datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 30, tzinfo=UTC), True),
    ],
)
def test_changepoint_date_filter(client, since_param, until_param, expect_emtpy):

    resp = getj(
        client,
        "/api/v1/detector/chagepoints",
        params={"since": since_param, "until": until_param},
    )

    assert len(resp["results"]) > 0 or expect_emtpy, "Not enough results to validate"
    assert len(resp["results"]) == 0 or not expect_emtpy, "Result should be empty"

    for r in resp["results"]:
        assert parse_dt(r["start_time"]) >= since, r["start_time"]
        assert parse_dt(r["end_time"]) <= until, r["end_time"]


def test_changepoint_change_dir_values(client):

    resp = getjsu(
        client,
        "/api/v1/detector/chagepoints",
    )

    assert len(resp["results"]) > 0, "Not enough data to validate"
    for r in resp["results"]:
        assert r["change_dir"] in ["up", "down"]

    resp = getjsu(
        client,
        "/api/v1/detector/chagepoints",
        {"probe_cc": "VE", "probe_asn": 15169, "domain": "google.com"},
    )

    assert resp["results"][0]["change_dir"] == "down"  # this one has change_dir == -1

    resp = getjsu(
        client,
        "/api/v1/detector/chagepoints",
        {"probe_cc": "VE", "probe_asn": 8048, "domain": "amazon.com"},
    )

    assert resp["results"][0]["change_dir"] == "up"  # this one has change_dir == 1
