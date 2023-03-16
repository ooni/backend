from ooniapi.countries import lookup_country


def test_lookup():
    assert lookup_country("IT") == "Italy"
