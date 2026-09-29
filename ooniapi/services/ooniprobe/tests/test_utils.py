import pytest
from fastapi import HTTPException
from ooniprobe.utils import check_measurement_meta, get_first_ip


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


def test_get_first_ip():

    assert get_first_ip("1.1.1.1") == "1.1.1.1"
    assert get_first_ip("1.1.1.1, 2.2.2.2") == "1.1.1.1"
    assert get_first_ip("") == ""
