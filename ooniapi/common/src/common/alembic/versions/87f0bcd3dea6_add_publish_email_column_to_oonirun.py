"""add publish_email column to oonirun

Revision ID: 87f0bcd3dea6
Revises: b860eb79750f
Create Date: 2026-09-18 14:27:05.598053

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '87f0bcd3dea6'
down_revision: Union[str, None] = 'b860eb79750f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "oonirun",
        sa.Column(
            "publish_email",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("oonirun", "publish_email")
