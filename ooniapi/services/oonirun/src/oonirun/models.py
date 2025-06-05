from datetime import datetime
from typing import List, Dict, Any
import sqlalchemy as sa
from sqlalchemy import ForeignKey, Sequence, String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from .common.models import UtcDateTime
from .common.postgresql import Base


class OONIRunLink(Base):
    __tablename__ = "oonirun"

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

    nettests: Mapped[List["OONIRunLinkNettest"]] = relationship(
        back_populates="oonirun_link",
        order_by="desc(OONIRunLinkNettest.revision), asc(OONIRunLinkNettest.nettest_index)",
    )


class OONIRunLinkNettest(Base):
    __tablename__ = "oonirun_nettest"

    oonirun_link = relationship("OONIRunLink", back_populates="nettests")
    oonirun_link_id: Mapped[str] = mapped_column(
        ForeignKey("oonirun.oonirun_link_id"), primary_key=True
    )

    revision: Mapped[int] = mapped_column(default=1, primary_key=True)
    nettest_index: Mapped[int] = mapped_column(default=0, primary_key=True)

    date_created: Mapped[datetime] = mapped_column(UtcDateTime())

    test_name: Mapped[str] = mapped_column()
    inputs: Mapped[List[str]] = mapped_column(nullable=True)

    is_background_run_enabled_default: Mapped[bool] = mapped_column(default=False)
    is_manual_run_enabled_default: Mapped[bool] = mapped_column(default=False)
    targets_name: Mapped[str] = mapped_column(nullable=True)
    inputs_extra: Mapped[List[Dict[str, Any]]] = mapped_column(nullable=True)
