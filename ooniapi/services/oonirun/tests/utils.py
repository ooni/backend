from typing import Any, Dict
from httpx import Client

def get(client : Client, url : str, params : Dict[str, Any] | None = None, expected_code: int = 200) -> Dict[str, Any]:
    resp = client.get(url, params=params)
    assert resp.status_code == expected_code, f"Unexpected status code: {resp.status_code}. {resp.content}"
    return resp.json()

def post(client : Client, url : str, json : Dict[str, Any] | None = None, expected_code: int = 200) -> Dict[str, Any]:
    resp = client.post(url, json=json)
    assert resp.status_code == expected_code, f"Unexpected status code: {resp.status_code}. {resp.content}"
    return resp.json()

def put(client : Client, url : str, json : Dict[str, Any] | None = None, expected_code: int = 200) -> Dict[str, Any]:
    resp = client.put(url, json=json)
    assert resp.status_code == expected_code, f"Unexpected status code: {resp.status_code}. {resp.content}"
    return resp.json()