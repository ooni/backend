def test_oonidata(client):
    r = client.get("api/v1/observations?since=2024-11-01&until=2024-11-02")
    j = r.json()
    assert isinstance(j["results"], list), j
    assert len(j["results"]) > 0
    for result in j["results"]:
        assert "test_name" in result, result
        assert "probe_cc" in result, result

    r = client.get("api/v1/analysis?since=2024-11-01&until=2024-11-02&probe_cc=IT")
    j = r.json()
    assert isinstance(j["results"], list), j
    assert len(j["results"]) > 0
    for result in j["results"]:
        assert result["probe_cc"] == "IT"

    r = client.get(
        "api/v1/aggregation/analysis?since=2024-11-01&until=2024-11-10&probe_cc=IR"
    )
    j = r.json()
    assert isinstance(j["results"], list), j
    assert len(j["results"]) > 0
    for result in j["results"]:
        assert result["probe_cc"] == "IR"

    r = client.get(
        "api/v1/aggregation/observations?since=2024-11-01&until=2024-11-10&probe_cc=IT"
    )
    j = r.json()
    assert isinstance(j["results"], list), j
    assert len(j["results"]) > 0
    for result in j["results"]:
        assert result["probe_cc"] == "IT"
