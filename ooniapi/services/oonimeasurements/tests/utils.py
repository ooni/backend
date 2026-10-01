from datetime import datetime
from typing import Dict, Any
import httpx


def getj(
    client: httpx.Client, url: str, params: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    resp = client.get(url, params=params)
    assert (
        resp.status_code == 200
    ), f"Unexpected status code:  {resp.status_code}. {resp.content}"
    return resp.json()


def make_fastpath_row(
    test_name: str, name: str, ts: datetime, uid_ts: datetime | None = None
) -> Dict[str, Any]:
    """
    Build a dummy fastpath row. `uid_ts` is the timestamp used in the
    measurement_uid, it defaults to `ts`
    """
    uid_ts = uid_ts or ts
    return {
        "measurement_uid": f"{uid_ts.strftime('%Y%m%d%H%M%S')}.000000_XY_{test_name}_{name}",
        "report_id": f"report_{name}",
        "input": f"https://example-{name}.com",
        "probe_cc": "XY",
        "probe_asn": 1234,
        "test_name": test_name,
        "measurement_start_time": ts,
        "test_start_time": ts,
        "scores": "{}",
    }
