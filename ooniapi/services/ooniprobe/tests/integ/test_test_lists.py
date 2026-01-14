from ..utils import getj


def test_url_prioritization(client, load_url_priorities):
    c = getj(client, "/api/v1/test-list/urls?limit=100")
    assert "metadata" in c
    assert c["metadata"]["count"] > 1
    c["metadata"]["count"] = 0
    assert c["metadata"] == {
        "count": 0,
        "current_page": -1,
        "limit": -1,
        "next_url": "",
        "pages": 1,
    }

    assert set(r["url"] for r in c["results"])


def test_url_prioritization_category_code(client, load_url_priorities):
    c = getj(client, "/api/v1/test-list/urls?category_codes=NEWS&limit=100")
    assert "metadata" in c
    for r in c["results"]:
        assert r["category_code"] == "NEWS"

    assert set(r["url"] for r in c["results"])


def test_url_prioritization_category_codes(client, load_url_priorities):
    c = getj(
        client,
        "/api/v1/test-list/urls?category_codes=NEWS,HUMR&country_code=US&limit=100",
    )
    assert "metadata" in c
    for r in c["results"]:
        assert r["category_code"] in ("NEWS", "HUMR")

    assert set(r["url"] for r in c["results"])


def test_url_prioritization_country_code_limit(client, load_url_priorities):
    c = getj(client, "/api/v1/test-list/urls?country_code=US&limit=4")
    assert "metadata" in c
    assert c["metadata"]["count"] > 1
    c["metadata"]["count"] = 0
    assert c["metadata"] == {
        "count": 0,
        "current_page": -1,
        "limit": -1,
        "next_url": "",
        "pages": 1,
    }
    for r in c["results"]:
        assert r["country_code"] in ("XX", "US")

    assert 4 >= len(set(r["url"] for r in c["results"])) > 0


def test_url_prioritization_country_code_nolimit(client, load_url_priorities):
    c = getj(client, "/api/v1/test-list/urls?country_code=US")
    assert "metadata" in c
    assert sum(1 for r in c["results"] if r["country_code"] == "XX")
