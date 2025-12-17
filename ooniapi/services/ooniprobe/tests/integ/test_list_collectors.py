def test_list_collectors(client):
    c = client.get("/api/v1/collectors").json()
    assert len(c) == 6
    for entry in c:
        assert "address" in entry
