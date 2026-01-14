from typing import Annotated

from fastapi import Depends

from .common.config import Settings
from .common.dependencies import get_settings

SettingsDep = Annotated[Settings, Depends(get_settings)]
