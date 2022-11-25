#!/usr/bin/env python3
# # -*- coding: utf-8 -*-
"""
OONI Event detector

Run sequence:

Fetch historical msmt from the fastpath tables

Analise msmt score with moving average to detect blocking/unblocking

Save outputs to local directories:
    - RSS feed                                      /var/lib/detector/rss/
        rss/global.xml                All events, globally
        rss/by-country/<CC>.xml       Events by country
        rss/type-inp/<hash>.xml       Events by test_name and input
        rss/cc-type-inp/<hash>.xml    Events by CC, test_name and input
    - JSON files with block/unblock events          /var/lib/detector/events/
    - JSON files with current blocking status       /var/lib/detector/status/

The tree under /var/lib/detector/ is served by Nginx with the exception of _internal

Events are defined as changes between blocking and non-blocking on single
CC / test_name / input tuples

Runs as a service "detector" in a systemd unit and sandbox
"""

# Compatible with Python3.9 - linted with Black
# debdeps: python3-setuptools

from argparse import ArgumentParser
from collections import namedtuple, deque
from configparser import ConfigParser
from datetime import datetime, timedelta
from pathlib import Path
from site import getsitepackages
import logging
import os
import sys

from systemd.journal import JournalHandler  # debdeps: python3-systemd
import ujson  # debdeps: python3-ujson
import feedgenerator  # debdeps: python3-feedgenerator
import statsd

from clickhouse_driver import Client as Clickhouse


log = logging.getLogger("detector")
metrics = statsd.StatsClient("localhost", 8125, prefix="detector")

DEFAULT_STARTTIME = datetime(2016, 1, 1)

PKGDIR = getsitepackages()[-1]

conf = None
cc_to_country_name = None  # set by load_country_name_map


def parse_date(d):
    return datetime.strptime(d, "%Y-%m-%d")


def setup_dirs(conf, root):
    """Setup directories, creating them if needed"""
    conf.vardir = root / "var/lib/detector"
    conf.outdir = conf.vardir / "output"
    conf.rssdir = conf.outdir / "rss"
    conf.rssdir_by_cc = conf.rssdir / "by-country"
    conf.rssdir_by_tname_inp = conf.rssdir / "type-inp"
    conf.rssdir_by_cc_tname_inp = conf.rssdir / "cc-type-inp"
    conf.eventdir = conf.outdir / "events"
    conf.statusdir = conf.outdir / "status"
    for p in (
        conf.vardir,
        conf.outdir,
        conf.rssdir,
        conf.rssdir_by_cc,
        conf.rssdir_by_tname_inp,
        conf.rssdir_by_cc_tname_inp,
        conf.eventdir,
        conf.statusdir,
    ):
        p.mkdir(parents=True, exist_ok=True)


DBURI = "clickhouse://detector:detector@localhost/default"


def setup():
    os.environ["TZ"] = "UTC"
    global conf
    ap = ArgumentParser(__doc__)
    ap.add_argument("--devel", action="store_true", help="Devel mode")
    ap.add_argument("-v", action="store_true", help="Debug verbosity")
    # FIXME args used for debugging
    ap.add_argument("--repro", action="store_true", help="Reprocess events")
    ap.add_argument("--start-date", type=lambda d: parse_date(d))
    ap.add_argument("--end-date", type=lambda d: parse_date(d))
    ap.add_argument("--interval-mins", type=int, default=30)
    ap.add_argument("--db-uri", default=DBURI, help="Database hostname")
    conf = ap.parse_args()
    if conf.devel:
        format = "%(relativeCreated)d %(process)d %(levelname)s %(name)s %(message)s"
        lvl = logging.DEBUG if conf.v else logging.INFO
        logging.basicConfig(stream=sys.stdout, level=lvl, format=format)
    else:
        log.addHandler(JournalHandler(SYSLOG_IDENTIFIER="detector"))
        log.setLevel(logging.DEBUG)

    conf.interval = timedelta(minutes=conf.interval_mins)
    # Run inside current directory in devel mode
    root = Path(os.getcwd()) if conf.devel else Path("/")
    conf.conffile = root / "etc/ooni/detector.conf"
    if 0:  # FIXME
        log.info("Using conf file %r", conf.conffile.as_posix())
        cp = ConfigParser()
        with open(conf.conffile) as f:
            cp.read_file(f)
            conf.db_uri = conf.db_uri or cp["DEFAULT"]["clickhouse_url"]
        setup_dirs(conf, root)


Change = namedtuple(
    "Change",
    [
        "probe_cc",
        "test_name",
        "input",
        "blocked",
        "mean",
        "measurement_start_time",
        "tid",
        "report_id",
    ],
)


def explorer_url(c: Change) -> str:
    return f"https://explorer.ooni.org/measurement/{c.report_id}?input={c.input}"


# TODO: regenerate RSS feeds (only) once after the warmup terminates


@metrics.timer("write_feed")
def write_feed(feed, p: Path) -> None:
    """Write out RSS feed atomically"""
    tmp_p = p.with_suffix(".tmp")
    with tmp_p.open("w") as f:
        feed.write(f, "utf-8")

    tmp_p.rename(p)


global_feed_cache = deque(maxlen=1000)


@metrics.timer("update_rss_feed_global")
def update_rss_feed_global(change: Change) -> None:
    """Generate RSS feed for global events and write it in
    /var/lib/detector/rss/global.xml
    """
    # The files are served by Nginx
    global global_feed_cache
    if not change.input:
        return
    global_feed_cache.append(change)
    feed = feedgenerator.Rss201rev2Feed(
        title="OONI events",
        link="https://explorer.ooni.org",
        description="Blocked services and websites detected by OONI",
        language="en",
    )
    for c in global_feed_cache:
        un = "" if c.blocked else "un"
        country = cc_to_country_name.get(c.probe_cc.upper(), c.probe_cc)
        feed.add_item(
            title=f"{c.input} {un}blocked in {country}",
            link=explorer_url(c),
            description=f"Change detected on {c.measurement_start_time}",
            pubdate=c.measurement_start_time,
            updateddate=datetime.utcnow(),
        )
    write_feed(feed, conf.rssdir / "global.xml")


by_cc_feed_cache = {}


@metrics.timer("update_rss_feed_by_country")
def update_rss_feed_by_country(change: Change) -> None:
    """Generate RSS feed for events grouped by country and write it in
    /var/lib/detector/rss/by-country/<CC>.xml
    """
    # The files are served by Nginx
    global by_cc_feed_cache
    if not change.input:
        return
    cc = change.probe_cc
    if cc not in by_cc_feed_cache:
        by_cc_feed_cache[cc] = deque(maxlen=1000)
    by_cc_feed_cache[cc].append(change)
    feed = feedgenerator.Rss201rev2Feed(
        title=f"OONI events in {cc}",
        link="https://explorer.ooni.org",
        description="Blocked services and websites detected by OONI",
        language="en",
    )
    for c in by_cc_feed_cache[cc]:
        un = "" if c.blocked else "un"
        country = cc_to_country_name.get(c.probe_cc.upper(), c.probe_cc)
        feed.add_item(
            title=f"{c.input} {un}blocked in {country}",
            link=explorer_url(c),
            description=f"Change detected on {c.measurement_start_time}",
            pubdate=c.measurement_start_time,
            updateddate=datetime.utcnow(),
        )
    write_feed(feed, conf.rssdir_by_cc / f"{cc}.xml")


@metrics.timer("update_rss_feeds_by_cc_tname_inp")
def update_rss_feeds_by_cc_tname_inp(events, hashfname):
    """Generate RSS feed by cc / test_name / input and write
    /var/lib/detector/rss/cc-type-inp/<hash>.xml
    """
    # The files are served by Nginx
    feed = feedgenerator.Rss201rev2Feed(
        title="OONI events",
        link="https://explorer.ooni.org",
        description="Blocked services and websites detected by OONI",
        language="en",
    )
    # TODO: render date properly and add blocked/unblocked
    # TODO: put only recent events in the feed (based on the latest event time)
    for e in events:
        if not e["input"]:
            continue

        country = cc_to_country_name.get(c.probe_cc.upper(), c.probe_cc)
        feed.add_item(
            title=f"{c.input} {un}blocked in {country}",
            link=explorer_url(c),
            description=f"Change detected on {c.measurement_start_time}",
            pubdate=c.measurement_start_time,
            updateddate=datetime.utcnow(),
        )

    write_feed(feed, conf.rssdir / f"{hashfname}.xml")


@metrics.timer("upsert_change")
def upsert_change(change):
    """Create / update RSS and JSON files with a new change"""
    # Create DB tables in future if needed
    if not change.report_id:
        log.error("Empty report_id")
        return

    try:
        update_rss_feed_global(change)
        update_rss_feed_by_country(change)
    except Exception as e:
        log.error(e, exc_info=1)

    # TODO: currently unused
    return

    # Append change to a list in a JSON file
    # It contains all the block/unblock events for a given cc/test_name/input
    hashfname = basefn(change.probe_cc, change.test_name, change.input)
    events_f = conf.eventdir / f"{hashfname}.json"
    if events_f.is_file():
        with events_f.open() as f:
            ecache = ujson.load(f)
    else:
        ecache = dict(format=1, blocking_events=[])

    ecache["blocking_events"].append(change._asdict())
    log.info("Saving %s", events_f)
    with events_f.open("w") as f:
        ujson.dump(ecache, f)

    update_rss_feeds_by_cc_tname_inp(ecache["blocking_events"], hashfname)


def load_country_name_map():
    """Load country-list.json and create a lookup dictionary"""
    fi = f"{PKGDIR}/detector/data/country-list.json"
    log.info("Loading %s", fi)
    with open(fi) as f:
        clist = ujson.load(f)

    # The file is deployed with the detector: crash out if it's broken
    d = {}
    for c in clist:
        cc = c["iso3166_alpha2"]
        name = c["name"]
        assert cc and (len(cc) == 2) and name
        d[cc.upper()] = name

    log.info("Loaded %d country names", len(d))
    return d


def create_table(click):
    sql = """
CREATE TABLE IF NOT EXISTS blocking_status
(
    `test_name` String,
    `input` String,
    `probe_cc` String,
    `probe_asn` Int32,
    `confirmed_perc` Float32,
    `pure_anomaly_perc` Float32,
    `accessible_perc` Float32,
    `cnt` Float32,
    `status` String,
    `old_status` String,
    `change` Float32,
    `update_time` DateTime64(0) MATERIALIZED now64()
)
ENGINE = ReplacingMergeTree
ORDER BY (test_name, input, probe_cc, probe_asn)
SETTINGS index_granularity = 4
"""
    click.execute(sql)
    sql = """
CREATE TABLE IF NOT EXISTS blocking_events
(
    `test_name` String,
    `input` String,
    `probe_cc` String,
    `probe_asn` Int32,
    `status` String,
    `time` DateTime64(3),
    `detection_time` DateTime64(0) MATERIALIZED now64()
)
ENGINE = ReplacingMergeTree
ORDER BY (test_name, input, probe_cc, probe_asn, time)
SETTINGS index_granularity = 4
"""
    click.execute(sql)


@metrics.timer("rebuild_status")
def rebuild_status(click, start_date, end_date, services):
    log.info("Truncate blocking_status")
    sql = "TRUNCATE TABLE blocking_status"
    click.execute(sql)

    log.info("Truncate blocking_events")
    sql = "TRUNCATE TABLE blocking_events"
    click.execute(sql)

    log.info("Fill status")
    sql = """
INSERT INTO blocking_status (test_name, input, probe_cc, probe_asn,
  confirmed_perc, pure_anomaly_perc, accessible_perc, cnt, status)
  SELECT
    test_name,
    input,
    probe_cc,
    probe_asn,
    (countIf(confirmed = 't') * 100) / cnt AS confirmed_perc,
    ((countIf(anomaly = 't') * 100) / cnt) - confirmed_perc AS pure_anomaly_perc,
    (countIf(anomaly = 'f') * 100) / cnt AS accessible_perc,
    count() AS cnt,
    multiIf(
        accessible_perc < 70, 'BLOCKED',
        accessible_perc > 90, 'OK',
        'UNKNOWN')
    AS status
FROM fastpath
WHERE test_name IN ['web_connectivity']
AND msm_failure = 'f'
AND input IN %(urls)s
AND measurement_start_time >= %(start_date)s
AND measurement_start_time < %(end_date)s
GROUP BY test_name, input, probe_cc, probe_asn;
"""
    urls = sorted(set(u for urls in services.values() for u in urls))
    click.execute(sql, dict(start_date=start_date, end_date=end_date, urls=urls))
    log.info("Fill done")


@metrics.timer("run_detection")
def run_detection(click, start_date, end_date, services):
    # log.info(f"Running detection from {start_date} to {end_date}")
    sql = """
INSERT INTO blocking_status (test_name, input, probe_cc, probe_asn,
  confirmed_perc, pure_anomaly_perc, accessible_perc, cnt, status, old_status, change)
SELECT test_name, input, probe_cc, probe_asn,
  confirmed_perc, pure_anomaly_perc, accessible_perc, totcnt AS cnt,
  multiIf(
    accessible_perc < 80, 'BLOCKED',
    accessible_perc > 95, 'OK',
    x.status)
  AS status,
  x.status AS old_status,
  if(status = x.status, x.change * %(tau)f, 1) AS change
FROM
(
SELECT
 empty(blocking_status.test_name) ? new.test_name : blocking_status.test_name AS test_name,
 empty(blocking_status.input) ? new.input : blocking_status.input AS input,
 empty(blocking_status.probe_cc) ? new.probe_cc : blocking_status.probe_cc AS probe_cc,
 (blocking_status.probe_asn = 0) ? new.probe_asn : blocking_status.probe_asn AS probe_asn,
 new.cnt * %(mu)f + blocking_status.cnt * %(tau)f AS totcnt,
 blocking_status.status,
 blocking_status.change,
 (new.confirmed_perc * new.cnt * %(mu)f +
  blocking_status.confirmed_perc * blocking_status.cnt * %(tau)f) / totcnt AS confirmed_perc,
 (new.pure_anomaly_perc * new.cnt * %(mu)f +
  blocking_status.pure_anomaly_perc * blocking_status.cnt * %(tau)f) / totcnt AS pure_anomaly_perc,
 (new.accessible_perc * new.cnt * %(mu)f +
  blocking_status.accessible_perc * blocking_status.cnt * %(tau)f) / totcnt AS accessible_perc
FROM
(
 SELECT test_name, input, probe_cc, probe_asn,
  countIf(confirmed = 't') * 100 / cnt AS confirmed_perc,
  countIf(anomaly = 't') * 100 / cnt - confirmed_perc AS pure_anomaly_perc,
  countIf(anomaly = 'f') * 100 / cnt AS accessible_perc,
  count() AS cnt
 FROM fastpath
 WHERE test_name IN ['web_connectivity']
 AND msm_failure = 'f'
 AND measurement_start_time >= %(start_date)s
 AND measurement_start_time < %(end_date)s
 AND input IN %(urls)s
 GROUP BY test_name, input, probe_cc, probe_asn
) AS new

FULL OUTER JOIN
    (SELECT * FROM blocking_status FINAL) AS blocking_status
ON
 new.input = blocking_status.input
 AND new.probe_cc = blocking_status.probe_cc
 AND new.probe_asn = blocking_status.probe_asn
) AS x
"""
    tau = 0.985
    mu = 1 - tau
    urls = sorted(set(u for urls in services.values() for u in urls))
    d = dict(start_date=start_date, end_date=end_date, tau=tau, mu=mu, urls=urls)
    click.execute(sql, d)


@metrics.timer("extract_changes")
def extract_changes(click, run_date):
    sql = """
    INSERT INTO blocking_events (test_name, input, probe_cc, probe_asn, status,
    time)
    SELECT test_name, input, probe_cc, probe_asn, status, %(t)s AS time
    FROM blocking_status FINAL
    WHERE status != old_status
    AND old_status != ''
    """
    li = click.execute(sql, dict(t=run_date))

    sql = """SELECT test_name, input, probe_cc, probe_asn, old_status, status
    FROM blocking_status FINAL
    WHERE status != old_status
    AND old_status != ''
    AND probe_asn = 135300 and probe_cc = 'MM' AND input = 'https://twitter.com/'
    """
    # DEBUG
    li = click.execute(sql)
    for tn, inp, cc, asn, old_status, status in li:
        log.info(f"{run_date} {old_status} -> {status} in {cc} {asn} {inp}")


@metrics.timer("process_historical_data")
def process_historical_data(click, start_date, end_date, interval, services):
    """Process past data"""
    log.info(f"Running process_historical_data from {start_date} to {end_date}")
    create_table(click)
    run_date = start_date + interval
    rebuild_status(click, start_date, run_date, services)
    while run_date < end_date:
        # bscnt = click.execute("SELECT count() FROM blocking_status FINAL")[0][0]
        # log.info(bscnt)
        run_detection(click, run_date, run_date + interval, services)
        extract_changes(click, run_date)
        run_date += interval

    log.debug("Done")


def main():
    setup()
    log.info("Starting")
    # global cc_to_country_name
    # cc_to_country_name = load_country_name_map()
    click = Clickhouse.from_url(conf.db_uri)
    # start_date = datetime(2022, 2, 20)
    # end_date = start_date + timedelta(days=20)
    # end_date = start_date + timedelta(minutes=120)
    # interval = timedelta(minutes=30 * 4)
    # FIXME: configure services
    services = {
        "Facebook": ["https://www.facebook.com/"],
        "Twitter": ["https://twitter.com/"],
    }
    if conf.repro:
        assert conf.start_date and conf.end_date, "Dates not set"
        process_historical_data(
            click, conf.start_date, conf.end_date, conf.interval, services
        )
    # FIXME: implement timed run
    # FIXME: implement feed generators


if __name__ == "__main__":
    main()
