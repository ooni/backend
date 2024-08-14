from copy import deepcopy
from datetime import datetime, timedelta
import pathlib
import pytest

import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

from oonifindings import models
from oonifindings.routers.v1 import utcnow_seconds

sample_start_time = (utcnow_seconds() + timedelta(minutes=-1))

SAMPLE_EMAIL = "sample@i.org"

SAMPLE_OONIFINDING = {
    "title": "sample oonifinding",
    "short_description": "sample oonifinding description",
    "reported_by": "sample user",
    "email_address": SAMPLE_EMAIL,
    "text": "this is a sample oonifinding incident",
    "published": 0,
    "event_type": "incident",
    "start_time": sample_start_time,
    "asns": [],
    "country_codes": [
        "IN", "TZ",
    ],
    "tags": [],
    "test_names": [
        "webconnectivity",
    ],
    "domains": [
        "www.google.com"
    ],
    "links": []
}

def config_alembic(db_url):
    from alembic.config import Config

    migrations_path = (
        pathlib.Path(__file__).parent.parent / "src" / "oonifindings" / "common" / "alembic"
    ).resolve()

    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", str(migrations_path))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    return alembic_cfg


def upgrade_to_head(db_url):
    from alembic import command

    command.upgrade(config_alembic(db_url), "head")


def get_db(pg_url):
    engine = create_engine(pg_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    return SessionLocal()


def test_downgrade(postgresql):
    from alembic import command

    db_url = f"postgresql://{postgresql.info.user}:@{postgresql.info.host}:{postgresql.info.port}/{postgresql.info.dbname}"

    command.upgrade(config_alembic(db_url), "head")
    command.downgrade(config_alembic(db_url), "-1")


def test_upgrade_to_head(postgresql):
    db_url = f"postgresql://{postgresql.info.user}:@{postgresql.info.host}:{postgresql.info.port}/{postgresql.info.dbname}"
    upgrade_to_head(db_url)
    db = get_db(db_url)

    finding = deepcopy(SAMPLE_OONIFINDING)

    new_row = db.query(models.OONIFinding).first()

    db_finding = models.OONIFinding(
        **finding,
        finding_id="000000000",
        finding_slug="2024-07-sample-finding",
        create_time=utcnow_seconds(),
        update_time=utcnow_seconds(),
        creator_account_id="000000000",
    )
    db.add(db_finding)
    db.commit()

    new_row = db.query(models.OONIFinding).first()
    assert new_row

    db.close()

    with pytest.raises(sa.exc.StatementError):
        db_finding = models.OONIFinding(
            **finding,
            finding_id="000000000",
            finding_slug="2024-07-sample-finding",
            create_time="NOT A DATE",
            update_time=utcnow_seconds(),
            creator_account_id="000000000",
        )
        db.add(db_finding)
        db.commit()
    db.rollback()

    with pytest.raises(sa.exc.StatementError):
        naive_datetime = datetime.now()
        db_finding = models.OONIFinding(
            **finding,
            finding_id="000000000",
            finding_slug="2024-07-sample-finding",
            create_time=naive_datetime,
            update_time=utcnow_seconds(),
            creator_account_id="000000000",
        )
        db.add(db_finding)
        db.commit()
    db.rollback()

    with pytest.raises(sa.exc.StatementError):
        db_finding = models.OONIFinding(
            **finding,
            finding_id="000000000",
            finding_slug="2024-07-sample-finding",
            create_time=None,
            update_time=utcnow_seconds(),
            creator_account_id="000000000",
        )
        db.add(db_finding)
        db.commit()
    db.rollback()
