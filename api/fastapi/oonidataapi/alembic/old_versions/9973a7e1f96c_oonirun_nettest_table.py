"""oonirun_nettest table

Revision ID: 9973a7e1f96c
Revises: 7d5841cb9549
Create Date: 2024-03-08 14:38:53.154821

"""

from datetime import datetime, timezone
from collections import defaultdict
from typing import Dict, List, Sequence, Union, Any
from copy import deepcopy

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from sqlalchemy.orm import Session, DeclarativeBase
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship


# revision identifiers, used by Alembic.
revision: str = "9973a7e1f96c"
down_revision: Union[str, None] = "7d5841cb9549"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


oonirun_nettest_table = table(
    "oonirun_nettest",
    sa.Column("oonirun_link_id", sa.String(), nullable=False),
    sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("1")),
    sa.Column(
        "nettest_index", sa.Integer(), nullable=False, server_default=sa.text("1")
    ),
    sa.Column("date_created", sa.DateTime(), nullable=True),
    sa.Column("test_name", sa.String(), nullable=True),
    sa.Column("inputs", sa.JSON(), nullable=True),
    sa.Column("options", sa.JSON(), nullable=True),
    sa.Column("backend_options", sa.JSON(), nullable=True),
    sa.Column(
        "is_background_run_enabled_default",
        sa.Boolean(),
        nullable=True,
        server_default=sa.text("false"),
    ),
    sa.Column(
        "is_manual_run_enabled_default",
        sa.Boolean(),
        nullable=True,
        server_default=sa.text("false"),
    ),
)


def upgrade() -> None:
    op.create_table(
        "oonirun_nettest",
        sa.Column("oonirun_link_id", sa.String(), nullable=False),
        sa.Column(
            "revision", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column(
            "nettest_index", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("date_created", sa.DateTime(), nullable=True),
        sa.Column("test_name", sa.String(), nullable=True),
        sa.Column("inputs", sa.JSON(), nullable=True),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("backend_options", sa.JSON(), nullable=True),
        sa.Column(
            "is_background_run_enabled_default",
            sa.Boolean(),
            nullable=True,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_manual_run_enabled_default",
            sa.Boolean(),
            nullable=True,
            server_default=sa.text("false"),
        ),
        sa.PrimaryKeyConstraint("oonirun_link_id", "revision", "nettest_index"),
    )

    bind = op.get_bind()
    session = Session(bind=bind)
    oonirun_rows = session.execute(
        sa.select(
            column("oonirun_link_id", sa.String),
            column("revision", sa.Integer),
            column("nettests", sa.JSON),
            column("date_created", sa.DateTime),
        ).select_from(table("oonirun"))
    ).fetchall()

    for record in oonirun_rows:
        nettests_data = record.nettests
        for index, nettest in enumerate(nettests_data):
            nettest = dict(
                oonirun_link_id=record.oonirun_link_id,
                revision=record.revision,
                nettest_index=index,
                date_created=record.date_created,
                test_name=nettest["test_name"],
                inputs=nettest.get("inputs", []),
                options=nettest.get("options", {}),
                backend_options=nettest.get("backend_options", {}),
                is_background_run_enabled_default=nettest.get(
                    "is_background_run_enabled", False
                ),
                is_manual_run_enabled_default=nettest.get(
                    "is_manual_run_enabled", False
                ),
            )
            print(nettest)
            session.execute(oonirun_nettest_table.insert().values(**nettest))
    session.commit()

    tmp_table_name = "tmp__oonirun_new"
    op.create_table(
        tmp_table_name,
        sa.Column("oonirun_link_id", sa.String(), nullable=False, primary_key=True),
        sa.Column("date_created", sa.DateTime(), nullable=False),
        sa.Column("date_updated", sa.DateTime(), nullable=False),
        sa.Column("creator_account_id", sa.String(), nullable=False),
        sa.Column("expiration_date", sa.DateTime(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("short_description", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("author", sa.String(), nullable=True),
        sa.Column("icon", sa.String(), nullable=True),
        sa.Column("color", sa.String(), nullable=True),
        sa.Column("name_intl", sa.JSON(), nullable=True),
        sa.Column("short_description_intl", sa.JSON(), nullable=True),
        sa.Column("description_intl", sa.JSON(), nullable=True),
    )
    conn = op.get_bind()
    # This SQL query is to deduplicate the oonirun link rows such that we can
    # have the highest revision kept so we have the latest metadata for the row
    conn.execute(
        sa.text(
            f"""
        INSERT INTO {tmp_table_name} (oonirun_link_id, date_created,
        date_updated, creator_account_id, expiration_date, name,
        short_description, description, author, icon, color, name_intl,
        short_description_intl, description_intl)
        SELECT oonirun_link_id, date_created,
        date_updated, creator_account_id, expiration_date, name,
        short_description, description, author, icon, color, name_intl,
        short_description_intl, description_intl
        FROM (
            SELECT oonirun_link_id, date_created,
        date_updated, creator_account_id, expiration_date, name,
        short_description, description, author, icon, color, name_intl,
        short_description_intl, description_intl, ROW_NUMBER() OVER (PARTITION BY oonirun_link_id ORDER BY revision DESC) AS rn
            FROM oonirun
        ) sub
        WHERE rn = 1
        """
        )
    )
    op.drop_table("oonirun")
    # We then swap these deduplcated table with the new one
    op.rename_table(tmp_table_name, "oonirun")

    op.create_foreign_key(
        "fk_oonirun_nettest_oonirun_link_id",
        "oonirun_nettest",
        "oonirun",
        ["oonirun_link_id"],
        ["oonirun_link_id"],
    )


def downgrade() -> None:
    """
    XXX This migration is not reversible.

    If you really must do it, check below for code that might work with some massaging.

    op.add_column(
        "oonirun",
        sa.Column(
            "revision",
            sa.INTEGER(),
            autoincrement=False,
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "oonirun",
        sa.Column("nettests", sa.JSON(), nullable=False, server_default="{}"),
    )

    bind = op.get_bind()
    session = Session(bind=bind)

    # Select distinct `oonirun_link_id` to iterate through each `oonirun` record
    distinct_ids = session.execute(
        sa.select(column("oonirun_link_id").distinct()).select_from(table("oonirun"))
    ).fetchall()

    for oonirun_link_id in distinct_ids:
        # Fetch nettest records for each `oonirun_link_id`
        nettest_records = session.execute(
            sa.select(oonirun_nettest_table)
            .where(
                oonirun_nettest_table.c.oonirun_link_id
                == oonirun_link_id.oonirun_link_id
            )
            .order_by(
                oonirun_nettest_table.c.revision, oonirun_nettest_table.c.nettest_index
            )
        ).fetchall()

        # Construct the JSON structure from the nettest records
        records_by_revision: Dict[int, List] = defaultdict(list)
        for record in nettest_records:
            inputs = []
            for d in record.test_inputs:
                if d:
                    # Kind of ghetto, but anyways we were just handling "url" in the upgrade, so it's better than nothing
                    inputs.append(list(d.values())[0])
            nettests_json = {
                "test_name": record.test_name,
                "options": record.test_options,
                "backend_options": record.backend_config,
                "is_background_run_enabled": record.is_background_run_enabled_default,
                "is_manual_run_enabled": record.is_manual_run_enabled_default,
                "inputs": inputs,
            }
            records_by_revision[record.revision].append(nettests_json)

        existing_run_link = session.execute(
            sa.select(OONIRunLink).where(OONIRunLink.oonirun_link_id == oonirun_link_id)
        ).one()
        print(existing_run_link)

        existing_run_link.nettests = records_by_revision.pop(existing_run_link.revision)
        session.commit()

        for revision, nettests in records_by_revision.items():
            new_oonirun_link = deepcopy(existing_run_link)
            session.expunge(new_oonirun_link)
            new_oonirun_link.nettests = nettests
            new_oonirun_link.revision = revision
            session.add(new_oonirun_link)
        session.commit()

    op.drop_table("oonirun_nettest")
    """
    raise Exception("This migration is not reversible.")
