"""
Integration test for OONIFindings API
"""

from typing import Dict, List
from copy import deepcopy
from datetime import timedelta

from oonifindings.routers.v1 import utcnow_seconds

sample_start_time = (utcnow_seconds() + timedelta(minutes=-1)).strftime(
    "%Y-%m-%dT%H:%M:%S.%fZ"
)

SAMPLE_EMAIL = "sample@ooni.org"

SAMPLE_OONIFINDING = {
    "id": "",
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
        "IN", "TZ",
    ],
    "tags": [],
    "test_names": [
        "webconnectivity",
    ],
    "domains": [
        "www.google.com"
    ],
    "links": []
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
    http_client = client_with_hashed_email(SAMPLE_EMAIL, "admin")
    
    z = deepcopy(SAMPLE_OONIFINDING)
    
    z["email_address"] = ""
    r = http_client.post("api/v1/incidents/create", json=z)
    assert r.status_code == 400, "email hash does not match with account id"
    
    z["email_address"] = SAMPLE_EMAIL 
    z["title"] = ""
    r = http_client.post("api/v1/incidents/create", json=z)
    assert r.status_code == 422, "empty title should be rejected"
    
    z["title"] = "sample oonifinding"
    z["text"] = ""
    r = http_client.post("api/v1/incidents/create", json=z)
    assert r.status_code == 422, "empty text should be rejected"

    z["text"] = "sample text for oonifinding incident"
    r = http_client.post("api/v1/incidents/create", json=z)
    assert r.status_code == 200, "email hash does not match with account id"


def test_oonifinding_publish(client, client_with_hashed_email):
    client_with_admin_role = client_with_hashed_email(SAMPLE_EMAIL, "admin")
    client_with_user_role = client_with_hashed_email(SAMPLE_EMAIL, "user")

    z = deepcopy(SAMPLE_OONIFINDING)
    
    z["published"] = True
    r = client_with_admin_role.post("/api/v1/incidents/create", json=z)
    assert r.status_code == 400, "published true should be rejected"

    z["published"] = False
    r = client_with_admin_role.post("/api/v1/incidents/create", json=z)
    assert r.status_code == 200
    assert r.json()["r"] == 1

    incident_id = r.json()["id"]
    assert incident_id

    r = client_with_admin_role.get(f"api/v1/incidents/show/{incident_id}")
    incident_payload = r.json()["incident"]
    
    r = client_with_admin_role.post("api/v1/incidents/random", json=incident_payload)
    assert r.status_code == 400, "only publish and unpublish are valid supported actions"

    r = client_with_user_role.post("api/v1/incidents/publish", json=incident_payload)
    assert r.status_code == 401, "only admins can publish incidents"

    incident_payload["id"] = "sample id"
    r = client_with_admin_role.post("api/v1/incidents/publish", json=incident_payload)
    assert r.status_code == 404, "valid incident id should be passed"

    incident_payload["id"] = incident_id
    r = client_with_admin_role.post("api/v1/incidents/publish", json=incident_payload)
    assert r.status_code == 200
    assert r.json()["r"] == 1
    assert r.json()["id"] == incident_id

    r = client_with_admin_role.get(f"api/v1/incidents/show/{incident_id}")
    incident = r.json()["incident"]
    assert incident
    assert incident["published"] is True

    r = client_with_admin_role.post("api/v1/incidents/unpublish", json=incident_payload)
    assert r.status_code == 200
    assert r.json()["r"] == 1
    assert r.json()["id"] == incident_id

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

    incident_id = r.json()["id"]
    assert incident_id

    z["id"] = incident_id
    r = client_with_admin_role.post("api/v1/incidents/delete", json=z)
    assert r.status_code == 200

    r = client_with_admin_role.post("api/v1/incidents/create", json=z)
    assert r.status_code == 200
    assert r.json()["r"] == 1

    incident_id = r.json()["id"]
    assert incident_id

    z["id"] = incident_id
    z["email_address"] = ""
    r = client_with_user_role.post("api/v1/incidents/delete", json=z)
    assert r.status_code == 400

    z["email_address"] = SAMPLE_EMAIL
    mismatched_client = client_with_hashed_email("user@ooni.org", "user")
    r = mismatched_client.post("api/v1/incidents/delete", json=z)
    assert r.status_code == 400

    r = client_with_user_role.post("api/v1/incidents/delete", json=z)
    assert r.status_code == 200

    r = client_with_admin_role.get(f"api/v1/incidents/show/{incident_id}")
    assert r.status_code == 404


def test_oonifinding_update(client, client_with_hashed_email):
    client_with_admin_role = client_with_hashed_email(SAMPLE_EMAIL, "admin")
    client_with_user_role = client_with_hashed_email(SAMPLE_EMAIL, "user")

    z = deepcopy(SAMPLE_OONIFINDING)

    r = client_with_admin_role.post("api/v1/incidents/create", json=z)
    assert r.status_code == 200
    assert r.json()["r"] == 1

    incident_id = r.json()["id"]
    assert incident_id

    r = client_with_admin_role.get(f"api/v1/incidents/show/{incident_id}")
    incident_payload = r.json()["incident"]

    sample_replacement_text = "sample replacement text for update"
    incident_payload["text"] = sample_replacement_text
    r = client_with_admin_role.post("api/v1/incidents/update", json=incident_payload)
    assert r.json()["r"] == 1
    assert r.json()["id"] == incident_id
    
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
    assert r.status_code == 400, "cannot update with invalid email"

    incident_payload["email_address"] = SAMPLE_EMAIL
    mismatched_client = client_with_hashed_email("user@ooni.org", "user")
    r = mismatched_client.post("api/v1/incidents/update", json=incident_payload)
    assert r.status_code == 400, "email should match account id"

    r = client_with_user_role.post("api/v1/incidents/update", json=incident_payload)
    assert r.status_code == 200
    assert r.json()["r"] == 1
    assert r.json()["id"] == incident_id

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

    r = client_with_admin_role.get(f"api/v1/incidents/show/{incident_id}")
    incident_payload = r.json()["incident"]
    assert incident_payload
    assert len(incident_payload["tags"]) == 1
    assert incident_payload["tags"][0] == sample_tag

    incident_payload["published"] = True
    r = client_with_user_role.post("api/v1/incidents/update", json=incident_payload)
    assert r.status_code == 400, "user role cannot publish incident" 

    r = client_with_admin_role.post("api/v1/incidents/update", json=incident_payload)
    assert r.status_code == 200
    assert r.json()["r"] == 1
    assert r.json()["id"] == incident_id

    r = client_with_admin_role.get(f"api/v1/incidents/show/{incident_id}")
    incident_payload = r.json()["incident"]
    assert incident_payload
    assert incident_payload["published"] == True


# TODO(decfox): add checks for fetched incident fields
def test_oonifinding_workflow(
        client, 
        client_with_hashed_email, 
        client_with_user_role
    ):
    client_with_admin_role = client_with_hashed_email(SAMPLE_EMAIL, "admin")
    
    z = deepcopy(SAMPLE_OONIFINDING)

    r = client_with_admin_role.post("api/v1/incidents/create", json=z)
    assert r.status_code == 200
    assert r.json()["r"] == 1

    incident_id = r.json()["id"]
    assert incident_id

    r = client.get(f"api/v1/incidents/show/{incident_id}")
    assert r.status_code == 404, "unpublished events cannot be seen with invalid account id"
    
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
    assert len(incidents) == 2
    for incident in incidents:
        assert incident["email_address"] == ""
        assert incident["mine"] is False
        assert sorted(incident.keys()) == sorted(EXPECTED_OONIFINDING_PUBLIC_KEYS)

    
    r = client_with_user_role.get("api/v1/incidents/search?only_mine=false")
    incidents = r.json()["incidents"]
    assert len(incidents) == 4
    for incident in incidents:
        assert incident["email_address"] == ""
        assert incident["mine"] is False
        assert sorted(incident.keys()) == sorted(EXPECTED_OONIFINDING_PUBLIC_KEYS)

    r = client_with_admin_role.get("api/v1/incidents/search?only_mine=false")
    incidents = r.json()["incidents"]
    assert len(incidents) == 4
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
    assert len(incidents) == 4
    for incident in incidents:
        assert incident["email_address"] == ""
        assert incident["mine"] is True
        assert sorted(incident.keys()) == sorted(EXPECTED_OONIFINDING_PUBLIC_KEYS)

    r = client_with_admin_role.get("api/v1/incidents/search?only_mine=true")
    assert r.status_code == 200
    incidents = r.json()["incidents"]
    assert len(incidents) == 4
    for incident in incidents:
        assert incident["email_address"] == SAMPLE_EMAIL
        assert incident["mine"] is True
        assert sorted(incident.keys()) == sorted(EXPECTED_OONIFINDING_PUBLIC_KEYS)
