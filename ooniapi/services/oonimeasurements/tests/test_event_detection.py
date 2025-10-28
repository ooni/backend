from typing import Dict, Any
import httpx
from datetime import datetime


def getj(
    client: httpx.Client, url: str, params: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    resp = client.get(url, params=params)
    assert resp.status_code == 200, (
        f"Unexpected status code: {resp.status_code}. {resp.content}"
    )
    return resp.json()


def test_changepoint_list(client):
    resp = getj(
        client,
        "/api/v1/detector/chagepoints",
        params={
            "probe_cc": "VE",
            "probe_asn": "AS8048",
            "domain": "google.com",
            "since" : datetime(2025, 10, 1),
            "until" : datetime(2025, 11, 1)
            },
    )
