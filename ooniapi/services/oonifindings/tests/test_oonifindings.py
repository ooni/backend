SAMPLE_OONIFINDING = {
    "id": "",
    "title": "sample oonifinding",
    "short_description": "sample oonifdining description",
    "reported_by": "sample user",
    "email_address": "sampleuser@ooni.org",
    "text": "this is a sample oonifinding incident",
    "published": False,
    "event_type": "incident",
    "ASNs": [
        ""
    ],
    "CCs": [
        "IN", "TZ",
    ],
    "tags": [
        "",
    ],
    "test_names": [
        "webconnectivity",
    ],
    "domains": [
        "www.google.com"
    ],
    "links": [
        "",
    ]
}

EXPECTED_OONIFINDING_PUBLIC_KEYS = [
    "id",
    "title",
    "short_description",
    "start_time",
    "end_time",
    "create_time",
    "update_time",
    "mine",
    "reported_by",
    "email_address",
    "text",
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


def test_oonifinding_creator_validation(client, client_with_user_role):
    pass