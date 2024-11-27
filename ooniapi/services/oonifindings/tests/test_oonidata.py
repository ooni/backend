def test_oonidata(client):
    r = client.get("api/v1/observations")
    j = r.json()
    assert isinstance(j["results"], list), j

    r = client.get("api/v1/analysis")
    j = r.json()
    assert isinstance(j["results"], list), j

    r = client.get("api/v1/aggregation/analysis")
    j = r.json()
    assert isinstance(j["results"], list), j

    r = client.get("api/v1/aggregation/observations")
    j = r.json()
    assert isinstance(j["results"], list), j
