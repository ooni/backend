import pytest

from ooniprobe.common import prio


def test_prio():
    cz = {
        "category_code": "MISC",
        "domain": "thehiddenwiki.org",
        "url": "https://thehiddenwiki.org/",
        "cc": "ZZ",
        "msmt_cnt": 38,
    }
    pr = {
        "category_code": "MISC",
        "cc": "US",
        "domain": "*",
        "priority": -200,
        "url": "*",
    }
    assert prio.match_prio_rule(cz, pr)
    pr = {
        "category_code": "BOGUS",
        "cc": "US",
        "domain": "*",
        "priority": -200,
        "url": "*",
    }
    assert not prio.match_prio_rule(cz, pr)
    pr = {
        "category_code": "MISC",
        "cc": "US",
        "domain": "BOGUS",
        "priority": -200,
        "url": "*",
    }
    assert not prio.match_prio_rule(cz, pr)
    pr = {
        "category_code": "MISC",
        "cc": "US",
        "domain": "*",
        "priority": -200,
        "url": "BOGUS",
    }
    assert not prio.match_prio_rule(cz, pr)


def test_prio_cc_1():
    cz = {"cc": "ZZ"}
    pr = {"cc": "US"}
    for k in ["category_code", "domain", "url"]:
        cz[k] = pr[k] = ""
    assert prio.match_prio_rule(cz, pr)


def test_prio_cc_2():
    cz = {"cc": "US"}
    pr = {"cc": "US"}
    for k in ["category_code", "domain", "url"]:
        cz[k] = pr[k] = ""
    assert prio.match_prio_rule(cz, pr)


def test_prio_cc_3():
    cz = {"cc": "US"}
    pr = {"cc": "*"}
    for k in ["category_code", "domain", "url"]:
        cz[k] = pr[k] = ""
    assert prio.match_prio_rule(cz, pr)


def test_prio_cc_4():
    cz = {"cc": "US"}
    pr = {"cc": "IE"}
    for k in ["category_code", "domain", "url"]:
        cz[k] = pr[k] = ""
    assert not prio.match_prio_rule(cz, pr)


def test_compute_priorities():
    entries = [
        {
            "category_code": "MISC",
            "domain": "thehiddenwiki.org",
            "url": "https://thehiddenwiki.org/",
            "cc": "ZZ",
            "msmt_cnt": 38,
        }
    ]
    prio_rules = [
        {"category_code": "MISC", "cc": "*", "domain": "*", "priority": 20, "url": "*"},
        {
            "category_code": "MISC",
            "cc": "US",
            "domain": "*",
            "priority": -200,
            "url": "*",
        },
    ]
    out = prio.compute_priorities(entries, prio_rules)
    assert out == [
        {
            "category_code": "MISC",
            "cc": "ZZ",
            "domain": "thehiddenwiki.org",
            "msmt_cnt": 38,
            "priority": -180,
            "url": "https://thehiddenwiki.org/",
            "weight": -4.7368421052631575,
        }
    ]


def test_compute_priorities_country_list():
    entries = [
        {
            "category_code": "HUMR",
            "domain": "ooni.org",
            "url": "https://ooni.org/",
            "cc": "it",
            "msmt_cnt": 38,
        }
    ]
    prio_rules = [
        {
            "category_code": "*",
            "cc": "IT",
            "domain": "ooni.org",
            "priority": 20,
            "url": "*",
        },
        {
            "category_code": "*",
            "cc": "IT",
            "domain": "ooni.org",
            "priority": 400,
            "url": "*",
        },
    ]
    out = prio.compute_priorities(entries, prio_rules)
    assert out == [
        {
            "category_code": "HUMR",
            "cc": "it",
            "domain": "ooni.org",
            "msmt_cnt": 38,
            "priority": 420,
            "url": "https://ooni.org/",
            "weight": 11.052631578947368,
        }
    ]


@pytest.mark.asyncio
async def test_show_countries_prioritization(client):
    c = client.get("/api/_/show_countries_prioritization").json()
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


@pytest.mark.asyncio
async def test_show_countries_prioritization_csv(client):
    resp = client.get("/api/_/show_countries_prioritization?format=CSV")
    assert resp.status_code == 200
    assert resp.headers["content-type"] != "application/json"


@pytest.mark.asyncio
async def test_debug_prioritization(client):
    resp = client.get(
        "/api/_/debug_prioritization?probe_cc=ZZ&category_codes=GOVT&probe_asn=4242"
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/json"

    resp = client.get("/api/_/debug_prioritization")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/json"


def test_compute_priorities_random_tie_break():
    # 20 URLs with the same weight and one with a higher weight
    entries = [
        {"category_code": "NEWS", "domain": f"d{i}.org", "url": f"https://d{i}.org/", "cc": "ZZ", "msmt_cnt": 0}
        for i in range(20)
    ]
    entries.append({"category_code": "NEWS", "domain": "top.org", "url": "https://top.org/", "cc": "ZZ", "msmt_cnt": 0})
    prio_rules = [
        {"category_code": "NEWS", "cc": "*", "domain": "*", "priority": 100, "url": "*"},
        {"category_code": "*", "cc": "*", "domain": "top.org", "priority": 100, "url": "*"},
    ]
    orders = set()
    for _ in range(20):
        out = prio.compute_priorities(entries, prio_rules)
        # the ranking holds: highest weight first, weights never increase
        assert out[0]["url"] == "https://top.org/"
        assert [o["weight"] for o in out] == sorted((o["weight"] for o in out), reverse=True)
        orders.add(tuple(o["url"] for o in out[1:]))
    # the 20 tied URLs come out in different orders; all 20 runs giving the
    # same order has probability 20!^-19
    assert len(orders) > 1
