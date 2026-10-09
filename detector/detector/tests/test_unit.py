#
# Event detector unit tests
#

from datetime import datetime
from pathlib import Path
import re

import detector.detector as dt

data = Path("detector/tests/data")


def test_generate_rss_feed_empty():
    feed = dt.generate_rss_feed([])
    feed = re.sub(r"<lastBuildDate>.*</lastBuildDate>", "<X></X>", feed)
    exp = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
<channel>
<title>OONI events</title>
<link>https://explorer.ooni.org</link>
<description>Blocked services and websites detected by OONI</description>
<language>en</language>
<X></X>
</channel>
</rss>"""
    assert feed.replace("\n", "") == exp.replace("\n", "")


def test_generate_rss_feed_one():
    # test_name, inp, probe_cc, probe_asn, status, time
    e = [
        (
            "web_connectivity",
            "https://twitter.com/",
            "IE",
            "1234",
            "OK",
            datetime(2022, 1, 2),
        )
    ]
    feed = dt.generate_rss_feed(e)
    feed = re.sub(r"<lastBuildDate>.*</lastBuildDate>", "<X></X>", feed)
    exp = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
<channel>
<title>OONI events</title>
<link>https://explorer.ooni.org</link>
<description>Blocked services and websites detected by OONI</description>
<language>en</language>
<X></X>
<item>
<title>https://twitter.com/ unblocked in IE AS1234</title>
<link>https://explorer.ooni.org/chart/mat?test_name=web_connectivity&amp;axis_x=measurement_start_day&amp;since=2021-12-26+00%3A00%3A00&amp;until=2022-01-09+00%3A00%3A00&amp;probe_asn=AS1234&amp;probe_cc=IE&amp;input=https%3A%2F%2Ftwitter.com%2F</link>
<description>Change detected on 2022-01-02 00:00:00</description>
<pubDate>Sun, 02 Jan 2022 00:00:00 -0000</pubDate>
</item>
</channel>
</rss>"""
    assert feed.replace("\n", "") == exp.replace("\n", "")
