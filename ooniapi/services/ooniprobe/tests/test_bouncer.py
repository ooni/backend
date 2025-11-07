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
