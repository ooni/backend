#!/usr/bin/env python3

"""
Monitor test-list/urls
"""

from urllib.request import urlopen
import json
import time
from argparse import ArgumentParser


def stats(cat, data):
    avg = sum(data) / len(data)
    s = f"{cat} count: {len(data)} min: {min(data)} max: {max(data)} avg: {avg}"
    print(s)


def main():

    ap = ArgumentParser()
    ap.add_argument("--prod", action="store_true")
    ap.add_argument("--interval", default=60 * 5, type=int)
    ap.add_argument("--cc", default="GB")
    ap.add_argument("--probestop", default=50, type=int)
    args = ap.parse_args()

    if args.prod:
        hn = "api.ooni.io"
    else:
        hn = "ams-pg-test.ooni.org"

    listurl = f"https://{hn}/api/v1/test-list/urls?country_code={args.cc}"

    cnt = {}
    while True:
        print(f"--- {hn} {args.cc} ---")
        with urlopen(listurl) as p:
            data = p.read().decode()
            try:
                data = json.loads(data)
            except json.decoder.JSONDecodeError:
                print("--error--")
                print(data)
                print("----")
                time.sleep(args.interval)
                continue

            li = data["results"][:args.probestop]  # simulate a probe
            for r in li:
                c = r["category_code"]
                url = r["url"]
                cnt.setdefault(c, {}).setdefault(url, 0)
                cnt[c][url] += 1

            for k in sorted(cnt):
                stats(k, cnt[k].values())

        time.sleep(args.interval)


main()
