import pytest

from ooniprobe.common import auth


@pytest.mark.asyncio
async def test_tor_targets(client, jwt_encryption_key):
    tok = auth.create_jwt({"registration_time": None, "aud": "probe_token"}, key=jwt_encryption_key)
    resp = client.get("/api/v1/test-list/tor-targets", headers={"Authorization": f"Bearer {tok}"}).json()
    for i, target in resp.items():
        assert i is not None
        for k in ["address", "fingerprint", "name", "protocol"]:
            assert k in target
