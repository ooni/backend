from typing import Any, Dict
from httpx import Client

def getj(client : Client, url : str, params : Dict[str, Any] | None = None, expected_code: int = 200, headers : Dict[str, Any] | None = None) -> Dict[str, Any]:
    resp = client.get(url, params=params, headers=headers)
    assert resp.status_code == expected_code, f"Unexpected status code: {resp.status_code}. {resp.content}"
    return resp.json()

def postj(client : Client, url : str, json : Dict[str, Any] | None = None, expected_code: int = 200, headers : Dict[str, Any] | None = None) -> Dict[str, Any]:
    resp = client.post(url, json=json, headers=headers)
    assert resp.status_code == expected_code, f"Unexpected status code: {resp.status_code}. {resp.content}"
    return resp.json()

def putj(client : Client, url : str, json : Dict[str, Any] | None = None, expected_code: int = 200, headers : Dict[str, Any] | None = None) -> Dict[str, Any]:
    resp = client.put(url, json=json, headers=headers)
    assert resp.status_code == expected_code, f"Unexpected status code: {resp.status_code}. {resp.content}"
    return resp.json()
