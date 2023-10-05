#!/usr/bin/env python3

"""
Monitors test list for changes in URLs for some countries.
Outputs metrics.
"""

from time import sleep
import urllib.request
import json

import statsd  # debdeps: python3-statsd

metrics = statsd.StatsClient("127.0.0.1", 8125, prefix="test-list-changes")

CCs = ["GE", "IT", "US"]
THRESH = 30


def peek(cc, listmap) -> None:
    url = f"https://api.ooni.io/api/v1/test-list/urls?country_code={cc}&debug=True"
    res = urllib.request.urlopen(url)
    j = json.load(res)
    top = j["results"][:THRESH]  # list of dicts
    top_urls = set(d["url"] for d in top)

    if cc in listmap:
        changed = listmap[cc].symmetric_difference(top_urls)
        changed_ratio = len(changed) / len(top_urls) * 100
        metrics.gauge(f"-{cc}", changed_ratio)

    listmap[cc] = top_urls


def main() -> None:
    listmap = {}
    while True:
        for cc in CCs:
            try:
                peek(cc, listmap)
            except Exception as e:
                print(e)
            sleep(1)
        sleep(60 * 10)


if __name__ == "__main__":
    main()
