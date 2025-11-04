def test_geolookup(client):
    j = dict(
        addresses=["192.33.4.12", "170.247.170.2", "2801:1b8:10::b", "2001:500:2::c"]
    )
    c = client.post("/api/v1/geolookup", json=j).json()
    assert "geolocation" in c
    assert "v" in c
    g = c["geolocation"]
    for ip in j["addresses"]:
        assert g[ip]["cc"] != "ZZ"
        assert g[ip]["asn"] != "AS0"
        assert g[ip]["as_name"] is not None
