"""ooniprobe services

Revision ID: c9119c05cf42
Revises: 981d92cf8790
Create Date: 2024-03-22 20:41:51.940695

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.schema import Sequence, CreateSequence

# revision identifiers, used by Alembic.
revision: str = "c9119c05cf42"
down_revision: Union[str, None] = "981d92cf8790"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    ooniprobe_vpn_provider_id_seq = Sequence("ooniprobe_vpn_provider_id_seq", start=1)
    op.execute(CreateSequence(ooniprobe_vpn_provider_id_seq))

    op.create_table(
        "ooniprobe_vpn_provider",
        sa.Column(
            "id",
            sa.String(),
            nullable=False,
            server_default=ooniprobe_vpn_provider_id_seq.next_value(),
            primary_key=True,
        ),
        sa.Column("date_created", sa.DateTime(timezone=True), nullable=False),
        sa.Column("date_updated", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_name", sa.String(), nullable=False),
        sa.Column("openvpn_cert", sa.String(), nullable=True),
        sa.Column("openvpn_ca", sa.String(), nullable=False),
        sa.Column("openvpn_key", sa.String(), nullable=False),
    )

    ooniprobe_vpn_provider_endpoint_id_seq = Sequence("ooniprobe_vpn_provider_endpoint_id_seq", start=1)
    op.execute(CreateSequence(ooniprobe_vpn_provider_endpoint_id_seq))

    op.create_table(
        "ooniprobe_vpn_provider_endpoint",
        sa.Column(
            "id",
            sa.String(),
            nullable=False,
            server_default=ooniprobe_vpn_provider_endpoint_id_seq.next_value(),
            primary_key=True,
        ),
        sa.Column("date_created", sa.DateTime(timezone=True), nullable=False),
        sa.Column("date_updated", sa.DateTime(timezone=True), nullable=False),
        sa.Column("address", sa.String(), nullable=False),
        sa.Column("protocol", sa.String(), nullable=True),
        sa.Column("transport", sa.String(), nullable=True),
        sa.Column("provider_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["ooniprobe_vpn_provider.id"],
        ),
    )

def downgrade() -> None:
    op.drop_table("ooniprobe_vpn_provider")
    op.drop_table("ooniprobe_vpn_provider_endpoint")
