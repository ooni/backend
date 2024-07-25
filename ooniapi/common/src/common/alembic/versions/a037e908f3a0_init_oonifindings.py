"""init oonifindings

Revision ID: a037e908f3a0
Revises: c9119c05cf42
Create Date: 2024-07-17 16:45:25.752551

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a037e908f3a0'
down_revision: Union[str, None] = "c9119c05cf42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "oonifinding",
        sa.Column(
            "finding_id",
            sa.String(),
            nullable=False,
            primary_key=True,
        ),
        sa.Column("finding_slug", sa.String(), nullable=True),
        sa.Column("create_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("update_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("creator_account_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("short_description", sa.String(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("reported_by", sa.String(), nullable=False),
        sa.Column("email_address", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("published", sa.Integer(), nullable=False),
        sa.Column("deleted", sa.Integer(), nullable=False, default=0),
        sa.Column("country_codes", sa.JSON(), nullable=True),
        sa.Column("asns", sa.JSON(), nullable=True),
        sa.Column("domains", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("links", sa.JSON(), nullable=True),
        sa.Column("test_names", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("oonifinding")
