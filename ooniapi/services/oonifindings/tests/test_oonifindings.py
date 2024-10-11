"""
Integration test for OONIFindings API
"""

from copy import deepcopy
from datetime import timedelta, datetime

from oonifindings.routers.v1 import utcnow_seconds

sample_start_time = (utcnow_seconds() + timedelta(minutes=-1)).strftime(
    "%Y-%m-%dT%H:%M:%S.%fZ"
)

sample_end_time = (utcnow_seconds() + timedelta(days=30)).strftime(
    "%Y-%m-%dT%H:%M:%S.%fZ"
)

SAMPLE_EMAIL = "sample@ooni.org"

SAMPLE_OONIFINDING = {
    "title": "sample oonifinding",
    "short_description": "sample oonifinding description",
    "reported_by": "sample user",
    "email_address": SAMPLE_EMAIL,
    "text": "this is a sample oonifinding incident",
    "published": False,
    "event_type": "incident",
    "start_time": sample_start_time,
    "ASNs": [],
    "CCs": [
        "IN",
        "TZ",
    ],
    "tags": [],
    "test_names": [
        "webconnectivity",
    ],
    "domains": ["www.google.com"],
    "links": [],
}

EXPECTED_OONIFINDING_PUBLIC_KEYS = [
    "id",
    "title",
    "short_description",
    "start_time",
    "end_time",
    "create_time",
    "update_time",
    "creator_account_id",
    "reported_by",
    "email_address",
    "text",
    "mine",
    "published",
    "event_type",
    "ASNs",
    "CCs",
    "tags",
    "test_names",
    "domains",
    "links",
    "slug",
    "themes",
]


def test_get_version(client):
    r = client.get("/version")
    j = r.json()
    assert "version" in j
    assert "build_label" in j


def test_get_root(client):
    r = client.get("/")
    assert r.status_code == 200


def test_oonifinding_validation(client, client_with_user_role):
    z = deepcopy(SAMPLE_OONIFINDING)
    r = client_with_user_role.post("/api/v1/incidents/create", json=z)
    assert r.status_code == 401, "only admins can create incidents"


def test_oonifinding_creator_validation(client, client_with_hashed_email):
    client_with_admin_role = client_with_hashed_email(SAMPLE_EMAIL, "admin")

    z = deepcopy(SAMPLE_OONIFINDING)

    z["email_address"] = ""
    r = client_with_admin_role.post("api/v1/incidents/create", json=z)
    assert r.status_code == 400, "email hash does not match with account id"

    z["email_address"] = SAMPLE_EMAIL
    z["title"] = ""
    r = client_with_admin_role.post("api/v1/incidents/create", json=z)
    assert r.status_code == 422, "empty title should be rejected"

    z["title"] = "sample oonifinding"
    z["text"] = ""
    r = client_with_admin_role.post("api/v1/incidents/create", json=z)
    assert r.status_code == 422, "empty text should be rejected"

    z["text"] = "sample text for oonifinding incident"
    start_time = datetime.strptime(sample_start_time, "%Y-%m-%dT%H:%M:%S.%fZ")
    sample_end_time = start_time + timedelta(minutes=-1)
    z["end_time"] = sample_end_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    r = client_with_admin_role.post("api/v1/incidents/create", json=z)
    assert r.status_code == 422, "invalid end_time should be rejected"

    sample_end_time = start_time + timedelta(minutes=1)
    z["end_time"] = sample_end_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    r = client_with_admin_role.post("api/v1/incidents/create", json=z)
    assert r.status_code == 200
    assert r.json()["r"] == 1
    assert r.headers["Cache-Control"] == "no-cache"


def test_oonifinding_publish(client, client_with_hashed_email):
    client_with_admin_role = client_with_hashed_email(SAMPLE_EMAIL, "admin")
    client_with_user_role = client_with_hashed_email(SAMPLE_EMAIL, "user")

    z = deepcopy(SAMPLE_OONIFINDING)

    z["published"] = True
    r = client_with_admin_role.post("/api/v1/incidents/create", json=z)
    assert r.status_code == 200, "published true should be ACCEPTED"

    z["published"] = False
    r = client_with_admin_role.post("/api/v1/incidents/create", json=z)
    assert r.status_code == 200
    assert r.json()["r"] == 1
    assert r.headers["Cache-Control"] == "no-cache"

    incident_id = r.json()["id"]
    assert incident_id

    r = client_with_admin_role.get(f"api/v1/incidents/show/{incident_id}")
    incident_payload = r.json()["incident"]

    r = client_with_admin_role.post("api/v1/incidents/random", json=incident_payload)
    assert (
        r.status_code == 400
    ), "only publish and unpublish are valid supported actions"

    r = client_with_user_role.post("api/v1/incidents/publish", json=incident_payload)
    assert r.status_code == 401, "only admins can publish incidents"

    r = client_with_admin_role.post("api/v1/incidents/publish", json={"id": "12341512"})
    assert r.status_code == 404, "valid incident id should be passed"

    r = client_with_admin_role.post(
        "api/v1/incidents/publish", json={"id": incident_id}
    )
    assert r.status_code == 200
    assert r.json()["r"] == 1
    assert r.json()["id"] == incident_id
    assert r.headers["Cache-Control"] == "no-cache"

    r = client_with_admin_role.get(f"api/v1/incidents/show/{incident_id}")
    incident = r.json()["incident"]
    assert incident
    assert incident["published"] is True

    r = client_with_admin_role.post("api/v1/incidents/unpublish", json=incident_payload)
    assert r.status_code == 200
    assert r.json()["r"] == 1
    assert r.json()["id"] == incident_id
    assert r.headers["Cache-Control"] == "no-cache"

    r = client_with_admin_role.get(f"api/v1/incidents/show/{incident_id}")
    incident = r.json()["incident"]
    assert incident
    assert incident["published"] is False


def test_oonifinding_delete(client, client_with_hashed_email):
    client_with_admin_role = client_with_hashed_email(SAMPLE_EMAIL, "admin")
    client_with_user_role = client_with_hashed_email(SAMPLE_EMAIL, "user")

    z = deepcopy(SAMPLE_OONIFINDING)

    r = client_with_admin_role.post("api/v1/incidents/create", json=z)
    assert r.status_code == 200
    assert r.json()["r"] == 1
    assert r.headers["Cache-Control"] == "no-cache"

    incident_id = r.json()["id"]
    assert incident_id

    z["id"] = "not-exist"
    r = client_with_admin_role.post("api/v1/incidents/delete", json=z)
    assert r.status_code == 404

    z["id"] = incident_id
    r = client_with_admin_role.post("api/v1/incidents/delete", json=z)
    assert r.status_code == 200
    assert r.headers["Cache-Control"] == "no-cache"

    r = client_with_admin_role.post("api/v1/incidents/create", json=z)
    assert r.status_code == 200
    assert r.json()["r"] == 1
    assert r.headers["Cache-Control"] == "no-cache"

    incident_id = r.json()["id"]
    assert incident_id

    z["id"] = incident_id
    z["email_address"] = ""
    r = client_with_user_role.post("api/v1/incidents/delete", json=z)
    assert r.status_code == 403

    z["email_address"] = SAMPLE_EMAIL
    mismatched_client = client_with_hashed_email("user@ooni.org", "user")
    r = mismatched_client.post("api/v1/incidents/delete", json=z)
    assert r.status_code == 403

    r = client_with_user_role.post("api/v1/incidents/delete", json=z)
    assert r.status_code == 200
    assert r.headers["Cache-Control"] == "no-cache"

    r = client_with_admin_role.get(f"api/v1/incidents/show/{incident_id}")
    assert r.status_code == 404


def test_oonifinding_update(client, client_with_hashed_email):
    client_with_admin_role = client_with_hashed_email(SAMPLE_EMAIL, "admin")
    client_with_user_role = client_with_hashed_email(SAMPLE_EMAIL, "user")

    z = deepcopy(SAMPLE_OONIFINDING)

    r = client_with_admin_role.post("api/v1/incidents/create", json=z)
    assert r.status_code == 200
    assert r.json()["r"] == 1
    assert r.headers["Cache-Control"] == "no-cache"

    incident_id = r.json()["id"]
    assert incident_id

    r = client_with_admin_role.get(f"api/v1/incidents/show/{incident_id}")
    incident_payload = r.json()["incident"]

    not_exist = deepcopy(incident_payload)
    not_exist["id"] = "does-not-exist"
    r = client_with_admin_role.post("api/v1/incidents/update", json=not_exist)
    assert r.status_code == 404

    sample_replacement_text = "sample replacement text for update"
    incident_payload["text"] = sample_replacement_text
    r = client_with_admin_role.post("api/v1/incidents/update", json=incident_payload)
    assert r.json()["r"] == 1
    assert r.json()["id"] == incident_id
    assert r.headers["Cache-Control"] == "no-cache"

    r = client_with_admin_role.get(f"api/v1/incidents/show/{incident_id}")
    incident_payload = r.json()["incident"]
    assert incident_payload
    assert incident_payload["text"] == sample_replacement_text

    incident_payload["text"] = ""
    r = client_with_admin_role.post("api/v1/incidents/update", json=incident_payload)
    assert r.status_code == 422, "cannot update with empty text"

    incident_payload["text"] = sample_replacement_text
    incident_payload["title"] = ""
    r = client_with_admin_role.post("api/v1/incidents/update", json=incident_payload)
    assert r.status_code == 422, "cannot update with empty title"

    incident_payload["title"] = z["title"]
    sample_replacement_description = "sample replacement discription for update"
    incident_payload["short_description"] = sample_replacement_description

    incident_payload["email_address"] = ""
    r = client_with_user_role.post("api/v1/incidents/update", json=incident_payload)
    assert r.status_code == 403, "cannot update with invalid email"

    incident_payload["email_address"] = SAMPLE_EMAIL
    mismatched_client = client_with_hashed_email("user@ooni.org", "user")
    r = mismatched_client.post("api/v1/incidents/update", json=incident_payload)
    assert r.status_code == 403, "email should match account id"

    r = client_with_user_role.post("api/v1/incidents/update", json=incident_payload)
    assert r.status_code == 200
    assert r.json()["r"] == 1
    assert r.json()["id"] == incident_id
    assert r.headers["Cache-Control"] == "no-cache"

    r = client_with_admin_role.get(f"api/v1/incidents/show/{incident_id}")
    incident_payload = r.json()["incident"]
    assert incident_payload
    assert incident_payload["short_description"] == sample_replacement_description

    sample_tag = "sample_tag"
    incident_payload["tags"].append(sample_tag)
    r = client_with_user_role.post("api/v1/incidents/update", json=incident_payload)
    assert r.status_code == 200
    assert r.json()["r"] == 1
    assert r.json()["id"] == incident_id
    assert r.headers["Cache-Control"] == "no-cache"

    r = client_with_admin_role.get(f"api/v1/incidents/show/{incident_id}")
    incident_payload = r.json()["incident"]
    assert incident_payload
    assert len(incident_payload["tags"]) == 1
    assert incident_payload["tags"][0] == sample_tag

    incident_payload["published"] = True
    r = client_with_user_role.post("api/v1/incidents/update", json=incident_payload)
    assert r.status_code == 403, "user role cannot publish incident"

    r = client_with_admin_role.post("api/v1/incidents/update", json=incident_payload)
    assert r.status_code == 200
    assert r.json()["r"] == 1
    assert r.json()["id"] == incident_id
    assert r.headers["Cache-Control"] == "no-cache"

    r = client_with_admin_role.get(f"api/v1/incidents/show/{incident_id}")
    incident_payload = r.json()["incident"]
    assert incident_payload
    assert incident_payload["published"] == True


# TODO(decfox): add checks for fetched incident fields
def test_oonifinding_workflow(client, client_with_hashed_email, client_with_user_role):
    client_with_admin_role = client_with_hashed_email(SAMPLE_EMAIL, "admin")

    z = deepcopy(SAMPLE_OONIFINDING)

    r = client_with_admin_role.post("api/v1/incidents/create", json=z)
    assert r.status_code == 200
    assert r.json()["r"] == 1
    assert r.headers["Cache-Control"] == "no-cache"

    r = client_with_admin_role.post("api/v1/incidents/create", json=z)
    assert r.status_code == 200
    assert r.json()["r"] == 1
    assert r.headers["Cache-Control"] == "no-cache"

    incident_id = r.json()["id"]
    assert incident_id

    r = client.get(f"api/v1/incidents/show/{incident_id}")
    assert (
        r.status_code == 404
    ), "unpublished events cannot be seen with invalid account id"

    r = client_with_user_role.get(f"api/v1/incidents/show/{incident_id}")
    incident = r.json()["incident"]
    assert incident
    assert incident["mine"] is False
    assert incident["email_address"] == ""
    assert sorted(incident.keys()) == sorted(EXPECTED_OONIFINDING_PUBLIC_KEYS)

    r = client_with_admin_role.get(f"api/v1/incidents/show/{incident_id}")
    incident = r.json()["incident"]
    assert incident
    assert incident["mine"] is True
    assert incident["email_address"] == z["email_address"]
    assert sorted(incident.keys()) == sorted(EXPECTED_OONIFINDING_PUBLIC_KEYS)

    # publish incident and test
    r = client_with_admin_role.post("api/v1/incidents/publish", json=incident)
    assert r.json()["r"] == 1

    r = client.get(f"api/v1/incidents/show/{incident_id}")
    incident = r.json()["incident"]
    assert incident
    assert incident["mine"] is False
    assert incident["email_address"] == ""
    assert sorted(incident.keys()) == sorted(EXPECTED_OONIFINDING_PUBLIC_KEYS)

    r = client_with_user_role.get(f"api/v1/incidents/show/{incident_id}")
    incident = r.json()["incident"]
    assert incident
    assert incident["mine"] is False
    assert incident["email_address"] == ""
    assert sorted(incident.keys()) == sorted(EXPECTED_OONIFINDING_PUBLIC_KEYS)

    r = client_with_admin_role.get(f"api/v1/incidents/show/{incident_id}")
    incident = r.json()["incident"]
    assert incident
    assert incident["mine"] is True
    assert incident["email_address"] == z["email_address"]
    assert sorted(incident.keys()) == sorted(EXPECTED_OONIFINDING_PUBLIC_KEYS)

    EXPECTED_OONIFINDING_PUBLIC_KEYS.remove("text")

    r = client.get("api/v1/incidents/search?only_mine=false")
    assert r.status_code == 200
    incidents = r.json()["incidents"]
    assert len(incidents) == 1
    for incident in incidents:
        assert incident["email_address"] == ""
        assert incident["mine"] is False
        assert sorted(incident.keys()) == sorted(EXPECTED_OONIFINDING_PUBLIC_KEYS)

    r = client_with_user_role.get("api/v1/incidents/search?only_mine=false")
    incidents = r.json()["incidents"]
    assert len(incidents) == 2
    for incident in incidents:
        assert incident["email_address"] == ""
        assert incident["mine"] is False
        assert sorted(incident.keys()) == sorted(EXPECTED_OONIFINDING_PUBLIC_KEYS)

    r = client_with_admin_role.get("api/v1/incidents/search?only_mine=false")
    incidents = r.json()["incidents"]
    assert len(incidents) == 2
    for incident in incidents:
        assert incident["email_address"] == SAMPLE_EMAIL
        assert incident["mine"] is True
        assert sorted(incident.keys()) == sorted(EXPECTED_OONIFINDING_PUBLIC_KEYS)

    r = client.get("api/v1/incidents/search?only_mine=true")
    assert r.status_code == 200
    incidents = r.json()["incidents"]
    assert len(incidents) == 0

    r = client_with_user_role.get("api/v1/incidents/search?only_mine=true")
    assert r.status_code == 200
    incidents = r.json()["incidents"]
    assert len(incidents) == 0

    client_account_with_user_role = client_with_hashed_email(SAMPLE_EMAIL, "user")

    r = client_account_with_user_role.get("api/v1/incidents/search?only_mine=true")
    assert r.status_code == 200
    incidents = r.json()["incidents"]
    assert len(incidents) == 2
    for incident in incidents:
        assert incident["email_address"] == ""
        assert incident["mine"] is True
        assert sorted(incident.keys()) == sorted(EXPECTED_OONIFINDING_PUBLIC_KEYS)

    r = client_with_admin_role.get("api/v1/incidents/search?only_mine=true")
    assert r.status_code == 200
    incidents = r.json()["incidents"]
    assert len(incidents) == 2
    for incident in incidents:
        assert incident["email_address"] == SAMPLE_EMAIL
        assert incident["mine"] is True
        assert sorted(incident.keys()) == sorted(EXPECTED_OONIFINDING_PUBLIC_KEYS)


def test_oonifinding_create(client, client_with_hashed_email, client_with_user_role):
    client_with_admin_role = client_with_hashed_email(SAMPLE_EMAIL, "admin")

    z = deepcopy(SAMPLE_OONIFINDING)
    z["themes"] = ["social_media"]
    z["CCs"] = ["IT", "GR"]
    z["domains"] = ["www.facebook.com"]
    z["slug"] = "this-is-my-slug"
    z["ASNs"] = [1234]
    z["published"] = True
    z["start_time"] = sample_start_time
    z["end_time"] = sample_end_time

    r = client_with_admin_role.post("api/v1/incidents/create", json=z)
    assert r.status_code == 200
    assert r.json()["r"] == 1
    assert r.headers["Cache-Control"] == "no-cache"

    incident_id = r.json()["id"]
    assert incident_id

    r = client.get(f"api/v1/incidents/show/{incident_id}")
    assert r.status_code == 200
    j = r.json()
    assert j["incident"]["themes"] == ["social_media"]
    assert j["incident"]["start_time"] == sample_start_time
    assert j["incident"]["end_time"] == sample_end_time

    r = client.get(f"api/v1/incidents/show/this-is-my-slug")
    assert r.status_code == 200
    j = r.json()
    assert j["incident"]["id"] == incident_id

    r = client.get(f"api/v1/incidents/search?theme=social_media")
    assert r.status_code == 200
    j = r.json()
    assert len(j["incidents"]) == 1

    assert j["incidents"][0]["themes"] == ["social_media"]

    r = client.get(f"api/v1/incidents/search?country_code=IT")
    assert r.status_code == 200
    j = r.json()
    assert len(j["incidents"]) == 1

    assert j["incidents"][0]["themes"] == ["social_media"]

    r = client.get(f"api/v1/incidents/search?domain=www.facebook.com")
    assert r.status_code == 200
    j = r.json()
    assert len(j["incidents"]) == 1

    assert j["incidents"][0]["themes"] == ["social_media"]

    r = client.get(f"api/v1/incidents/search?domain=example.com")
    assert r.status_code == 200
    j = r.json()
    assert len(j["incidents"]) == 0

    r = client.get(f"api/v1/incidents/search?asn=1234")
    assert r.status_code == 200
    j = r.json()
    assert len(j["incidents"]) == 1

    assert j["incidents"][0]["themes"] == ["social_media"]
