#!/usr/bin/env python3
# # -*- coding: utf-8 -*-
"""
OONI Event detector

Fetch historical msmt from the fastpath tables

Analise msmt score with moving average to detect blocking/unblocking
See the run_detection function for details

Save RSS feeds to local directories:
  - /var/lib/detector/rss/<fname>.xml    Events by CC, ASN, test_name and input

The tree under /var/lib/detector/ is served by Nginx with the exception of _internal

Events are defined as changes between blocking and non-blocking on single
CC / test_name / input tuples

Runs as a service "detector" in a systemd unit and sandbox

The --reprocess mode is only for debugging and it's destructive to
the blocking_* DB tables.
"""

# Compatible with Python3.9 - linted with Black
# debdeps: python3-setuptools

from argparse import ArgumentParser
from configparser import ConfigParser
from datetime import datetime, timedelta
from pathlib import Path
from site import getsitepackages
from urllib.parse import urlunsplit, urlencode
import logging
import os
import sys

from systemd.journal import JournalHandler  # debdeps: python3-systemd
import ujson  # debdeps: python3-ujson
import feedgenerator  # debdeps: python3-feedgenerator
import statsd  # debdeps: python3-statsd

from clickhouse_driver import Client as Clickhouse


log = logging.getLogger("detector")
metrics = statsd.StatsClient("localhost", 8125, prefix="detector")

PKGDIR = getsitepackages()[-1]
DBURI = "clickhouse://detector:detector@localhost/default"

conf = None
click = None
cc_to_country_name = None  # set by load_country_name_map


def query(*a, **kw):
    settings = {}
    if conf.reprocess:
        settings["log_query"] = 0
    else:
        log.info(a)
    return click.execute(*a, settings=settings, **kw)


def parse_date(d):
    return datetime.strptime(d, "%Y-%m-%d")


def setup_dirs(root):
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


def setup():
    os.environ["TZ"] = "UTC"
    global conf
    ap = ArgumentParser(__doc__)
    # FIXME args used for debugging
    ap.add_argument("--devel", action="store_true", help="Devel mode")
    ap.add_argument("-v", action="store_true", help="High verbosity")
    ap.add_argument("--reprocess", action="store_true", help="Reprocess events")
    ap.add_argument("--start-date", type=lambda d: parse_date(d))
    ap.add_argument("--end-date", type=lambda d: parse_date(d))
    ap.add_argument("--interval-mins", type=int, default=10)
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
    setup_dirs(root)
    if 0:  # TODO
        log.info("Using conf file %r", conf.conffile.as_posix())
        cp = ConfigParser()
        with open(conf.conffile) as f:
            cp.read_file(f)
            conf.db_uri = conf.db_uri or cp["DEFAULT"]["clickhouse_url"]


def explorer_mat_url(test_name, inp, probe_cc, probe_asn, t) -> str:
    since = str(t - timedelta(days=7))
    until = str(t + timedelta(days=7))
    p = dict(
        test_name=test_name,
        axis_x="measurement_start_day",
        since=since,
        until=until,
        probe_asn=f"AS{probe_asn}",
        probe_cc=probe_cc,
        input=inp,
    )
    return urlunsplit(("https", "explorer.ooni.org", "/chart/mat", urlencode(p), ""))


@metrics.timer("write_feed")
def write_feed(feed, p: Path) -> None:
    """Write out RSS feed atomically"""
    tmp_p = p.with_suffix(".tmp")
    tmp_p.write_text(feed)
    tmp_p.rename(p)


@metrics.timer("generate_rss_feed")
def generate_rss_feed(events):
    """Generate RSS feed into /var/lib/detector/rss/<fname>.xml"""
    # The files are served by Nginx
    feed = feedgenerator.Rss201rev2Feed(
        title="OONI events",
        link="https://explorer.ooni.org",
        description="Blocked services and websites detected by OONI",
        language="en",
    )
    for test_name, inp, probe_cc, probe_asn, status, time in events:
        # country = cc_to_country_name.get(c.probe_cc.upper(), c.probe_cc)
        status2 = "unblocked" if status == "OK" else "blocked"
        link = explorer_mat_url(test_name, inp, probe_cc, probe_asn, time)
        feed.add_item(
            title=f"{inp} {status2} in {probe_cc} AS{probe_asn}",
            link=link,
            description=f"Change detected on {time}",
            pubdate=time,
            updateddate=datetime.utcnow(),
        )

    return feed.writeString("utf-8")


@metrics.timer("rebuild_feeds")
def rebuild_feeds(changes):
    """Rebuild whole feeds"""
    # Changes are rare enough that running a query on blocking_events for each
    # changes is not too heavy
    sql = """SELECT test_name, input, probe_cc, probe_asn, status, time
        FROM blocking_events
        WHERE test_name = %(test_name)s AND input = %(inp)s
        AND probe_cc = %(cc)s AND probe_asn = %(asn)s
        ORDER BY time
    """
    for test_name, inp, probe_cc, probe_asn in changes:
        d = dict(test_name=test_name, inp=inp, cc=probe_cc, asn=probe_asn)
        events = query(sql, d)
        # FIXME: add test_name and input
        fname = f"{probe_cc}-AS{probe_asn}"
        log.info(f"Generating feed for {fname}")
        feed = generate_rss_feed(events, fname)
        write_feed(feed, conf.rssdir / f"{fname}.xml")


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


def create_tables() -> None:
    # Requires admin privileges
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
    `stability` Float32,
    `update_time` DateTime64(0) MATERIALIZED now64()
)
ENGINE = ReplacingMergeTree
ORDER BY (test_name, input, probe_cc, probe_asn)
SETTINGS index_granularity = 4
"""
    query(sql)
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
    query(sql)
    sql = "CREATE USER IF NOT EXISTS detector IDENTIFIED WITH plaintext_password BY 'detector'"
    query(sql)
    query("GRANT SELECT,INSERT,OPTIMIZE,SHOW ON blocking_status TO detector")
    query("GRANT SELECT,INSERT,OPTIMIZE,SHOW ON blocking_events TO detector")
    query("GRANT SELECT ON * TO detector")


@metrics.timer("rebuild_status")
def rebuild_status(click, start_date, end_date, services) -> None:
    log.info("Truncate blocking_status")
    sql = "TRUNCATE TABLE blocking_status"
    query(sql)

    log.info("Truncate blocking_events")
    sql = "TRUNCATE TABLE blocking_events"
    query(sql)

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
    query(sql, dict(start_date=start_date, end_date=end_date, urls=urls))
    log.info("Fill done")

#
# The blocking event detector is meant to run frequently in order to
# provide fast response to events - currently every 10 mins.
# As the amount of probes and measuraments increases, extracting all the
# required data for multiple inputs/CCs/ASNs and past weeks/months could
# become too CPU and memory-intensive for the database and the detector.
# Therefore we run the detection on the database side as much as possible.
# The current version uses moving averages stored in a status table
# `blocking_status`.
# Detection is performed on test_name+probe_cc+probe_asn+input aka "TCAI"
# following query. It's easier to read the query from the bottom up:
#  - Select data from the fastpath table for the last time window, counting
#    the percentages of confirmed, anomaly-but-not-confirmed etc. --> As "new"
#  - Select stored related moving averages etc. from blocking_status.
#    FINAL is required to avoid duplicates due to table updates.
#  - Join the two queries on TCAI
#  - Run SELECT to compute new values:
#    - The empty(blocking_status... parts are simply picking the right
#      value in case the entry is missing from blocking_status (TCAI never
#      seen before) or not in fastpath (no recent msmts for a given TCAI)
#    - Weighted percentages e.g.
#      (new_confirmed_perc * msmt count * μ + stored_perc * blocking_status.cnt * 𝜏) / totcnt
#      Where: 𝜏 < 1, μ = 1 - t  are used to combine old vs new values,
#       blocking_status.cnt is an averaged count of seen msmts representing how
#       "meaningful" the confirmed percentage in the blocking_status table is.
#    - Stability: compares the current and stored accessible/ confirmed/etc
#        percentage. 1 if there is no change, 0 for maximally fast change.
#        (Initialized as 0 for new TCAI)
#  - Then run another SELECT to:
#    - Set `status` based on accessible thresholds and stability
#      We don't want to trigger a spurius change if accessibility rates
#      floating a lot.
#    - Set `change` if the detected status is different from the past
#  - INSERT: Finally store the TCAI, the moving averages, msmt count, change,
#    stability in blocking_status to use it in the next cycle.
#
#  As the INSERT does not returns the rows, we select them in extract_changes
#  (with FINAL) to record them into `blocking_events`.
#  If there are changes we then extract the whole history for each changed
#  TCAI in rebuild_feeds.
#
@metrics.timer("run_detection")
def run_detection(start_date, end_date, services) -> None:
    if not conf.reprocess:
        log.info(f"Running detection from {start_date} to {end_date}")

    if 0 and conf.reprocess:
        # Used for debugging
        sql = """SELECT count() AS cnt FROM fastpath
    WHERE test_name IN ['web_connectivity']
    AND msm_failure = 'f'
    AND measurement_start_time >= %(start_date)s
    AND measurement_start_time < %(end_date)s
    AND probe_asn = 135300 and probe_cc = 'MM' AND input = 'https://twitter.com/'
        """
        d = dict(start_date=start_date, end_date=end_date)
        log_example = bool(query(sql, d)[0][0])

    # FIXME:   new.cnt * %(mu)f + blocking_status.cnt * %(tau)f AS totcnt
    sql = """
INSERT INTO blocking_status (test_name, input, probe_cc, probe_asn,
  confirmed_perc, pure_anomaly_perc, accessible_perc, cnt, status, old_status, change, stability)
SELECT test_name, input, probe_cc, probe_asn,
  confirmed_perc, pure_anomaly_perc, accessible_perc, totcnt AS cnt,
  multiIf(
    accessible_perc < 80 AND stability > 0.95, 'BLOCKED',
    accessible_perc > 95 AND stability > 0.97, 'OK',
    x.status)
  AS status,
  x.status AS old_status,
  if(status = x.status, x.change * %(tau)f, 1) AS change,
  stability
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
  blocking_status.accessible_perc * blocking_status.cnt * %(tau)f) / totcnt AS accessible_perc,

 ( cos(3.14/2*(new.accessible_perc - blocking_status.accessible_perc)/100) * 0.7 +
  blocking_status.stability * 0.3) AS stability

FROM blocking_status FINAL

FULL OUTER JOIN
(
 SELECT test_name, input, probe_cc, probe_asn,
  countIf(confirmed = 't') * 100 / cnt AS confirmed_perc,
  countIf(anomaly = 't') * 100 / cnt - confirmed_perc AS pure_anomaly_perc,
  countIf(anomaly = 'f') * 100 / cnt AS accessible_perc,
  count() AS cnt,
  0 AS stability
 FROM fastpath
 WHERE test_name IN ['web_connectivity']
 AND msm_failure = 'f'
 AND measurement_start_time >= %(start_date)s
 AND measurement_start_time < %(end_date)s
 AND input IN %(urls)s
 GROUP BY test_name, input, probe_cc, probe_asn
) AS new

ON
 new.input = blocking_status.input
 AND new.probe_cc = blocking_status.probe_cc
 AND new.probe_asn = blocking_status.probe_asn
 AND new.test_name = blocking_status.test_name
) AS x
"""
    tau = 0.985
    mu = 1 - tau
    urls = sorted(set(u for urls in services.values() for u in urls))
    d = dict(start_date=start_date, end_date=end_date, tau=tau, mu=mu, urls=urls)
    query(sql, d)

    if 0 and conf.reprocess and log_example:
        sql = """SELECT accessible_perc, cnt, status, stability FROM blocking_status FINAL
        WHERE probe_asn = 135300 and probe_cc = 'MM' AND input = 'https://twitter.com/'
        """
        it = list(query(sql)[0])
        it.append(str(start_date))
        print(repr(it) + ",")


@metrics.timer("extract_changes")
def extract_changes(run_date):
    sql = """
    INSERT INTO blocking_events (test_name, input, probe_cc, probe_asn, status,
    time)
    SELECT test_name, input, probe_cc, probe_asn, status, %(t)s AS time
    FROM blocking_status FINAL
    WHERE status != old_status
    AND old_status != ''
    """
    query(sql, dict(t=run_date))

    # TODO: simplify?
    # https://github.com/mymarilyn/clickhouse-driver/issues/221
    sql = """
    SELECT test_name, input, probe_cc, probe_asn
    FROM blocking_status FINAL
    WHERE status != old_status
    """
    if not conf.reprocess:
        sql += " AND old_status != ''"
    sql += " AND old_status != ''"
    changes = query(sql, dict(t=run_date))

    # Debugging
    sql = """SELECT test_name, input, probe_cc, probe_asn, old_status, status
    FROM blocking_status FINAL
    WHERE status != old_status
    AND old_status != ''
    AND probe_asn = 135300 and probe_cc = 'MM' AND input = 'https://twitter.com/'
    """
    if conf.reprocess:
        li = query(sql)
        for tn, inp, cc, asn, old_status, status in li:
            log.info(f"{run_date} {old_status} -> {status} in {cc} {asn} {inp}")

    return changes


@metrics.timer("process_historical_data")
def process_historical_data(start_date, end_date, interval, services):
    """Process past data"""
    log.info(f"Running process_historical_data from {start_date} to {end_date}")
    run_date = start_date + interval
    rebuild_status(click, start_date, run_date, services)
    while run_date < end_date:
        run_detection(run_date, run_date + interval, services)
        changes = extract_changes(run_date)
        if changes:
            rebuild_feeds(changes)
        run_date += interval

    log.debug("Done")


def gen_stats():
    """Generate gauge metrics showing the table sizes"""
    sql = "SELECT count() FROM blocking_status FINAL"
    bss = query(sql)[0][0]
    metrics.gauge("blocking_status_tblsize", bss)
    sql = "SELECT count() FROM blocking_events"
    bes = query(sql)[0][0]
    metrics.gauge("blocking_events_tblsize", bes)


def main():
    global click
    setup()
    log.info("Starting")
    # TODO: use country names
    # cc_to_country_name = load_country_name_map()
    click = Clickhouse.from_url(conf.db_uri)
    # create_tables()
    # FIXME: configure services
    services = {
        "Facebook": ["https://www.facebook.com/"],
        "Twitter": ["https://twitter.com/"],
    }
    if conf.reprocess:
        assert conf.start_date and conf.end_date, "Dates not set"
        process_historical_data(conf.start_date, conf.end_date, conf.interval, services)
        return

    end_date = datetime.utcnow()
    start_date = end_date - conf.interval
    run_detection(start_date, end_date, services)
    changes = extract_changes(end_date)
    if changes:
        rebuild_feeds(changes)
        # TODO: create an index of available RSS feeds
    gen_stats()
    log.info("Done")


if __name__ == "__main__":
    main()
