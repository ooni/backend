def test_api_smoke(client):
    response = client.get("/api/v1/files")
    assert response.status_code == 200

    response = client.get("/api/v1/measurements")
    assert response.status_code == 200

    response = client.get("/api/v1/measurements?domain=ooni.io")
    assert response.status_code == 200
