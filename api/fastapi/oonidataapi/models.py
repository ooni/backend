from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, DateTime
from sqlalchemy.orm import relationship

from .postgresql import Base


class OONIRunLink(Base):
    __tablename__ = "oonirun"

    ooni_run_link_id = Column(Integer, primary_key=True)
    descriptor_creation_time = Column(DateTime)
    translation_creation_time = Column(DateTime)
    creator_account_id = Column(String)
    is_archived = Column(Boolean, default=False)
    descriptor = Column(String)
    author = Column(String)
    name = Column(String)
    short_description = Column(String)
    icon = Column(String)
