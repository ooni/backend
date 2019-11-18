from measurements.countries import lookup_country


def test_lookup():
    c = lookup_country("IT")

    assert c.alpha_2 == "IT"
    assert c.name == "Italy"
