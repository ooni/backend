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
