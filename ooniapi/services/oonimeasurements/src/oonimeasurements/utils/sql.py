from datetime import timedelta
from sqlalchemy.sql.expression import text as sql_text
from sqlalchemy.sql.expression import column


gmap = dict(
    hour="toStartOfHour",
    day="toDate",
    week="toStartOfWeek",
    month="toStartOfMonth",
)


def _resolve_time_grain(since, until, time_grain):
    if since and until:
        delta = until - since
    else:
        delta = None

    ranges = (
        (7, ("hour", "day", "auto")),
        (30, ("day", "week", "auto")),
        (365, ("day", "week", "month", "auto")),
        (9999999, ("day", "week", "month", "year", "auto")),
    )
    if delta is None or delta <= timedelta():
        raise Exception("Invalid since and until values")

    for thresh, allowed in ranges:
        if delta > timedelta(days=thresh):
            continue
        if time_grain not in allowed:
            a = ", ".join(allowed)
            raise Exception(f"Choose time_grain between {a} for the given time range")
        if time_grain == "auto":
            time_grain = allowed[0]
        return time_grain

    raise Exception("Unable to resolve time_grain")


def group_by_date(since, until, time_grain, cols, colnames, group_by):
    time_grain = _resolve_time_grain(since, until, time_grain)
    fun = gmap[time_grain]
    tcol = "measurement_start_day"
    cols.append(sql_text(f"{fun}(measurement_start_time) AS {tcol}"))
    colnames.append(tcol)
    group_by.append(column(tcol))
    return time_grain


_param_cast = {
    "hour": "toDateTime",
    "day": "toDate",
    "week": "toDateTime",
    "month": "toDateTime",
}


def where_by_date(since, until, time_grain, where_by):
    time_grain = _resolve_time_grain(since, until, time_grain)
    fun = gmap[time_grain]
    cast = _param_cast[time_grain]

    if since:
        where_by.append(sql_text(f"{fun}(measurement_start_time) >= {fun}({cast}(:since))"))
    if until:
        where_by.append(sql_text(f"{fun}(measurement_start_time) < {fun}({cast}(:until))"))

    return time_grain

