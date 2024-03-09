from datetime import datetime, timezone
from typing import List, Dict, Any
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from .postgresql import Base


class OONIRunLink(Base):
    __tablename__ = "oonirun"

    oonirun_link_id: Mapped[str] = mapped_column(primary_key=True)
    date_updated: Mapped[datetime] = mapped_column()
    date_created: Mapped[datetime] = mapped_column()
    creator_account_id: Mapped[str] = mapped_column()

    expiration_date: Mapped[datetime] = mapped_column(nullable=False)

    # Timezones are kind of tricky. We assume everything is always in UTC,
    # but python, rightfully complains, if that encoding is not specified in
    # the object itself since more modern versions of python.
    # To avoid making this a DB specific change, we don't introduce the
    # TIMESTAMP column which would allow us to retrieve timezone native
    # objects, but instead do casting to the timezone native equivalent in
    # the code.
    # See: https://stackoverflow.com/questions/414952/sqlalchemy-datetime-timezone
    @property
    def expiration_date_dt_native(self):
        return self.expiration_date.replace(tzinfo=timezone.utc)

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

    date_created: Mapped[datetime] = mapped_column()

    test_name: Mapped[str] = mapped_column()
    test_inputs: Mapped[List[str]] = mapped_column(nullable=True)
    test_options: Mapped[Dict[str, Any]] = mapped_column(nullable=True)
    backend_config: Mapped[Dict[str, Any]] = mapped_column(nullable=True)

    is_background_run_enabled_default: Mapped[bool] = mapped_column(default=False)
    is_manual_run_enabled_default: Mapped[bool] = mapped_column(default=False)
