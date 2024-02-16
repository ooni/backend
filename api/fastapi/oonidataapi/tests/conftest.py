import pytest

import time
import jwt
from pathlib import Path

from fastapi.testclient import TestClient

from ..config import settings
from ..main import app
from ..dependencies import get_postgresql_session
from .. import models

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def setup_db(db_url):
    from alembic import command
    from alembic.config import Config

    migrations_path = (Path(__file__).parent.parent / "alembic").resolve()

    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", str(migrations_path))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    print(migrations_path)
    print(db_url)

    ret = command.upgrade(alembic_cfg, "head")
    print(ret)


def override_pg(db_url):
    def f():
        engine = create_engine(db_url, connect_args={"check_same_thread": False})
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    return f


@pytest.fixture
def postgresql(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("oonidb") / "db.sqlite3"
    db_url = f"sqlite:///{db_path}"

    setup_db(db_url)
    app.dependency_overrides[get_postgresql_session] = override_pg(db_url)
    yield


@pytest.fixture
def client(postgresql):
    client = TestClient(app)
    return client


def create_jwt(payload: dict) -> str:
    key = settings.jwt_encryption_key
    token = jwt.encode(payload, key, algorithm="HS256")
    if isinstance(token, bytes):
        return token.decode()
    else:
        return token


def create_session_token(account_id: str, role: str, login_time=None) -> str:
    now = int(time.time())
    if login_time is None:
        login_time = now
    payload = {
        "nbf": now,
        "iat": now,
        "exp": now + 10 * 86400,
        "aud": "user_auth",
        "account_id": account_id,
        "login_time": login_time,
        "role": role,
    }
    return create_jwt(payload)


@pytest.fixture
def client_with_user_role(client):
    client = TestClient(app)
    jwt_token = create_session_token("0" * 16, "user")
    client.headers = {"Authorization": f"Bearer {jwt_token}"}
    yield client


@pytest.fixture
def client_with_admin_role(client):
    client = TestClient(app)
    jwt_token = create_session_token("0" * 16, "admin")
    client.headers = {"Authorization": f"Bearer {jwt_token}"}
    yield client
