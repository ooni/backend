from httpx import Client
from typing import Dict, Any
from fastapi import status

def getj(client : Client, url: str, params: Dict[str, Any] = {}) -> Dict[str, Any]:
    resp = client.get(url)
    assert resp.status_code == status.HTTP_200_OK, f"Unexpected status code: {resp.status_code} - {url}. {resp.content}"
    return resp.json()

def postj(
        client : Client,
        url: str,
        json: Dict[str, Any] | None = None,
        headers: Dict[str, Any] | None = None
        ) -> Dict[str, Any]:
    resp = client.post(url, json=json, headers=headers)
    assert resp.status_code == status.HTTP_200_OK, f"Unexpected status code: {resp.status_code} - {url}. {resp.content}"
    return resp.json()

def post(client : Client, url, data=None, headers=None):
    response = client.post(url, data=data, headers=headers)
    assert response.status_code == 200
    return response.json()