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
    url = f"/api/v1/test-list/urls?category_codes=NEWS,CULTR&country_code=US&limit={lim}"
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


@pytest.mark.skip("needs mock db")
def test_url_prioritization_country_code_limit(client):
    lim = 2
    c = getjson(client, f"/api/v1/test-list/urls?country_code=US&limit={lim}")
    assert "metadata" in c
    assert c["metadata"] == {
        "count": lim,
        "current_page": -1,
        "limit": -1,
        "next_url": "",
        "pages": 1,
    }
    for r in c["results"]:
        assert r["country_code"] in ("XX", "US")

    assert len(set(r["url"] for r in c["results"])) == lim


@pytest.mark.skip("needs mock db")
def test_url_prioritization_country_code_nolimit(client):
    c = getjson(client, "/api/v1/test-list/urls?country_code=US")
    assert "metadata" in c
    xx_cnt = 0
    for r in c["results"]:
        assert r["country_code"] in ("XX", "US")
        if r["country_code"] == "XX":
            xx_cnt += 1

    assert xx_cnt > 1200
    us_cnt = c["metadata"]["count"] - xx_cnt
    assert us_cnt > 40
