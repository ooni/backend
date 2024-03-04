import time

from oonidataapi.utils import decode_jwt, create_jwt


def test_decode_jwt():
    key = "DUMMYKEY"
    now = int(time.time())
    payload = {
        "nbf": now,
        "iat": now,
        "exp": now + 2 * 60,
        "aud": "user_auth",
        "account_id": 0,
        "login_time": now,
        "role": "user",
    }
    token = create_jwt(payload, key)
    d = decode_jwt(token=token, key=key, audience="user_auth")
    assert d["role"] == "user"
    assert d["aud"] == "user_auth"
    assert d["account_id"] == 0
