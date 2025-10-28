from typing import Dict, Any
import httpx
from datetime import datetime
import pytest


def getj(
    client: httpx.Client, url: str, params: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    resp = client.get(url, params=params)
    assert resp.status_code == 200, (
        f"Unexpected status code: {resp.status_code}. {resp.content}"
    )
    return resp.json()

# reasonable default since and until for the testing data
since = datetime(2025, 10, 1)
until = datetime(2025, 11, 1)

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

    assert 'results' in resp, resp
    assert len(resp['results']) > 0, resp['results']

def normalize_asn(asn: int | str):
    if isinstance(asn, int):
        return asn
    if isinstance(asn, str) and asn.upper().startswith('AS'):
        asn = asn.upper().strip("AS")

    return int(asn)

@pytest.mark.parametrize(
    "filter_param, filter_value",
    [
        ("probe_asn", 8048),
        ("probe_asn", "AS8048"),# filter asn by string is also valid
        ("probe_asn", "8048"),
        ("probe_cc", "VE"),
        ("domain", "google.com")
    ],
)
def test_changepoint_filter_basic(client, filter_param, filter_value):

    # Check filtering by cc
    resp = getjsu(
        client,
        "/api/v1/detector/chagepoints",
        params={
            filter_param : filter_value
        }
    )

    assert len(resp['results']) > 0, "No results to validate"

    if filter_param == "probe_asn":
        assert all(r[filter_param] == normalize_asn(filter_value) for r in resp['results']), resp['results']
    else:
        assert all(r[filter_param] == filter_value for r in resp['results']), resp['results']
