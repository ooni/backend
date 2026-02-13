from functools import lru_cache
from typing import Annotated, TypeAlias

from clickhouse_driver import Client as Clickhouse

import boto3
from fastapi import Depends
from fastapi import HTTPException, Header
from mypy_boto3_s3 import S3Client
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from .auth import get_client_token
from .config import Settings


@lru_cache
def get_settings() -> Settings:
    return Settings()

SettingsDep: TypeAlias = Annotated[Settings, Depends(get_settings)]

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

        if not tok:
            raise HTTPException(detail="Authentication required", status_code=401)
        if tok["role"] not in roles:
            raise HTTPException(detail="Role not authorized", status_code=401)

        return tok
    
    return verify_jwt


def get_clickhouse_session(settings: SettingsDep):
    db = Clickhouse.from_url(settings.clickhouse_url)
    try:
        yield db
    finally:
        db.disconnect()


ClickhouseDep = Annotated[Clickhouse, Depends(get_clickhouse_session)]


def get_postgresql_session(settings: SettingsDep):
    engine = create_engine(settings.postgresql_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


PostgresDep = Annotated[Session, Depends(get_postgresql_session)]


def get_s3_client() -> S3Client:
    s3 = boto3.client("s3")
    return s3


S3ClientDep = Annotated[S3Client, Depends(get_s3_client)]
