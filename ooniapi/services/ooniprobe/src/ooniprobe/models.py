from datetime import datetime
from typing import List, Dict, Any
from .common.models import UtcDateTime
from sqlalchemy import Sequence, String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from .postgresql import Base


class OONIProbeVPNConfig(Base):
    __tablename__ = "ooniprobe_vpn_config"

    # First 10k OONI Run links are reserved for official OONI links
    oonirun_link_id: Mapped[str] = mapped_column(
        String,
        Sequence("oonirun_link_id_seq", start=10_000),
        primary_key=True,
    )
    date_updated: Mapped[datetime] = mapped_column(UtcDateTime())
    date_created: Mapped[datetime] = mapped_column(UtcDateTime())
    creator_account_id: Mapped[str] = mapped_column()

    expiration_date: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)

    name: Mapped[str] = mapped_column()
    name_intl: Mapped[Dict[str, str]] = mapped_column(nullable=True)
    short_description: Mapped[str] = mapped_column(nullable=True)
    short_description_intl: Mapped[Dict[str, str]] = mapped_column(nullable=True)
    description: Mapped[str] = mapped_column(nullable=True)
    description_intl: Mapped[Dict[str, str]] = mapped_column(nullable=True)
    author: Mapped[str] = mapped_column(nullable=True)
    icon: Mapped[str] = mapped_column(nullable=True)
    color: Mapped[str] = mapped_column(nullable=True)
