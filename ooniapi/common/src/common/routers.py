from datetime import date, datetime
from pydantic import BaseModel as PydandicBaseModel


ISO_FORMAT_DATETIME = "%Y-%m-%dT%H:%M:%S.%fZ"
ISO_FORMAT_DATE = "%Y-%m-%d"


class BaseModel(PydandicBaseModel):
    class Config:
        json_encoders = {
            datetime: lambda v: v.strftime(ISO_FORMAT_DATETIME),
            date: lambda v: v.strftime(ISO_FORMAT_DATE),
        }
