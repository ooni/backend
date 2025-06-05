"""Add targets_name and inputs_extra columns to oonirun_nettest

Revision ID: b860eb79750f
Revises: 8e7ecea5c2f5
Create Date: 2025-05-21 15:44:32.959349

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b860eb79750f"
down_revision: Union[str, None] = "8e7ecea5c2f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "oonirun_nettest", sa.Column("targets_name", sa.String(), nullable=True)
    )
    op.add_column(
        "oonirun_nettest", sa.Column("inputs_extra", sa.ARRAY(sa.JSON()), nullable=True)
    )
    op.drop_column("oonirun_nettest", "backend_options")
    op.drop_column("oonirun_nettest", "options")


def downgrade() -> None:
    op.drop_column("oonirun_nettest", "targets_name")
    op.drop_column("oonirun_nettest", "inputs_extra")
