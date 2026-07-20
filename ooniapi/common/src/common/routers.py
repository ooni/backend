from datetime import date, datetime, timezone
from pydantic import BaseModel as PydandicBaseModel
from pydantic import field_serializer


ISO_FORMAT_DATETIME = "%Y-%m-%dT%H:%M:%S.%fZ"
ISO_FORMAT_DATE = "%Y-%m-%d"


class BaseModel(PydandicBaseModel):
    @field_serializer("*", when_used="json")
    def serialize_json(self, v):
        # Note: datetime is a subclass of date, so check datetime first.
        if isinstance(v, datetime):
            # If you always want "...Z", normalize to UTC.
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            else:
                v = v.astimezone(timezone.utc)

            # Your format includes microseconds + trailing Z
            return v.strftime(ISO_FORMAT_DATETIME)

        if isinstance(v, date):
            return v.strftime(ISO_FORMAT_DATE)

        return v
