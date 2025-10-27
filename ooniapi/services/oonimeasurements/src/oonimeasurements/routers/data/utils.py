from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Annotated, Literal, Union, Optional

from fastapi import Query
from pydantic import AfterValidator


TimeGrains = Literal["hour", "day", "week", "month", "year", "auto"]


def get_measurement_start_day_agg(
    time_grain: TimeGrains, column_name: str = "measurement_start_time"
):
    if time_grain == "hour":
        return f"toStartOfHour({column_name})"
    if time_grain == "day":
        return f"toStartOfDay({column_name})"
    if time_grain == "week":
        return f"toStartOfWeek({column_name})"
    if time_grain == "month":
        return f"toStartOfMonth({column_name})"
    if time_grain == "year":
        return f"toStartOfYear({column_name})"
    return f"toStartOfDay({column_name})"


def parse_date(d: Union[datetime, str]) -> datetime:
    from dateutil.parser import parse as parse_date

    if isinstance(d, str):
        return parse_date(d)
    return d


SinceUntil = Annotated[Union[str, datetime], AfterValidator(parse_date), Query()]


def utc_30_days_ago():
    return datetime.combine(
        datetime.now(timezone.utc) - timedelta(days=30), datetime.min.time()
    ).replace(tzinfo=None)


def utc_today():
    return datetime.combine(datetime.now(timezone.utc), datetime.min.time()).replace(
        tzinfo=None
    )


def test_name_to_group(tn):
    if tn in ("web_connectivity", "http_requests"):
        return "websites"
    # TODO(arturo): currently we only support websites
    return ""


def parse_probe_asn_to_int(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        probe_asn = kwargs.get("probe_asn", None)
        if isinstance(probe_asn, str):
            if probe_asn.startswith("AS"):
                probe_asn = probe_asn[2:]
            kwargs["probe_asn"] = int(probe_asn)
        return await func(*args, **kwargs)

    return wrapper

ProbeCCOrNone = Annotated[Optional[str], Query(min_length=2, max_length=2)]
ProbeASNOrNone = Annotated[Union[int, str, None], Query()]