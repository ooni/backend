import hashlib
from typing import Optional, Dict, Any 
import jwt


def hash_email_address(email_address: str, key: str) -> str:
    em = email_address.encode()
    return hashlib.blake2b(em, key=key.encode("utf-8"), digest_size=16).hexdigest()


def check_email_address(
    authorization: str,
    jwt_encryption_key: str,
    email_address: str,
    key: str
) -> bool:
    account_id = get_account_id_or_raise(authorization, jwt_encryption_key=jwt_encryption_key)
    hashed = hash_email_address(email_address, key=key)
    if account_id == hashed:
        return True
    return False


def decode_jwt(token: str, key: str, **kw) -> Dict[str, Any]:
    tok = jwt.decode(token, key, algorithms=["HS256"], **kw)
    return tok


def create_jwt(payload: dict, key: str) -> str:
    token = jwt.encode(payload, key, algorithm="HS256")
    if isinstance(token, bytes):
        return token.decode()
    else:
        return token


def get_client_token(authorization: str, jwt_encryption_key: str):
    try:
        assert authorization.startswith("Bearer ")
        token = authorization[7:]
        return decode_jwt(token, audience="user_auth", key=jwt_encryption_key)
    except:
        return None


def get_client_role(authorization: str, jwt_encryption_key: str) -> str:
    """Raise exception for unlogged users"""
    tok = get_client_token(authorization, jwt_encryption_key)
    try:
        assert tok
        return tok["role"]
    except:
        return None

def get_account_id_or_none(
    authorization: str, jwt_encryption_key: str
) -> Optional[str]:
    """Returns None for unlogged users"""
    tok = get_client_token(authorization, jwt_encryption_key)
    if tok:
        return tok["account_id"]
    return None


def get_account_id_or_raise(authorization: str, jwt_encryption_key: str) -> str:
    """Raise exception for unlogged users"""
    tok = get_client_token(authorization, jwt_encryption_key)
    if tok:
        return tok["account_id"]
    raise Exception
