from datetime import timezone
from sqlalchemy import Boolean, Column, Integer, String, DateTime, JSON

from .postgresql import Base


class OONIRunLink(Base):
    __tablename__ = "oonirun"

    oonirun_link_id = Column(Integer, primary_key=True)
    revision = Column(Integer, default=1, primary_key=True)
    date_updated = Column(DateTime)
    date_created = Column(DateTime)
    creator_account_id = Column(String)

    expiration_date = Column(DateTime, nullable=False)

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
