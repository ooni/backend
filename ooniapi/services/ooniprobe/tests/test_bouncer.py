"""
Integration test for OONIProbe API
"""


def test_get_bouncer_nettests(client):
    version = "1"

    r = client.post("/bouncer/net-tests", json={"net-tests": [{"name": "foo", "version": version}]})
    j = r.json()
    assert "net-tests" in j
    for v in j["net-tests"]:
        for x in ["collector", "input-hashes", "name", "test-helpers", "test-helpers-alternate", "version"]:
            assert x in v

def test_bouncer_net_tests(client):
    j = {
        "net-tests": [
            {
                "input-hashes": None,
                "name": "web_connectivity",
                "test-helpers": ["web-connectivity"],
                "version": "0.0.1",
            }
        ]
    }
    c = client.post("/bouncer/net-tests", json=j)
    expected = {
        "net-tests": [
            {
                "collector": "httpo://guegdifjy7bjpequ.onion",
                "collector-alternate": [
                    {"type": "https", "address": "https://ams-pg.ooni.org"},
                    {
                        "front": "dkyhjv0wpi2dk.cloudfront.net",
                        "type": "cloudfront",
                        "address": "https://dkyhjv0wpi2dk.cloudfront.net",
                    },
                ],
                "name": "web_connectivity",
                "test-helpers": {
                    "tcp-echo": "37.218.241.93",
                    "http-return-json-headers": "http://37.218.241.94:80",
                    "web-connectivity": "httpo://y3zq5fwelrzkkv3s.onion",
                },
                "test-helpers-alternate": {
                    "web-connectivity": [
                        {"type": "https", "address": "https://wcth.ooni.io"},
                        {
                            "front": "d33d1gs9kpq1c5.cloudfront.net",
                            "type": "cloudfront",
                            "address": "https://d33d1gs9kpq1c5.cloudfront.net",
                        },
                    ]
                },
                "version": "0.0.1",
                "input-hashes": None,
            }
        ]
    }
    assert c.json() == expected


def test_bouncer_net_tests_bad_request1(client):
    resp = client.post("/bouncer/net-tests")
    # XXX: fastapi returns 422 Unprocessable Entity; expected result was 400 in old test
    assert resp.status_code != 200


def test_bouncer_net_tests_bad_request2(client):
    j = {"net-tests": []}
    resp = client.post("/bouncer/net-tests", json=j)
    # XXX: fastapi returns 422 Unprocessable Entity; expected result was 400 in old test
    assert resp.status_code != 200
