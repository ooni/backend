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

# from configparser import ConfigParser
from datetime import datetime, timedelta
from pathlib import Path
from site import getsitepackages
from typing import Generator, Tuple, Optional, Any, Dict
from urllib.parse import urlunsplit, urlencode
import logging
import os
import sys

from systemd.journal import JournalHandler  # debdeps: python3-systemd
import ujson  # debdeps: python3-ujson
import feedgenerator  # debdeps: python3-feedgenerator
import statsd  # debdeps: python3-statsd

import pandas as pd  # debdeps: python3-pandas
import numpy as np  # debdeps: python3-numpy

from clickhouse_driver import Client as Clickhouse

try:
    from tqdm import tqdm
except ImportError:

    def tqdm(x, *a, **kw):  # type: ignore
        return x


log = logging.getLogger("detector")
metrics = statsd.StatsClient("localhost", 8125, prefix="detector")

DBURI = "clickhouse://detector:detector@localhost/default?use_numpy=True"
TCAI = ["test_name", "probe_cc", "probe_asn", "input"]
tTCAI = ["t", "test_name", "probe_cc", "probe_asn", "input"]

conf: Any = None
click: Clickhouse = None
cc_to_country_name: Dict[str, str] = {}  # CC-> name, see load_country_name_map


def query(*a, **kw):
    settings = {}
    if conf.reprocess:
        settings["log_query"] = 0
    else:
        log.info(a)
    return click.execute(*a, settings=settings, **kw)


def parse_date(d: str) -> datetime:
    return datetime.strptime(d, "%Y-%m-%d %H:%M")


def setup_dirs(root: Path) -> None:
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
    # TODO cleanup args used for debugging
    ap.add_argument("--devel", action="store_true", help="Devel mode")
    ap.add_argument("-v", action="store_true", help="High verbosity")
    ap.add_argument("--reprocess", action="store_true", help="Reprocess events")
    ap.add_argument("--start-date", type=lambda d: parse_date(d))
    ap.add_argument("--end-date", type=lambda d: parse_date(d))
    ap.add_argument("--interval-mins", type=int, default=60)
    ap.add_argument("--db-uri", default=DBURI, help="Database hostname")
    conf = ap.parse_args()
    if conf.devel:
        format = "%(relativeCreated)d %(process)d %(levelname)s %(name)s %(message)s"
        lvl = logging.DEBUG if conf.v else logging.DEBUG
        logging.basicConfig(stream=sys.stdout, level=lvl, format=format)
    else:
        log.addHandler(JournalHandler(SYSLOG_IDENTIFIER="detector"))
        log.setLevel(logging.DEBUG)

    conf.interval = timedelta(minutes=conf.interval_mins)
    # Run inside current directory in devel mode
    root = Path(os.getcwd()) if conf.devel else Path("/")
    setup_dirs(root)
    # conf.conffile = root / "etc/ooni/detector.conf"
    # log.info("Using conf file %r", conf.conffile.as_posix())
    # cp = ConfigParser()
    # with open(conf.conffile) as f:
    #     cp.read_file(f)
    #     conf.db_uri = conf.db_uri or cp["DEFAULT"]["clickhouse_url"]


# # RSS feed generation


def explorer_mat_url(
    test_name: str, inp: str, probe_cc: str, probe_asn: int, t: datetime
) -> str:
    """Generates a link to the MAT to display an event"""
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
def generate_rss_feed(events: pd.DataFrame, update_time: datetime) -> Tuple[str, Path]:
    """
    Generate RSS feed for a single TCAI into /var/lib/detector/rss/<fname>.xml
    The files are then served by Nginx
    """
    x = events.iloc[0]
    minp = x.input.replace("://", "_").replace("/", "_")
    fname = f"{x.test_name}-{x.probe_cc}-AS{x.probe_asn}-{minp}"
    log.info(f"Generating feed for {fname}. {len(events)} events.")

    feed = feedgenerator.Rss201rev2Feed(
        title="OONI events",
        link="https://explorer.ooni.org",
        description="Blocked services and websites detected by OONI",
        language="en",
    )
    for e in events.itertuples():
        cc = e.probe_cc.upper()
        # TODO use country
        country = cc_to_country_name.get(cc, cc)
        status2 = "unblocked" if e.status == "OK" else "blocked"
        link = explorer_mat_url(e.test_name, e.input, e.probe_cc, e.probe_asn, e.time)
        feed.add_item(
            title=f"{e.input} {status2} in {e.probe_cc} AS{e.probe_asn}",
            link=link,
            description=f"Change detected on {e.time}",
            pubdate=e.time,
            updateddate=update_time,
        )

    path = conf.rssdir / f"{fname}.xml"
    return feed.writeString("utf-8"), path


@metrics.timer("rebuild_feeds")
def rebuild_feeds(events: pd.DataFrame) -> int:
    """Rebuild whole feeds for each TCAI"""
    # When generated in real time "events" only contains the recent events for
    # each TCAI. We need the full history.
    # Changes are rare enough that running a query on blocking_events for each
    # change is not too heavy
    cnt = 0
    sql = """SELECT test_name, probe_cc, probe_asn, input, time, status
    FROM blocking_events
    WHERE test_name = %(test_name)s AND input = %(inp)s
    AND probe_cc = %(cc)s AND probe_asn = %(asn)s
    ORDER BY time
    """
    events = events.reset_index()
    unique_tcais = events[TCAI].drop_duplicates()
    update_time = datetime.utcnow()
    for x in unique_tcais.itertuples():
        d = dict(test_name=x.test_name, inp=x.input, cc=x.probe_cc, asn=x.probe_asn)
        history = click.query_dataframe(sql, d)
        if len(history):
            feed_data, path = generate_rss_feed(history, update_time)
            write_feed(feed_data, path)
            cnt += len(history)

    log.info(f"[re]created {cnt} feeds")
    return cnt


# # Initialization


def load_country_name_map(devel: bool) -> dict:
    """Loads country-list.json and creates a lookup dictionary"""
    try:
        fi = "detector/data/country-list.json"
        log.info("Loading %s", fi)
        with open(fi) as f:
            clist = ujson.load(f)
    except FileNotFoundError:
        pkgdir = getsitepackages()[-1]
        fi = f"{pkgdir}/detector/data/country-list.json"
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


def create_empty_status_df() -> pd.DataFrame:
    status = pd.DataFrame(
        columns=[
            "status",
            "old_status",
            "change",
            "stability",
            "test_name",
            "probe_cc",
            "probe_asn",
            "input",
            "accessible_perc",
            "cnt",
            "confirmed_perc",
            "pure_anomaly_perc",
        ]
    )
    status.set_index(TCAI, inplace=True)
    return status


def reprocess_inner(
    gen, time_slots_cnt: int, collect_hist=False
) -> Tuple[pd.DataFrame, pd.DataFrame, Optional[pd.DataFrame]]:
    #    df = pd.DataFrame({'Courses': pd.Series(dtype='str'),
    #                   'Fee': pd.Series(dtype='int'),
    #                   'Duration': pd.Series(dtype='str'),
    #                   'Discount': pd.Series(dtype='float')})
    status = create_empty_status_df()
    events_tmp = []
    status_history_tmp = []

    log.info(f"Processing {time_slots_cnt} time slots")
    for new in tqdm(gen, total=time_slots_cnt):
        assert "Unnamed: 0" not in sorted(new.columns), sorted(new.columns)
        # assert new.index.names == TCAI, new.index.names
        status, events = process_data(status, new)
        if events is not None and len(events):
            events_tmp.append(events)
            if collect_hist:
                status_history_tmp.append(status)

    if events_tmp:
        events = pd.concat(events_tmp)
    else:
        events = None
        status_history = pd.concat(status_history_tmp) if collect_hist else None
        return events, status, status_history


@metrics.timer("process_historical_data")
def process_historical_data(
    start_date: datetime,
    end_date: datetime,
    interval: timedelta,
    services: dict,
    probe_cc=None,
    collect_hist=False,
) -> Tuple[pd.DataFrame, pd.DataFrame, Optional[pd.DataFrame]]:
    """Processes past data. Rebuilds blocking_status table and events
    Keeps blocking_status and blocking_events in memory during the run.
    """
    log.info(f"Running process_historical_data from {start_date} to {end_date}")
    urls = sorted(set(u for urls in services.values() for u in urls))
    time_slots_cnt = int((end_date - interval - start_date) / interval)

    gen = gen_input(click, start_date, end_date, interval, urls)
    events, status, status_history = reprocess_inner(gen, time_slots_cnt)

    log.debug("Replacing blocking_status table")
    click.execute("TRUNCATE TABLE blocking_status SYNC")

    tmp_s = status.reset_index()  # .convert_dtypes()
    click.insert_dataframe("INSERT INTO blocking_status VALUES", tmp_s)

    log.debug("Replacing blocking_events table")
    click.execute("TRUNCATE TABLE blocking_events SYNC")
    if events is not None and len(events):
        sql = "INSERT INTO blocking_events VALUES"
        click.insert_dataframe(sql, events.reset_index(drop=True))

    log.info("Done")
    return events, status, status_history


@metrics.timer("process_fresh_data")
def process_fresh_data(
    start_date: datetime,
    end_date: datetime,
    interval: timedelta,
    services: dict,
    probe_cc=None,
    collect_hist=False,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Processes current data."""
    log.info(f"Running process_fresh_data from {start_date} to {end_date}")
    urls = sorted(set(u for urls in services.values() for u in urls))

    status = load_blocking_status()
    metrics.gauge("blocking_status_tblsize", len(status))

    gen = gen_input(click, start_date, end_date, interval, urls)
    new = None
    for x in gen:
        new = x
        pass

    if new is None or len(new) == 0:
        log.error("Empty measurament batch received")
        sys.exit(1)

    log.info(f"New rows: {len(new)} Status rows: {len(status)}")
    status, events = process_data(status, new)

    assert len(status)

    log.debug("Updating blocking_status table")

    wanted_cols = [
        "test_name",
        "input",
        "probe_cc",
        "probe_asn",
        "confirmed_perc",
        "pure_anomaly_perc",
        "accessible_perc",
        "cnt",
        "status",
        "old_status",
        "change",
        "stability",
    ]
    status.status.fillna("UNKNOWN", inplace=True)
    status.old_status.fillna("UNKNOWN", inplace=True)
    status.change.fillna(0, inplace=True)
    tmp_s = status.reset_index()[wanted_cols].convert_dtypes()
    click.execute("TRUNCATE TABLE blocking_status SYNC")
    click.insert_dataframe("INSERT INTO blocking_status VALUES", tmp_s)

    if events is not None and len(events):
        log.debug(f"Appending {len(events)} events to blocking_events table")
        ev = events.reset_index()
        ev = ev.drop(columns=["old_status"])
        ev["time"] = end_date  # event detection time
        log.info(ev)
        assert ev.columns.values.tolist() == [
            "test_name",
            "probe_cc",
            "probe_asn",
            "input",
            "status",
            "time",
        ]
        sql = "INSERT INTO blocking_events (test_name, probe_cc, probe_asn, input, status, time) VALUES"
        click.insert_dataframe(sql, ev)

    log.info("Done")
    return events, status


def gen_stats():
    """Generates gauge metrics showing the table sizes"""
    sql = "SELECT count() FROM blocking_status FINAL"
    bss = query(sql)[0][0]
    metrics.gauge("blocking_status_tblsize", bss)
    sql = "SELECT count() FROM blocking_events"
    bes = query(sql)[0][0]
    metrics.gauge("blocking_events_tblsize", bes)


def process_data(
    blocking_status: pd.DataFrame, new: pd.DataFrame
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Detects blocking. The inputs are the current blocking status and a df
    with new data from a single timeslice.
    Returns an updated blocking status and a df with new blocking events.
    """
    if len(blocking_status) == 0 and len(new) == 0:
        return blocking_status, []

    m = blocking_status.merge(new, how="outer", on=TCAI, suffixes=("_BS", ""))
    assert "index" not in m.columns
    m = m.reset_index().set_index(TCAI)  # performance improvement?
    assert m.index.names == TCAI

    m["input_cnt"] = m.cnt
    m = m.fillna(value=dict(cnt=0, cnt_BS=0, accessible_perc_BS=m.accessible_perc))
    tau = 0.9

    mavg_cnt = m.cnt * (1 - tau) + m.cnt_BS * tau
    # totcnt = m.cnt + m.cnt_BS
    # cp = (new.confirmed_perc * new.cnt * mu + blocking_status.confirmed_perc * blocking_status.cnt * tau / totcnt #AS confirmed_perc,
    # ap = (new.pure_anomaly_perc * new.cnt * mu + blocking_status.pure_anomaly_perc * blocking_status.cnt * tau) / totcnt #AS pure_anomaly_perc,
    # NOTE: using fillna(0) on percentages looks like a bug but the value is going to be ignored due to the cnt set to 0

    m["input_ap"] = m.accessible_perc
    tmp_ap = m.accessible_perc.fillna(m.accessible_perc_BS)
    delta = (tmp_ap - m.accessible_perc_BS) / 100

    # Weight the amount of datapoints in the current timeslot with
    nu = m.cnt / (m.cnt + m.cnt_BS)
    nu = nu * tau

    m.accessible_perc = (
        m.accessible_perc.fillna(m.accessible_perc_BS) * (1 - nu)
        + m.accessible_perc_BS * nu
    )

    # Stability moves slowly towards 1 when accessible_perc is constant over
    # time but drop quickly towards 0 when accessible_perc changes a lot.
    # It is later on used to decide when we are confident enough to make
    # statements on BLOCKED/OK status. It is also immediately set to 0 when we
    # detect a blocking change event to mitigate flapping.
    s_def = 0.7  # default stability
    stability_thr = 0.8  # threshold to consider a TCAI stable
    gtau = 0.99  # moving average tau for
    btau = 0.7

    stability = np.cos(3.14 / 2 * delta)
    m["stab_insta"] = stability  # used for charting
    good = stability * (1 - gtau) + m.stability.fillna(s_def) * gtau
    gstable = stability >= stability_thr
    m.loc[gstable, "stability"] = good[gstable]

    bad = stability * (1 - btau) + m.stability.fillna(s_def) * btau
    bstable = stability < stability_thr
    m.loc[bstable, "stability"] = bad[bstable]

    m.status = m.status.fillna("UNKNOWN")
    m.old_status = m.status.fillna("UNKNOWN")

    # Use different stability thresholds for OK vs BLOCKED?
    stable = (m.stability > 0.98) & (stability > 0.98)
    m.loc[(m.accessible_perc < 80) & stable, "status"] = "BLOCKED"
    m.loc[(m.accessible_perc > 95) & stable, "status"] = "OK"

    # Detect status changes AKA events
    # Always use braces on both expressions
    sel = (m.status != m.old_status) & (m.old_status != "UNKNOWN")
    ww = m[sel]
    if len(ww):
        ww = ww[["status", "old_status"]]
        # Drop stability to 0 after an event to prevent noisy detection
        m.loc[sel, "stability"] = 0

    events = m[sel][["status", "old_status"]]
    if conf.devel:
        exp_cols = [
            "old_status",
            "status",
        ]
        assert sorted(events.columns) == exp_cols, sorted(events.columns)

    m.confirmed_perc.fillna(m.confirmed_perc_BS, inplace=True)
    m.pure_anomaly_perc.fillna(m.pure_anomaly_perc_BS, inplace=True)
    # m.accessible_perc.fillna(m.accessible_perc_BS, inplace=True)
    m = m.drop(
        [
            "confirmed_perc_BS",
            "pure_anomaly_perc_BS",
            "accessible_perc_BS",
            "cnt",
            "cnt_BS",
        ],
        axis=1,
    )

    # moving average on cnt
    m["cnt"] = mavg_cnt
    assert m.index.names == TCAI

    # m.reset_index(inplace=True)
    # if "index" in m.columns:
    #    m.drop(["index"], axis=1, inplace=True)

    # if conf.devel:
    #    exp_cols = [
    #        "accessible_perc",
    #        "change",
    #        "cnt",
    #        "confirmed_perc",
    #        "input",
    #        "input_ap",
    #        "input_cnt",
    #        "old_status",
    #        "probe_asn",
    #        "probe_cc",
    #        "pure_anomaly_perc",
    #        "stab_insta",
    #        "stability",
    #        "status",
    #        "test_name",
    #    ]
    #    assert exp_cols == sorted(m.columns), sorted(m.columns)

    return m, events


def gen_input(
    click,
    start_date: datetime,
    end_date: datetime,
    interval: timedelta,
    urls: list[str],
) -> Generator[pd.DataFrame, None, None]:
    """Queries the fastpath table for measurament counts grouped by TCAI.
    Yields a dataframe for each time interval. Use read-ahead where needed
    to speed up reprocessing.
    """
    assert start_date < end_date
    assert interval == timedelta(minutes=60)
    read_ahead = interval * 6 * 24
    sql = """
    SELECT test_name, probe_cc, probe_asn, input,
      countIf(confirmed = 't') * 100 / cnt AS confirmed_perc,
      countIf(anomaly = 't') * 100 / cnt - confirmed_perc AS pure_anomaly_perc,
      countIf(anomaly = 'f') * 100 / cnt AS accessible_perc,
      count() AS cnt,
      toStartOfHour(measurement_start_time) AS t
    FROM fastpath
    WHERE test_name IN ['web_connectivity']
    AND msm_failure = 'f'
    AND measurement_start_time >= %(start_date)s
    AND measurement_start_time < %(end_date)s
    AND input IN %(urls)s
    GROUP BY test_name, probe_cc, probe_asn, input, t
    ORDER BY t
    """
    cache = None
    t = start_date
    while t < end_date:
        # Load chunk from DB doing read-ahead (if needed)
        partial_end_date = min(end_date, t + read_ahead)
        d = dict(start_date=t, end_date=partial_end_date, urls=urls)
        log.info(f"Querying fastpath from {t} to {partial_end_date}")
        cache = click.query_dataframe(sql, d)
        if len(cache) == 0:
            t = partial_end_date
            log.info("No data")
            continue
        while t < partial_end_date:
            out = cache[cache.t == t]
            if len(out):
                out = out.drop(["t"], axis=1)
                log.info(f"Returning {len(out)} rows {t}")
                yield out
            t += interval


def load_blocking_status() -> pd.DataFrame:
    """Loads the current blocking status into a dataframe."""
    log.debug("Loading blocking status")
    sql = """SELECT status, old_status, change, stability,
        test_name, probe_cc, probe_asn, input,
        accessible_perc, cnt, confirmed_perc, pure_anomaly_perc
        FROM blocking_status FINAL
    """
    blocking_status = click.query_dataframe(sql)
    if len(blocking_status) == 0:
        log.info("Starting with empty blocking_status")
        blocking_status = create_empty_status_df()

    return blocking_status


def reprocess_data_from_df(idf, debug=False):
    """Reprocess data using Pandas. Used for testing."""
    assert len(idf.index.names) == 5
    assert "Unnamed: 0" not in sorted(idf.columns), sorted(idf.columns)
    timeslots = idf.reset_index().t.unique()

    def gen():
        for tslot in timeslots:
            new = idf[idf.index.get_level_values(0) == tslot]
            assert len(new.index.names) == 5, new.index.names
            assert "Unnamed: 0" not in sorted(new.columns), sorted(new.columns)
            yield new

    events, status, status_history = reprocess_inner(gen(), len(timeslots), True)
    assert status.index.names == TCAI
    return events, status, status_history


def process(start, end, interval, services) -> None:
    events, status = process_fresh_data(start, end, interval, services)
    log.info(f"Events: {len(events)}")
    if events is not None and len(events):
        log.info("Rebuilding feeds")
        rebuild_feeds(events)
        # TODO: create an index of available RSS feeds


def reprocess(conf, services) -> None:
    click.execute("TRUNCATE TABLE blocking_status SYNC")
    click.execute("TRUNCATE TABLE blocking_events SYNC")

    t = conf.start_date
    while t < conf.end_date:
        te = t + conf.interval
        process(t, te, conf.interval, services)
        t += conf.interval


def main():
    global click
    setup()
    log.info("Starting")
    cc_to_country_name = load_country_name_map(conf.devel)
    click = Clickhouse.from_url(conf.db_uri)
    if "use_numpy" not in conf.db_uri:
        log.error("Add use_numpy to db_uri")
        return

    # create_tables()
    # TODO: configure services
    services = {
        "Facebook": ["https://www.facebook.com/"],
        "Twitter": ["https://twitter.com/"],
        "YouTube": ["https://www.youtube.com/"],
        "Instagram": ["https://www.instagram.com/"],
    }
    if conf.reprocess:
        # Destructing reprocess
        assert conf.start_date and conf.end_date, "Dates not set"
        reprocess(conf, services)
        return
        # assert conf.start_date and conf.end_date, "Dates not set"
        # events, status, _ = process_historical_data(
        #    conf.start_date, conf.end_date, conf.interval, services
        # )
        # s = status.reset_index()
        # log.info((s.accessible_perc, s.cnt, s.status))

    else:
        # Process fresh data
        if conf.end_date is None:
            # Beginning of current UTC hour
            conf.end_date = datetime(*datetime.utcnow().timetuple()[:4])
            conf.start_date = conf.end_date - conf.interval
        process(conf.start_date, conf.end_date, conf.interval, services)

    gen_stats()
    log.info("Done")


if __name__ == "__main__":
    main()
