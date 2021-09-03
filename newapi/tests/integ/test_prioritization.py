"""
Integration test for URL prioritization
Lint using Black.
Test using:
    pytest-3 -s --show-capture=no ooniapi/tests/integ/test_prioritization.py
"""

import pytest

def getjson(client, url):
    response = client.get(url)
    assert response.status_code == 200
    assert response.is_json
    return response.json


def test_url_prioritization(client):
    c = getjson(client, "/api/v1/test-list/urls?limit=100")
    assert "metadata" in c
    assert c["metadata"] == {
        "count": 100,
        "current_page": -1,
        "limit": -1,
        "next_url": "",
        "pages": 1,
    }

    assert len(set(r["url"] for r in c["results"])) == 100


def test_url_prioritization_category_code(client):
    c = getjson(client, "/api/v1/test-list/urls?category_codes=NEWS&limit=100")
    assert "metadata" in c
    assert c["metadata"] == {
        "count": 100,
        "current_page": -1,
        "limit": -1,
        "next_url": "",
        "pages": 1,
    }
    for r in c["results"]:
        assert r["category_code"] == "NEWS"

    assert len(set(r["url"] for r in c["results"])) == 100


def test_url_prioritization_category_codes(client):
    c = getjson(
        client,
        "/api/v1/test-list/urls?category_codes=NEWS,HUMR&country_code=US&limit=100",
    )
    assert "metadata" in c
    assert c["metadata"] == {
        "count": 100,
        "current_page": -1,
        "limit": -1,
        "next_url": "",
        "pages": 1,
    }
    for r in c["results"]:
        assert r["category_code"] in ("NEWS", "HUMR")

    assert len(set(r["url"] for r in c["results"])) == 100


def test_url_prioritization_country_code_limit(client):
    c = getjson(client, "/api/v1/test-list/urls?country_code=US&limit=999")
    assert "metadata" in c
    assert c["metadata"] == {
        "count": 999,
        "current_page": -1,
        "limit": -1,
        "next_url": "",
        "pages": 1,
    }
    for r in c["results"]:
        assert r["country_code"] in ("XX", "US")

    assert len(set(r["url"] for r in c["results"])) == 999


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
