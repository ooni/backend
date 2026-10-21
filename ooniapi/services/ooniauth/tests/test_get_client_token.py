import time
import jwt
import pytest
from ooniauth.common.auth import get_client_token

KEY = "k"

def tok(aud="user_auth", key=KEY, exp=60):
    now = int(time.time())
    return jwt.encode({"iat": now, "exp": now + exp, "aud": aud, "role": "user"}, key, algorithm="HS256")

def test_valid():
    assert get_client_token(f"Bearer {tok()}", KEY)["role"] == "user"

@pytest.mark.parametrize("authorization", [
    None, "", "authorization", "Bearer", "Bearer ", "Bearer notajwt",
    "Basic Zm9vOmJhcg==", f"bearer {tok()}", tok(),
    f"Bearer {tok(aud='probe_token')}", f"Bearer {tok(key='other')}", f"Bearer {tok(exp=-10)}",
])
def test_rejected(authorization):
    assert get_client_token(authorization, KEY) is None
