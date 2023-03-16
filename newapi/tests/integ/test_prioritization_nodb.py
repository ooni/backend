"""
Integration test for URL prioritization with mocked database
Uses data from tests/integ/data/
Lint using Black.
Test using:
    pytest-3 -s --show-capture=no ooniapi/tests/integ/test_prioritization_nodb.py
"""

import json
from pathlib import Path

import pytest
from mock import MagicMock

# Extract database responses with:
# COPY (SELECT json_agg(t) FROM (...) t) TO '/tmp/<name>.json';

queries = {
    (
        "SELECT category_code, priority, url FROM citizenlab WHERE cc = 'ZZ' ORDER BY priority DESC"
    ): Path("citizenlab.json"),
    (
        "SELECT category_code, domain, url, cc, COALESCE(msmt_cnt, 0)::float AS msmt_cnt FROM ( SELECT domain, url, cc, category_code FROM citizenlab WHERE citizenlab.cc = :cc_low OR citizenlab.cc = :cc OR citizenlab.cc = 'ZZ' ) AS citiz LEFT OUTER JOIN ( SELECT input, msmt_cnt FROM counters_test_list WHERE probe_cc = :cc ) AS cnt ON (citiz.url = cnt.input)"
    ): Path("citizenlab_counters_us.json"),
    (
        "SELECT category_code, cc, domain, url, priority FROM url_priorities WHERE cc = :cc OR cc = '*'"
    ): Path("url_priorities_us.json"),
}


def mockdb(query, *query_kw):
    """Mocked app.db_session.execute"""
    query = " ".join(x.strip() for x in query.splitlines()).strip()
    print(f"     {query} --")
    if query in queries:
        resp = queries[query]
        if isinstance(resp, Path):
            fn = Path("tests/integ/data") / resp
            print(f"       loading {fn}")
            with fn.open() as f:
                j = json.load(f)

            r = MagicMock(side_effect=iter(j))
            r.fetchall.return_value = j
            return r

    assert query == "", "Unexpected query to be mocked out: " + repr(query)


@pytest.fixture
def nodb(app):
    if hasattr(app, "db_session"):
        app.db_session.execute = mockdb


def getjson(client, url):
    response = client.get(url)
    assert response.status_code == 200
    assert response.is_json
    return response.json


def test_url_prioritization(client, nodb):
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


def test_url_prioritization_category_code(client, nodb):
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


def test_url_prioritization_category_codes(client, nodb):
    url = "/api/v1/test-list/urls?category_codes=NEWS,HUMR&country_code=US&limit=100"
    c = getjson(client, url)
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


def test_url_prioritization_country_code_limit_debug(client, nodb):
    c = getjson(client, "/api/v1/test-list/urls?country_code=US&limit=9999&debug=true")
    assert "metadata" in c
    assert c["metadata"] == {
        "count": 1513,
        "current_page": -1,
        "limit": -1,
        "next_url": "",
        "pages": 1,
    }
    for r in c["results"]:
        assert r["country_code"] in ("XX", "US")

    assert len(c["results"]) == 1513


def test_url_prioritization_country_code_nolimit(client, nodb):
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
