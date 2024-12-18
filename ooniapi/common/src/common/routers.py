from datetime import date, datetime
from typing import Union
from pydantic import BaseModel as PydandicBaseModel
from pydantic import ConfigDict


ISO_FORMAT_DATETIME = "%Y-%m-%dT%H:%M:%S.%fZ"
ISO_FORMAT_DATE = "%Y-%m-%d"


class BaseModel(PydandicBaseModel):
    model_config = ConfigDict(
        # TODO(art): this should be ported over to the functional serializer
        # pattern (https://docs.pydantic.dev/latest/api/functional_serializers/)
        # since json_encoders is deprecated, see:
        # https://docs.pydantic.dev/2.6/api/config/#pydantic.config.ConfigDict.json_encoders
        json_encoders={
            datetime: lambda v: v.strftime(ISO_FORMAT_DATETIME),
            date: lambda v: v.strftime(ISO_FORMAT_DATE),
        }
    )
