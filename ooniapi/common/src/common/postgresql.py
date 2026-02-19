from typing import Any, Dict, List

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    type_annotation_map = {
        Dict[str, Any]: sa.JSON,
        List[str]: sa.JSON,
        Dict[str, str]: sa.JSON,
        List[Dict[str, Any]]: sa.ARRAY(sa.JSON()),
    }
