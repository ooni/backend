"""Add expiration_date, color columns. Drop is_archived column.

Revision ID: 836b3451a168
Revises: f96cf47f2791
Create Date: 2024-02-27 09:44:26.833238

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "836b3451a168"
down_revision: Union[str, None] = "f96cf47f2791"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "oonirun", sa.Column("expiration_date", sa.DateTime(), nullable=False)
    )
    op.add_column("oonirun", sa.Column("color", sa.String(), nullable=True))
    op.drop_column("oonirun", "is_archived")


def downgrade() -> None:
    op.drop_column("oonirun", "expiration_date")
    op.drop_column("oonirun", "color")
