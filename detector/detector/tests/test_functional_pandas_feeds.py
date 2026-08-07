"""
Event detector functional tests: feed generation

Run as:
pytest tests/test_functional_pandas.py -s

"""
from argparse import Namespace
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest
from clickhouse_driver import Client as Clickhouse

import detector.detector as dt


@pytest.fixture(scope="session", autouse=True)
def setup():
    dt.conf = Namespace()
    dt.conf.reprocess = False
    dt.conf.devel = True
    DBURI = "clickhouse://localhost/default"
    dt.click = Clickhouse.from_url(DBURI)
    dt.conf.rssdir = Path("tests/out_rss")
    dt.setup_dirs(Path("devel"))


def test_generate_rss_feeds2(setup):
    be = pd.read_csv("tests/data/be.csv")  # blocking events
    be.drop(["Unnamed: 0"], axis=1, inplace=True)
    be.time = pd.to_datetime(be.time)
    be2 = be[
        (be.probe_cc == "US")
        & (be.test_name == "web_connectivity")
        & (be.probe_asn == 11427)
        & (be.input == "https://twitter.com/")
    ]
    assert len(be2) == 2
    assert sorted(be2.columns) == [
        "input",
        "probe_asn",
        "probe_cc",
        "status",
        "test_name",
        "time",
    ]
    s, p = dt.generate_rss_feed(be2, datetime(2023, 5, 22))
    assert p == Path("devel/var/lib/detector/output/rss/web_connectivity-US-AS11427-https_twitter.com_.xml")
    s = s.replace("\n", "")
    exp = """
<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
 <channel>
  <title>OONI events</title>
  <link>https://explorer.ooni.org</link>
  <description>Blocked services and websites detected by OONI</description>
  <language>en</language>
  <lastBuildDate>Mon, 22 May 2023 00:00:00 -0000</lastBuildDate>
  <item>
   <title>https://twitter.com/ unblocked in US AS11427</title>
   <link>https://explorer.ooni.org/chart/mat?test_name=web_connectivity&amp;axis_x=measurement_start_day&amp;since=2022-12-03+14%3A20%3A00&amp;until=2022-12-17+14%3A20%3A00&amp;probe_asn=AS11427&amp;probe_cc=US&amp;input=https%3A%2F%2Ftwitter.com%2F</link>
   <description>Change detected on 2022-12-10 14:20:00</description>
   <pubDate>Sat, 10 Dec 2022 14:20:00 -0000</pubDate>
  </item>
  <item>
   <title>https://twitter.com/ blocked in US AS11427</title>
   <link>https://explorer.ooni.org/chart/mat?test_name=web_connectivity&amp;axis_x=measurement_start_day&amp;since=2022-12-12+16%3A50%3A00&amp;until=2022-12-26+16%3A50%3A00&amp;probe_asn=AS11427&amp;probe_cc=US&amp;input=https%3A%2F%2Ftwitter.com%2F</link>
   <description>Change detected on 2022-12-19 16:50:00</description>
   <pubDate>Mon, 19 Dec 2022 16:50:00 -0000</pubDate>
  </item>
 </channel>
</rss>
"""
    exp = "".join(line.strip() for line in exp.splitlines())
    assert s == exp


def test_rebuild_feeds(setup):
    d = {
        "test_name": "web_connectivity",
        "input": "https://twitter.com/",
        "probe_cc": "IT",
        "probe_asn": "123",
        "status": "BLOCKED",
        "time": "",
    }
    d = {k: [v] for k, v in d.items()}
    events = pd.DataFrame.from_dict(d)
    dt.conf.reprocess = False
    cnt = dt.rebuild_feeds(events)
    assert cnt == 0


