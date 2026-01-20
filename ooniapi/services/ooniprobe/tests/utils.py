from httpx import Client
from typing import Dict, Any, Tuple
from fastapi import status
from ooniauth_py import UserState

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

def setup_user(client) -> Tuple[UserState, str, int]: # user, manifest version, emission day
    manifest = getj(client, "/api/v1/manifest")
    user = UserState(manifest['manifest']['public_parameters'])
    req = user.make_registration_request()
    resp = postj(client, "/api/v1/sign_credential", json = {
        "credential_sign_request" : req,
        "manifest_version" : manifest['meta']['version']
    })
    user.handle_registration_response(resp['credential_sign_response'])

    return (user, manifest['meta']['version'], resp['emission_day'])
