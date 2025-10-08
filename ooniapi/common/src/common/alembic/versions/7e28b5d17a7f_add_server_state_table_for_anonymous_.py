"""Add server state table for anonymous credentials

Revision ID: 7e28b5d17a7f
Revises: 8e7ecea5c2f5
Create Date: 2025-10-08 10:36:55.796144

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy.schema as sc


# revision identifiers, used by Alembic.
revision: str = '7e28b5d17a7f'
down_revision: Union[str, None] = '8e7ecea5c2f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ---
ooniprobe_server_state_id_seq = sc.Sequence("ooniprobe_server_state_id_seq", start=1)
def upgrade() -> None:
    op.execute(sc.CreateSequence(ooniprobe_server_state_id_seq))

    op.create_table(
        "ooniprobe_server_state",
        sa.Column(
            "id",
            sa.String(),
            nullable=False,
            server_default=ooniprobe_server_state_id_seq.next_value(),
            primary_key=True
        ),
        sa.Column("date_created", sa.DateTime(timezone=True), nullable=False),
        sa.Column("secret_key", sa.String(), nullable=False),
        sa.Column("public_parameters", sa.String(), nullable=False)
    )
    pass


def downgrade() -> None:
    op.drop_table("ooniprobe_server_state")
    op.execute(sc.DropSequence(ooniprobe_server_state_id_seq))
    pass
