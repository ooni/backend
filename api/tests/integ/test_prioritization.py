"""
Integration test for URL prioritization
Lint using Black.
Test using:
    pytest-3 -s --show-capture=no ooniapi/tests/integ/test_prioritization.py
"""

import pytest
from tests.utils import *


@pytest.mark.skip("needs mock db")
def test_url_prioritization(client):
    c = getjson(client, "/api/v1/test-list/urls?limit=2")
    assert "metadata" in c
    assert c["metadata"] == {
        "count": 2,
        "current_page": -1,
        "limit": -1,
        "next_url": "",
        "pages": 1,
    }

    assert len(set(r["url"] for r in c["results"])) == 2


def test_url_prioritization_category_code(client):
    lim = 1
    c = getjson(client, f"/api/v1/test-list/urls?category_codes=NEWS&limit={lim}")
    assert "metadata" in c
    assert c["metadata"] == {
        "count": lim,
        "current_page": -1,
        "limit": -1,
        "next_url": "",
        "pages": 1,
    }
    for r in c["results"]:
        assert r["category_code"] == "NEWS"

    assert len(set(r["url"] for r in c["results"])) == lim


def test_url_prioritization_category_codes(client):
    lim = 1
    url = (
        f"/api/v1/test-list/urls?category_codes=NEWS,CULTR&country_code=US&limit={lim}"
    )
    c = getjson(client, url)
    assert "metadata" in c
    assert c["metadata"] == {
        "count": lim,
        "current_page": -1,
        "limit": -1,
        "next_url": "",
        "pages": 1,
    }
    for r in c["results"]:
        assert r["category_code"] in ("NEWS", "CULTR")

    assert len(set(r["url"] for r in c["results"])) == lim


def test_show_countries_prioritization(client):
    c = getjson(client, "/api/_/show_countries_prioritization")
    assert len(c) > 10
    assert len(c) < 60000
    assert sorted(c[0].keys()) == [
        "anomaly_perc",
        "category_code",
        "cc",
        "domain",
        "msmt_cnt",
        "priority",
        "url",
    ]


def test_show_countries_prioritization_csv(client):
    resp = client.get("/api/_/show_countries_prioritization?format=CSV")
    assert not resp.is_json
