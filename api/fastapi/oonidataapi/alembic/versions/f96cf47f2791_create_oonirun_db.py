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
        sa.Column("ooni_run_link_id", sa.Integer, primary_key=True),
        sa.Column("descriptor_creation_time", sa.DateTime(), nullable=False),
        sa.Column("translation_creation_time", sa.DateTime(), nullable=False),
        sa.Column("is_archived", sa.Boolean()),
        sa.Column("descriptor", sa.String()),
        sa.Column("author", sa.String()),
        sa.Column("name", sa.String()),
        sa.Column("short_description", sa.String()),
        sa.Column("icon", sa.String()),
    )


def downgrade() -> None:
    op.drop_table("oonirun")
