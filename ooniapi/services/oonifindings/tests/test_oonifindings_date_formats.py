"""
Dedicated coverage for the *exact* wire format of every date/datetime field
returned by the oonifindings API.

oonifindings' response models are built on `oonifindings.common.routers.BaseModel`,
which centralizes datetime JSON serialization for the whole service (this is
the same shared base class used by oonimeasurements, ooniauth and oonirun --
see ooniapi/common/src/common/routers.py). A change to that shared serializer
can silently change the wire format of every endpoint that uses it.

`start_time`/`end_time` are already indirectly format-checked elsewhere via
exact round-trip equality with a client-supplied value (see
test_oonifinding_create), but `create_time`/`update_time` are server-generated
and, prior to this module, were only checked for *presence*, never for
format. This module pins down the exact "YYYY-MM-DDTHH:MM:SS.ffffffZ" format
(oonifindings.common.routers.ISO_FORMAT_DATETIME) for all four fields.
"""

import re
from copy import deepcopy
from datetime import timedelta

from oonifindings.routers.v1 import utcnow_seconds

# "2025-07-01T00:00:00.000000Z"
DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")

SAMPLE_EMAIL = "date-format-test@ooni.org"

sample_start_time = (utcnow_seconds() + timedelta(minutes=-1)).strftime(
    "%Y-%m-%dT%H:%M:%S.%fZ"
)
sample_end_time = (utcnow_seconds() + timedelta(days=30)).strftime(
    "%Y-%m-%dT%H:%M:%S.%fZ"
)

SAMPLE_OONIFINDING = {
    "title": "sample oonifinding for date format checks",
    "short_description": "sample oonifinding description",
    "reported_by": "sample user",
    "email_address": SAMPLE_EMAIL,
    "text": "this is a sample oonifinding incident",
    "published": True,
    "event_type": "incident",
    "start_time": sample_start_time,
    "end_time": sample_end_time,
    "ASNs": [],
    "CCs": ["IN"],
    "tags": [],
    "test_names": ["webconnectivity"],
    "domains": ["www.google.com"],
    "links": [],
}


def assert_datetime_format(value):
    assert isinstance(value, str), repr(value)
    assert DATETIME_RE.match(value), (
        f"{value!r} does not match the expected datetime format "
        f"(YYYY-MM-DDTHH:MM:SS.ffffffZ)"
    )


def test_incident_date_fields_format(client, client_with_hashed_email):
    client_with_admin_role = client_with_hashed_email(SAMPLE_EMAIL, "admin")

    z = deepcopy(SAMPLE_OONIFINDING)
    r = client_with_admin_role.post("api/v1/incidents/create", json=z)
    assert r.status_code == 200, r.json()
    incident_id = r.json()["id"]
    assert incident_id

    r = client.get(f"api/v1/incidents/show/{incident_id}")
    assert r.status_code == 200
    incident = r.json()["incident"]

    # server-generated timestamps: only ever checked for *presence* before
    # this module, never for exact format.
    assert_datetime_format(incident["create_time"])
    assert_datetime_format(incident["update_time"])

    # client-supplied, round-tripped timestamps: reinforce the existing
    # exact-value check in test_oonifinding_create with an explicit format
    # assertion, independent of what the test happened to send in.
    assert_datetime_format(incident["start_time"])
    assert_datetime_format(incident["end_time"])

    # also check the list/search response, which shares the same model
    r = client.get("api/v1/incidents/search")
    assert r.status_code == 200
    incidents = r.json()["incidents"]
    assert len(incidents) > 0
    for i in incidents:
        assert_datetime_format(i["create_time"])
        assert_datetime_format(i["update_time"])
        assert_datetime_format(i["start_time"])
        if i["end_time"] is not None:
            assert_datetime_format(i["end_time"])
