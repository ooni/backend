from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from fastapi import HTTPException, Header
from .utils import get_client_token
from .config import Settings


@lru_cache
def get_settings() -> Settings:
    return Settings()


def role_required(roles: list[str]):
    """Wrapped function requiring user to be logged in and have the right role."""

    # Also:
    #  explicitely set no-cache headers
    #  apply the cross_origin decorator to:
    #    - set CORS header to a trusted URL
    #    - enable credentials (cookies)
    #
    async def verify_jwt(
        settings: Annotated[Settings, Depends(get_settings)],
        authorization: str = Header("authorization"),
    ):
        try:
            tok = get_client_token(authorization, settings.jwt_encryption_key)
        except:
            raise HTTPException(detail="Authentication required", status_code=401)
        if tok["role"] not in roles:
            raise HTTPException(detail="Role not authorized", status_code=401)

        return tok
        # TODO(art): we don't check for the session_expunge table yet. It's empty so the impact is none
        # query = """SELECT threshold
        #    FROM session_expunge
        #    WHERE account_id = :account_id """
        # account_id = tok["account_id"]
        # query_params = dict(account_id=account_id)
        # row = query_click_one_row(sql.text(query), query_params)
        # if row:
        #    threshold = row["threshold"]
        #    iat = datetime.utcfromtimestamp(tok["iat"])
        #    if iat < threshold:
        #        return jerror("Authentication token expired", 401)

        # If needed we can add here a 2-tier expiration time: long for
        # /api/v1/user_refresh_token and short for everything else

    return verify_jwt
