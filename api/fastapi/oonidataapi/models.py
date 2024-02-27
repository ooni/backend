from sqlalchemy import Boolean, Column, Integer, String, DateTime, JSON

from .postgresql import Base


class OONIRunLink(Base):
    __tablename__ = "oonirun"

    oonirun_link_id = Column(Integer, primary_key=True)
    revision = Column(Integer, default=1, primary_key=True)
    date_updated = Column(DateTime)
    date_created = Column(DateTime)
    creator_account_id = Column(String)

    expiration_date = Column(DateTime)

    name = Column(String)
    name_intl = Column(JSON, nullable=True)
    short_description = Column(String)
    short_description_intl = Column(JSON, nullable=True)
    description = Column(String)
    description_intl = Column(JSON, nullable=True)
    author = Column(String)
    icon = Column(String)
    color = Column(String)
    nettests = Column(JSON)
