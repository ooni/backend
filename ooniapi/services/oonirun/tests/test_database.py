from copy import deepcopy
from datetime import datetime
import pathlib
from oonirun.routers.v2 import utcnow_seconds
import pytest

import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from oonirun import models
from sqlalchemy import create_engine

SAMPLE_OONIRUN = {
    "name": "",
    "name_intl": {},
    "description": "integ-test description in English",
    "description_intl": {
        "es": "integ-test descripción en español",
    },
    "short_description": "integ-test short description in English",
    "short_description_intl": {
        "it": "integ-test descrizione breve in italiano",
    },
    "icon": "myicon",
    "author": "integ-test author",
    "nettests": [
        {
            "inputs": [
                "https://example.com/",
                "https://ooni.org/",
            ],
            "options": {
                "HTTP3Enabled": True,
            },
            "is_background_run_enabled_default": False,
            "is_manual_run_enabled_default": False,
            "test_name": "web_connectivity",
        },
        {
            "inputs": [],
            "options": {},
            "is_background_run_enabled_default": False,
            "is_manual_run_enabled_default": False,
            "test_name": "dnscheck",
        },
        {
            "targets_name": "sample_target",
            "options": {},
            "is_background_run_enabled_default": False,
            "is_manual_run_enabled_default": False,
            "test_name": "dnscheck",
        },
        {
            "inputs": [
                "https://example.com/",
                "https://ooni.org/",
            ],
            "inputs_extra": [{"category_code": "HUMR"}, {}],
            "options": {},
            "is_background_run_enabled_default": False,
            "is_manual_run_enabled_default": False,
            "test_name": "dnscheck",
        },
    ],
}


def config_alembic(db_url):
    from alembic.config import Config

    migrations_path = (
        pathlib.Path(__file__).parent.parent / "src" / "oonirun" / "common" / "alembic"
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

    run_link = deepcopy(SAMPLE_OONIRUN)
    nettests = run_link.pop("nettests")

    new_row = db.query(models.OONIRunLink).first()

    db_runlink = models.OONIRunLink(
        **run_link,
        oonirun_link_id="000000000",
        date_created=utcnow_seconds(),
        date_updated=utcnow_seconds(),
        expiration_date=utcnow_seconds(),
        creator_account_id="000000000",
    )
    db_runlink.nettests = [
        models.OONIRunLinkNettest(
            **nettests[0],
            revision=1,
            nettest_index=0,
            date_created=utcnow_seconds(),
        ),
        models.OONIRunLinkNettest(
            **nettests[1],
            revision=1,
            nettest_index=1,
            date_created=utcnow_seconds(),
        ),
        models.OONIRunLinkNettest(
            **nettests[1],
            revision=2,
            nettest_index=0,
            date_created=utcnow_seconds(),
        ),
        models.OONIRunLinkNettest(
            **nettests[1],
            revision=3,
            nettest_index=0,
            date_created=utcnow_seconds(),
        ),
        models.OONIRunLinkNettest(
            **nettests[2],
            revision=1,
            nettest_index=2,
            date_created=utcnow_seconds(),
        ),
        models.OONIRunLinkNettest(
            **nettests[3],
            revision=1,
            nettest_index=3,
            date_created=utcnow_seconds(),
        ),
    ]
    db.add(db_runlink)
    db.commit()

    new_row = db.query(models.OONIRunLink).first()
    assert new_row
    assert (
        new_row.nettests[0].revision == 3
    ), "First one to show up should have the latest revision"

    db.close()

    with pytest.raises(sa.exc.StatementError):
        db_runlink = models.OONIRunLink(
            **run_link,
            oonirun_link_id="000000000",
            date_created="NOT A DATE",
            date_updated=utcnow_seconds(),
            expiration_date=utcnow_seconds(),
            creator_account_id="000000000",
        )
        db.add(db_runlink)
        db.commit()
    db.rollback()

    with pytest.raises(sa.exc.StatementError):
        naive_datetime = datetime.now()
        db_runlink = models.OONIRunLink(
            **run_link,
            oonirun_link_id="000000000",
            date_created=naive_datetime,
            date_updated=utcnow_seconds(),
            expiration_date=utcnow_seconds(),
            creator_account_id="000000000",
        )
        db.add(db_runlink)
        db.commit()
    db.rollback()

    with pytest.raises(sa.exc.StatementError):
        db_runlink = models.OONIRunLink(
            **run_link,
            oonirun_link_id="000000000",
            date_created=None,
            date_updated=utcnow_seconds(),
            expiration_date=utcnow_seconds(),
            creator_account_id="000000000",
        )
        db.add(db_runlink)
        db.commit()
    db.rollback()
