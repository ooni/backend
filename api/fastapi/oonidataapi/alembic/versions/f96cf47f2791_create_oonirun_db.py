"""create oonirun db

Revision ID: f96cf47f2791
Revises: 
Create Date: 2024-02-15 14:39:47.867136

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f96cf47f2791"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "oonirun",
        sa.Column("oonirun_link_id", sa.Integer, primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("date_created", sa.DateTime(), nullable=False),
        sa.Column("date_updated", sa.DateTime(), nullable=False),
        sa.Column("creator_account_id", sa.String(), nullable=False),
        sa.Column("name", sa.String()),
        sa.Column("name_intl", sa.JSON()),
        sa.Column("short_description", sa.String()),
        sa.Column("short_description_intl", sa.JSON()),
        sa.Column("description", sa.String()),
        sa.Column("description_intl", sa.JSON()),
        sa.Column("author", sa.String()),
        sa.Column("icon", sa.String()),
        sa.Column("nettests", sa.JSON(), nullable=False),
        sa.Column("is_archived", sa.Boolean()),
    )


def downgrade() -> None:
    op.drop_table("oonirun")
