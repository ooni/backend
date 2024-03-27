from datetime import datetime
from typing import Dict
from .common.models import UtcDateTime
from .common.postgresql import Base
from sqlalchemy import Sequence, String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column


class OONIProbeVPNConfig(Base):
    __tablename__ = "ooniprobe_vpn_config"

    id: Mapped[str] = mapped_column(
        String,
        Sequence("vpn_config_id_seq", start=1),
        primary_key=True,
    )
    date_updated: Mapped[datetime] = mapped_column(UtcDateTime())
    date_created: Mapped[datetime] = mapped_column(UtcDateTime())

    provider: Mapped[str] = mapped_column()

    protocol: Mapped[str] = mapped_column()
    openvpn_cert: Mapped[str] = mapped_column(nullable=True)
    openvpn_ca: Mapped[str] = mapped_column(nullable=True)
    openvpn_key: Mapped[str] = mapped_column(nullable=True)
