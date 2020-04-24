import time
import random
from collections import Counter

import pytest

import prio


def test_algo_chao():
    random.seed(3)
    entries = [
        {"priority": 500, "name": "heavy"},
        {"priority": 200, "name": "b"},
        {"priority": 150, "name": "c"},
        {"priority": 50, "name": "uncommon"},
    ] + [{"priority": 100, "name": "None"},] * 95

    c = Counter()
    for x in range(1, 10000):
        selected = prio.algo_chao(entries, 1)
        c.update([s["name"] for s in selected])

    assert c.most_common() == [
        ("None", 9060),
        ("heavy", 494),
        ("b", 221),
        ("c", 173),
        ("uncommon", 51),
    ]


def test_generate_test_list_no_country():
    prio.last_update_time = time.time()
    prio.test_items = {}
    with pytest.raises(Exception):
        prio.generate_test_list("XY", [], 10)


def test_generate_test_list_bug():
    prio.last_update_time = time.time()
    prio.test_items = {"IE": {"NEWS": []}}
    tl = prio.generate_test_list("IE", "NEWS", 10)
    assert not tl


def test_generate_test_list_3():
    random.seed(3)
    prio.last_update_time = time.time()
    prio.test_items = {
        "IE": {
            "NEWS": [
                {"priority": 100, "category_code": "NEWS", "url": "url1", "cc": "IE"},
                {"priority": 200, "category_code": "NEWS", "url": "url2", "cc": "IE"},
                {"priority": 300, "category_code": "NEWS", "url": "url3", "cc": "IE"},
            ]
        }
    }
    tl = prio.generate_test_list("IE", "NEWS", 2)
    assert [i["url"] for i in tl] == ["url3", "url2"]

    tl = prio.generate_test_list("IE", "NEWS", 2)
    assert [i["url"] for i in tl] == ["url1", "url3"]


def test_generate_test_list_categories():
    random.seed(3)
    prio.last_update_time = time.time()
    prio.test_items = {
        "IE": {
            "NEWS": [
                {"priority": 100, "category_code": "NEWS", "url": "url1", "cc": "IE"},
            ],
            "ANON": [
                {"priority": 200, "category_code": "ANON", "url": "url2", "cc": "IE"},
            ],
            "FILE": [
                {"priority": 300, "category_code": "FILE", "url": "url3", "cc": "IE"},
            ],
        }
    }
    tl = prio.generate_test_list("IE", "NEWS", 3)
    assert [i["url"] for i in tl] == ["url1"], tl

    tl = prio.generate_test_list("IE", "NEWS,ANON", 3)
    assert [i["url"] for i in tl] == ["url1", "url2"], tl

    tl = prio.generate_test_list("IE", "ANON,FILE", 3)
    assert [i["url"] for i in tl] == ["url2", "url3"], tl
