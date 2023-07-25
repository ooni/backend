"""
Unit test for OONIRn API
"""

import pytest

import ooniapi.oonirun as oor
from ooniapi.errors import EmptyTranslation


def test_date_conversion():
    ts = "2023-07-21T16:36:12.456Z"
    t = oor.from_timestamp(ts)
    assert oor.to_timestamp(t) == ts
    assert oor.to_db_date(t) == "2023-07-21 16:36:12.456"


def test_validate_translations_not_empty():
    desc = {
        "name": "foo",
        "name_intl": {
            "it": "",
        },
        "description": "integ-test description in English",
        "description_intl": {
        },
        "short_description": "integ-test short description in English",
        "short_description_intl": {
        },
    }
    with pytest.raises(EmptyTranslation):
        oor.validate_translations_not_empty(desc)


def test_compare_descriptors_true():
    a = {
        "name": "",
        "name_intl": {
            "it": "",
        },
        "description": "integ-test description in English",
        "description_intl": {
            "es": "integ-test descripción en español",
        },
        "short_description": "integ-test short description in English",
        "short_description_intl": {
            "it": "integ-test descrizione breve in italiano",
        },
        "icon": "",
        "author": "integ-test author",
        "nettests": [
            {
                "inputs": ["https://example.com/", "https://ooni.org/"],
                "options": {
                    "HTTP3Enabled": True,
                },
                "test_name": "web_connectivity",
            },
            {"test_name": "dnscheck"},
        ],
    }
    b = a.copy()
    b["author"] = "new value"
    assert oor.compare_descriptors(a, b)
    b = a.copy()
    b["icon"] = "new value"
    assert oor.compare_descriptors(a, b)
    b = a.copy()
    b["nettests"] = []
    assert oor.compare_descriptors(a, b)


def test_compare_descriptors_false():
    a = {
        "name": "",
        "name_intl": {
            "it": "",
        },
        "description": "integ-test description in English",
        "description_intl": {
            "es": "integ-test descripción en español",
        },
        "short_description": "integ-test short description in English",
        "short_description_intl": {
            "it": "integ-test descrizione breve in italiano",
        },
        "icon": "",
        "author": "integ-test author",
        "nettests": [
            {
                "inputs": ["https://example.com/", "https://ooni.org/"],
                "options": {
                    "HTTP3Enabled": True,
                },
                "test_name": "web_connectivity",
            },
            {"test_name": "dnscheck"},
        ],
    }
    b = a.copy()
    b["name_intl"]["it"] = "new value"
    assert oor.compare_descriptors(a, b) is False
    b = a.copy()
    b["short_description_intl"]["newlang"] = "new value"
    assert oor.compare_descriptors(a, b) is False
