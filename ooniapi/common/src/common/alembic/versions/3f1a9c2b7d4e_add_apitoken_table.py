"""add apitoken table

Revision ID: 3f1a9c2b7d4e
Revises: 87f0bcd3dea6
Create Date: 2026-11-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3f1a9c2b7d4e"
down_revision: Union[str, None] = "87f0bcd3dea6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "apitoken",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "date_created",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_id", sa.String(), nullable=False),
    )
    op.create_index("ix_apitoken_user_id", "apitoken", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_apitoken_user_id", table_name="apitoken")
    op.drop_table("apitoken")
