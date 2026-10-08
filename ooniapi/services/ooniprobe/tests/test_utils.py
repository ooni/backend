import pytest
from fastapi import HTTPException
from ooniprobe.common.utils import InvalidForwardedFor, TrustedProxies, client_ipaddr
from ooniprobe.utils import check_measurement_meta


def test_check_measurement_meta_http_header_field_manipulation():
    test_name = "http_header_field_manipulation"
    assert len(test_name) == 30
    check_measurement_meta(test_name, "US", "AS30722")


def test_check_measurement_meta_asn_leading_zeros():
    # Valid ASN
    check_measurement_meta("web_connectivity", "IT", "AS123")

    # Invalid ASNs with leading zeros
    with pytest.raises(HTTPException) as e:
        check_measurement_meta("web_connectivity", "IT", "AS07")
    assert e.value.status_code == 400
    assert "asn_leading_zero" in str(e.value.detail)

    with pytest.raises(HTTPException) as e:
        check_measurement_meta("web_connectivity", "IT", "AS007")
    assert e.value.status_code == 400
    assert "asn_leading_zero" in str(e.value.detail)

    # AS0 is also invalid but for a different reason
    with pytest.raises(HTTPException) as e:
        check_measurement_meta("web_connectivity", "IT", "AS0")
    assert e.value.status_code == 400
    assert "asn_leading_zero" not in str(e.value.detail)


def test_client_ipaddr():
    # the last entry is the one our proxy appended; earlier ones are the client's
    assert client_ipaddr(["1.1.1.1"], "10.0.0.1", TrustedProxies([])) == "1.1.1.1"
    assert client_ipaddr(["1.1.1.1, 2.2.2.2"], "10.0.0.1", TrustedProxies([])) == "2.2.2.2"
    assert client_ipaddr(["1.1.1.1", "2.2.2.2"], "10.0.0.1", TrustedProxies([])) == "2.2.2.2"
    # trusted proxies are skipped from the right
    assert client_ipaddr(["1.1.1.1, 2.2.2.2"], "10.0.0.1", TrustedProxies(["2.2.2.2"])) == "1.1.1.1"
    assert client_ipaddr(["1.1.1.1, 2.2.2.2"], "10.0.0.1", TrustedProxies(["2.2.0.0/16"])) == "1.1.1.1"
    # no header: the peer
    assert client_ipaddr([], "10.0.0.1", TrustedProxies([])) == "10.0.0.1"
    assert client_ipaddr([], None, TrustedProxies([])) == ""


def test_client_ipaddr_rejects_what_our_proxies_should_not_write():
    # whatever the client writes further left is never reached
    assert client_ipaddr(["not-an-ip, 2.2.2.2"], "10.0.0.1", TrustedProxies([])) == "2.2.2.2"
    assert client_ipaddr(["not-an-ip, 1.1.1.1, 2.2.2.2"], "10.0.0.1", TrustedProxies(["2.2.2.2"])) == "1.1.1.1"
    # an entry our proxy appended that isn't a bare address is an error
    for entry in ("2.2.2.2:51234", "[2001:db8::1]:443", "unknown"):
        with pytest.raises(InvalidForwardedFor):
            client_ipaddr([f"1.1.1.1, {entry}"], "10.0.0.1", TrustedProxies([]))
    # only trusted proxies: the chain doesn't say who the client is
    for xff in (["2.2.2.2"], ["2.2.2.3, 2.2.2.2"]):
        with pytest.raises(InvalidForwardedFor):
            client_ipaddr(xff, "10.0.0.1", TrustedProxies(["2.2.2.0/24"]))

