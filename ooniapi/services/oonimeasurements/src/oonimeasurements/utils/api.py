"""
Utility functions and types to assist API development
"""

from datetime import datetime, timezone
from typing import Annotated, Optional, Union
from fastapi import Query


ProbeCCOrNone = Annotated[Optional[str], Query(min_length=2, max_length=2)]
ProbeASNOrNone = Annotated[Union[int, str, None], Query()]


def normalize_datetime(dt: datetime) -> datetime:
    """
    Normalize a datetime to UTC timezone.

    If the datetime already has timezone information, it remains unchanged.

    Otherwise, UTC timezone is added, assuming the datetime is already in UTC.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt