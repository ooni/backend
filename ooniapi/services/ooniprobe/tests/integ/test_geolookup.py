from typing import Tuple
import ooniprobe.routers.v1.probe_services as ps
from ooniprobe.dependencies import CCReaderDep, ASNReaderDep

def fake_lookup_probe_network(ipaddr: str, asn_reader: ASNReaderDep) -> Tuple[str, str]:
    return ("AS4242", "Testing Networks")

def fake_lookup_probe_cc(ipaddr: str, cc_reader: CCReaderDep) -> str:
    return "US"

def test_geolookup(client, monkeypatch):
    monkeypatch.setattr(ps, "lookup_probe_network", fake_lookup_probe_network)
    monkeypatch.setattr(ps, "lookup_probe_cc", fake_lookup_probe_cc)
    j = dict(
        addresses=["192.33.4.12", "170.247.170.2", "2801:1b8:10::b", "2001:500:2::c"]
    )
    c = client.post("/api/v1/geolookup", json=j).json()
    assert "geolocation" in c
    assert "v" in c
    g = c["geolocation"]

    for ip in j["addresses"]:
        assert g[ip]["cc"] == "US"
        assert g[ip]["asn"] == "AS4242"
        assert g[ip]["as_name"] == "Testing Networks"
