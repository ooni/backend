from datetime import datetime
from typing import List
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from .common.models import UtcDateTime
from .common.postgresql import Base


class OONIFinding(Base):
    __tablename__ = "oonifinding"

    # TODO(decfox): add primary key finding id
    incident_id: Mapped[str] = mapped_column(String, primary_key=True)

    create_time: Mapped[datetime] = mapped_column(UtcDateTime())
    update_time: Mapped[datetime] = mapped_column(UtcDateTime())
    start_time: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=True)
    end_time: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=True)
    creator_account_id: Mapped[str] = mapped_column(String(32))

    title: Mapped[str] = mapped_column()
    short_description: Mapped[str] = mapped_column()
    text: Mapped[str] = mapped_column()
    reported_by: Mapped[str] = mapped_column()
    email_address: Mapped[str] = mapped_column()
    event_type: Mapped[str] = mapped_column()
    published: Mapped[int] = mapped_column()
    deleted: Mapped[int] = mapped_column(default=0)

    country_codes: Mapped[List[str]] = mapped_column(nullable=True)
    asns: Mapped[List[str]] = mapped_column(nullable=True)
    domains: Mapped[List[str]] = mapped_column(nullable=True)
    tags: Mapped[List[str]] = mapped_column(nullable=True)
    links: Mapped[List[str]] = mapped_column(nullable=True)
    test_names: Mapped[List[str]] = mapped_column(nullable=True)
