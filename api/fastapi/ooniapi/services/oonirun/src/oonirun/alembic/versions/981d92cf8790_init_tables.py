"""init tables

Revision ID: 981d92cf8790
Revises: 
Create Date: 2024-03-11 08:03:55.462815

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.schema import Sequence, CreateSequence

# revision identifiers, used by Alembic.
revision: str = "981d92cf8790"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(CreateSequence(Sequence("oonirun_link_id_seq", start=10_000)))

    oonirun_link_id_seq = Sequence("oonirun_link_id_seq")

    op.create_table(
        "oonirun",
        sa.Column(
            "oonirun_link_id",
            sa.String(),
            nullable=False,
            server_default=oonirun_link_id_seq.next_value(),
            primary_key=True,
        ),
        sa.Column("date_created", sa.DateTime(timezone=True), nullable=False),
        sa.Column("date_updated", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creator_account_id", sa.String(), nullable=False),
        sa.Column("expiration_date", sa.DateTime(timezone=True), nullable=False),
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

    op.create_table(
        "oonirun_nettest",
        sa.Column("oonirun_link_id", sa.String(), nullable=False),
        sa.Column(
            "revision", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column(
            "nettest_index", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("date_created", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["oonirun_link_id"],
            ["oonirun.oonirun_link_id"],
        ),
    )


def downgrade() -> None:
    op.drop_table("oonirun")
    op.drop_table("oonirun_nettest")
