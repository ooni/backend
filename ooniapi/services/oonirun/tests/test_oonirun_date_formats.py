"""
Dedicated coverage for the *exact* wire format of every date/datetime field
returned by the oonirun API.

oonirun's response models are built on `oonirun.common.routers.BaseModel`,
the same shared base class used by oonimeasurements, ooniauth and
oonifindings (see ooniapi/common/src/common/routers.py). A change to that
shared serializer can silently change the wire format of every endpoint that
uses it.

`date_created`/`date_updated` are already strictly format-checked elsewhere
(see test_oonirun_full_workflow, which round-trips them through
`datetime.strptime(..., "%Y-%m-%dT%H:%M:%S.%fZ")` and would fail loudly on a
format regression). `expiration_date`'s server-assigned default value,
however, was previously only ever captured and round-tripped -- never
independently checked against the expected format. This module closes that
gap and, for good measure, re-asserts the format of all three fields in one
place using a regex so a future format change is caught regardless of which
existing test happens to touch the field.
"""

import re
from copy import deepcopy

from .test_oonirun import SAMPLE_OONIRUN

# "2025-07-01T00:00:00.000000Z"
DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")


def assert_datetime_format(value):
    assert isinstance(value, str), repr(value)
    assert DATETIME_RE.match(value), (
        f"{value!r} does not match the expected datetime format "
        f"(YYYY-MM-DDTHH:MM:SS.ffffffZ)"
    )


def test_oonirun_link_date_fields_format(client_with_user_role):
    z = deepcopy(SAMPLE_OONIRUN)
    z["name"] = "integ-test name for date format checks"
    z["name_intl"] = None

    r = client_with_user_role.post("/api/v2/oonirun/links", json=z)
    assert r.status_code == 200, r.json()
    j = r.json()

    # date_created/date_updated are already strictly checked (via strptime)
    # in test_oonirun_full_workflow; re-assert with a regex here too so this
    # module is a self-contained, single source of truth for the format.
    assert_datetime_format(j["date_created"])
    assert_datetime_format(j["date_updated"])

    # expiration_date's server-assigned default was previously never
    # checked against the expected format, only round-tripped.
    assert_datetime_format(j["expiration_date"])

    oonirun_link_id = j["oonirun_link_id"]

    r = client_with_user_role.get(f"/api/v2/oonirun/links/{oonirun_link_id}")
    assert r.status_code == 200, r.json()
    j = r.json()
    assert_datetime_format(j["date_created"])
    assert_datetime_format(j["date_updated"])
    assert_datetime_format(j["expiration_date"])
