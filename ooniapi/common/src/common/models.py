from datetime import datetime, timezone
from sqlalchemy.types import DateTime, TypeDecorator


class UtcDateTime(TypeDecorator):
    """
    Taken from: https://github.com/spoqa/sqlalchemy-utc/blob/8409688000ba0f52c928cc38d34069e521c24bae/sqlalchemy_utc/sqltypes.py
    Almost equivalent to :class:`~sqlalchemy.types.DateTime` with
    ``timezone=True`` option, but it differs from that by:

    - Never silently take naive :class:`~datetime.datetime`, instead it
      always raise :exc:`ValueError` unless time zone aware value.
    - :class:`~datetime.datetime` value's :attr:`~datetime.datetime.tzinfo`
      is always converted to UTC.
    - Unlike SQLAlchemy's built-in :class:`~sqlalchemy.types.DateTime`,
      it never return naive :class:`~datetime.datetime`, but time zone
      aware value, even with SQLite or MySQL.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            if not isinstance(value, datetime):
                raise TypeError("expected datetime.datetime, not " + repr(value))
            elif value.tzinfo is None:
                raise ValueError("naive datetime is disallowed")
            return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is not None:  # no cov
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            else:
                value = value.astimezone(timezone.utc)
        return value
