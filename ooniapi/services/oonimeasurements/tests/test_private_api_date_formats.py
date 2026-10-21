"""
Dedicated coverage for the *exact* wire format of every date/datetime field
returned by the private API (/api/_/...).

These endpoints are built on top of `oonimeasurements.common.routers.BaseModel`,
which centralizes datetime/date JSON serialization for the whole service. A
change to that shared serializer (e.g. migrating away from the deprecated
pydantic `json_encoders` config) can silently change the wire format of every
endpoint that uses it -- including endpoints, like the ones below, that
intentionally override the shared format to stay backwards compatible with
existing API consumers.

The existing tests in test_private_api.py mostly check for the *presence* of
date/datetime fields (or use loose checks like `.startswith("20")`), which is
not enough to catch a format regression. This module pins down the exact
format for every such field so that any future change to the shared
serializer (or to a per-model override) is caught immediately, regardless of
which endpoint it slips through.

There are two formats in use across the private API:

- "legacy timestamp" endpoints (asn_by_month, countries_by_month, im_stats,
  global_overview_by_month) predate the shared BaseModel serializer and
  explicitly override it to keep emitting a UTC ISO-8601 timestamp with the
  microseconds truncated and a "+00:00" offset, e.g. "2025-07-01T00:00:00+00:00".
- everything else that emits a plain `date` (not `datetime`) field uses the
  shared BaseModel default of a bare "YYYY-MM-DD" string, e.g. "2025-07-01".
"""

import re

from urllib.parse import urlencode

# "2025-07-01T00:00:00+00:00" -- UTC timestamp, no microseconds, "+00:00" offset.
LEGACY_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$"
)

# "2025-07-01" -- plain calendar date.
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def privapi(client, subpath):
    response = client.get(f"/api/_/{subpath}")
    assert response.status_code == 200
    return response.json()


def assert_legacy_datetime_format(value):
    assert isinstance(value, str), repr(value)
    assert LEGACY_DATETIME_RE.match(value), (
        f"{value!r} does not match the expected legacy timestamp format "
        f"(YYYY-MM-DDTHH:MM:SS+00:00)"
    )


def assert_date_format(value):
    assert isinstance(value, str), repr(value)
    assert DATE_RE.match(value), (
        f"{value!r} does not match the expected date format (YYYY-MM-DD)"
    )


# ---------------------------------------------------------------------------
# datetime fields serialized with the legacy "+00:00" (no microseconds) format
# ---------------------------------------------------------------------------


def test_asn_by_month_date_format(client, fixed_time):
    resp = privapi(client, "asn_by_month")
    assert len(resp) > 0, resp
    for r in resp:
        assert_legacy_datetime_format(r["date"])


def test_countries_by_month_date_format(client, fixed_time):
    resp = privapi(client, "countries_by_month")
    assert len(resp) > 0, resp
    for r in resp:
        assert_legacy_datetime_format(r["date"])


def test_im_stats_test_day_format(client, fixed_time):
    url = "im_stats?probe_cc=DE&probe_asn=680&test_name=signal"
    resp = privapi(client, url)
    assert len(resp["results"]) > 0, resp
    for r in resp["results"]:
        assert_legacy_datetime_format(r["test_day"])


def test_im_stats_basic_test_day_format(client):
    url = "im_stats?probe_cc=CH&probe_asn=3303&test_name=facebook_messenger"
    resp = privapi(client, url)
    assert len(resp["results"]) > 0, resp
    for r in resp["results"]:
        assert_legacy_datetime_format(r["test_day"])


def test_global_overview_by_month_date_format(client, fixed_time):
    resp = privapi(client, "global_overview_by_month")
    for key in ("networks_by_month", "countries_by_month", "measurements_by_month"):
        assert len(resp[key]) > 0, resp
        for r in resp[key]:
            assert_legacy_datetime_format(r["date"])


# ---------------------------------------------------------------------------
# plain `date` fields serialized with the shared BaseModel default format.
# These are unaffected by the legacy-format regression, but are pinned down
# here so any future change to the shared serializer is caught too.
# ---------------------------------------------------------------------------


def test_test_coverage_date_format(client, log):
    resp = privapi(client, "test_coverage?probe_cc=BR")
    assert len(resp["network_coverage"]) > 0, resp
    assert len(resp["test_coverage"]) > 0, resp
    for r in resp["network_coverage"]:
        assert_date_format(r["test_day"])
    for r in resp["test_coverage"]:
        assert_date_format(r["test_day"])


def test_website_stats_test_day_format(client, log, fixed_time):
    qs = urlencode({"probe_cc": "CN", "probe_asn": 9808, "input": "https://www.x.com"})
    resp = privapi(client, f"website_stats?{qs}")
    assert len(resp["results"]) > 0, resp
    for r in resp["results"]:
        assert_date_format(r["test_day"])


def test_vanilla_tor_stats_last_tested_format(client, fixed_time):
    resp = privapi(client, "vanilla_tor_stats?probe_cc=DE")
    assert_date_format(resp["last_tested"])
    assert len(resp["networks"]) > 0, resp
    for n in resp["networks"]:
        assert_date_format(n["last_tested"])


def test_vanilla_tor_stats_empty_last_tested_is_null(client):
    # sample data does not contain rows for probe_cc=LI
    resp = privapi(client, "vanilla_tor_stats?probe_cc=LI")
    assert resp["last_tested"] is None
    assert resp["networks"] == []


def test_im_networks_last_tested_format(client, fixed_time):
    resp = privapi(client, "im_networks?probe_cc=DE")
    assert "signal" in resp, resp
    stats = resp["signal"]
    assert_date_format(stats["last_tested"])
    assert len(stats["ok_networks"]) > 0, stats
    for n in stats["ok_networks"]:
        assert_date_format(n["last_tested"])


def test_country_overview_first_bucket_date_format(client):
    resp = privapi(client, "country_overview?probe_cc=BR")
    assert_date_format(resp["first_bucket_date"])


def test_circumvention_runtime_stats_date_format(client, log, fixed_time):
    resp = privapi(client, "circumvention_runtime_stats")
    assert len(resp["results"]) > 0, resp
    for r in resp["results"]:
        assert_date_format(r["date"])
