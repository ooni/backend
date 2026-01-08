def test_tor_targets(client):
    resp = client.get("/api/v1/test-list/tor-targets").json()
    for i, target in resp.items():
        assert i is not None
        for k in ["address", "fingerprint", "name", "protocol"]:
            assert k in target
