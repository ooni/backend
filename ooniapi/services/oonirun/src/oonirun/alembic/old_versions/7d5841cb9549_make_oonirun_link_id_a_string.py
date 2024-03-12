"""make oonirun link id a string

Revision ID: 7d5841cb9549
Revises: 836b3451a168
Create Date: 2024-02-28 15:41:53.811746

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7d5841cb9549"
down_revision: Union[str, None] = "836b3451a168"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE oonirun
        ALTER COLUMN oonirun_link_id TYPE TEXT USING oonirun_link_id::TEXT
    """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE oonirun
        ALTER COLUMN oonirun TYPE INTEGER USING oonirun::INTEGER
    """
    )
