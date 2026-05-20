from ooniprobe.utils import check_measurement_meta, get_first_ip


def test_check_measurement_meta_http_header_field_manipulation():
    test_name = "http_header_field_manipulation"
    assert len(test_name) == 30
    check_measurement_meta(test_name, "US", "AS30722")


def test_get_first_ip():

    assert get_first_ip("1.1.1.1") == "1.1.1.1"
    assert get_first_ip("1.1.1.1, 2.2.2.2") == "1.1.1.1"
    assert get_first_ip("") == ""