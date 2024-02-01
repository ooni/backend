#!/usr/bin/env python3
# # -*- coding: utf-8 -*-

"""
OONI Event detector

Run sequence:

Fetch already-processed mean values from internal data directory.
This is done to speed up restarts as processing historical data from the database
would take a very long time.

Fetch historical msmt from the fastpath and measurement/report/input tables

Fetch realtime msmt by subscribing to the notifications channel `fastpath`

Analise msmt score with moving average to detect blocking/unblocking

Save outputs to local directories:
    - RSS feed                                      /var/lib/detector/rss/
        rss/global.xml                All events, globally
        rss/by-country/<CC>.xml       Events by country
        rss/type-inp/<hash>.xml       Events by test_name and input
        rss/cc-type-inp/<hash>.xml    Events by CC, test_name and input
    - JSON files with block/unblock events          /var/lib/detector/events/
    - JSON files with current blocking status       /var/lib/detector/status/
    - Internal data                                 /var/lib/detector/_internal/

The tree under /var/lib/detector/ is served by Nginx with the exception of _internal

Events are defined as changes between blocking and non-blocking on single
CC / test_name / input tuples

Outputs are "upserted" where possible. New runs overwrite/update old data.

Runs as a service "detector" in a systemd unit and sandbox

See README.adoc
"""

# Compatible with Python3.6 and 3.7 - linted with Black
# debdeps: python3-setuptools

from argparse import ArgumentParser
from collections import namedtuple, deque
from configparser import ConfigParser
from datetime import date, datetime, timedelta
from pathlib import Path
from site import getsitepackages
import hashlib
import logging
import os
import pickle
import select
import signal
import sys

from systemd.journal import JournalHandler  # debdeps: python3-systemd
import psycopg2  # debdeps: python3-psycopg2
import psycopg2.extensions
import psycopg2.extras
import ujson  # debdeps: python3-ujson
import feedgenerator  # debdeps: python3-feedgenerator

from detector.metrics import setup_metrics
import detector.scoring as scoring

log = logging.getLogger("detector")
metrics = setup_metrics(name="detector")

DB_USER = "shovel"
DB_NAME = "metadb"
DB_PASSWORD = "yEqgNr2eXvgG255iEBxVeP"  # This is already made public

RO_DB_USER = "amsapi"
RO_DB_PASSWORD = "b2HUU6gKM19SvXzXJCzpUV"  # This is already made public

DEFAULT_STARTTIME = datetime(2016, 1, 1)

BASEURL = "http://fastpath.ooni.nu:8080"
WEBAPP_URL = BASEURL + "/webapp"

PKGDIR = getsitepackages()[-1]

conf = None
cc_to_country_name = None  # set by load_country_name_map

# Speed up psycopg2's JSON load
psycopg2.extras.register_default_jsonb(loads=ujson.loads, globally=True)
psycopg2.extras.register_default_json(loads=ujson.loads, globally=True)


def fetch_past_data(conn, start_date):
    """Fetch past data in large chunks ordered by measurement_start_time
    """
    q = """
    SELECT
        coalesce(false) as anomaly,
        coalesce(false) as confirmed,
        input,
        measurement_start_time,
        probe_cc,
        scores::text,
        coalesce('') as report_id,
        test_name,
        tid
    FROM fastpath
    WHERE measurement_start_time >= %(start_date)s
    AND measurement_start_time < %(end_date)s

    UNION

    SELECT
        anomaly,
        confirmed,
        input,
        measurement_start_time,
        probe_cc,
        coalesce('') as scores,
        report_id,
        test_name,
        coalesce('') as tid

    FROM measurement
    JOIN report ON report.report_no = measurement.report_no
    JOIN input ON input.input_no = measurement.input_no
    WHERE measurement_start_time >= %(start_date)s
    AND measurement_start_time < %(end_date)s
    ORDER BY measurement_start_time
    """
    assert start_date

    end_date = start_date + timedelta(weeks=1)

    chunk_size = 20000
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        while True:
            # Iterate across time blocks
            now = datetime.utcnow()
            # Ignore measurements with future timestamp
            if end_date > now:
                end_date = now
                log.info("Last run")
            log.info("Query from %s to %s", start_date, end_date)
            p = dict(start_date=str(start_date), end_date=str(end_date))
            cur.execute(q, p)
            while True:
                # Iterate across chunks of rows
                rows = cur.fetchmany(chunk_size)
                if not rows:
                    break
                log.info("Fetched msmt chunk of size %d", len(rows))
                for r in rows:
                    d = dict(r)
                    if d["scores"]:
                        d["scores"] = ujson.loads(d["scores"])

                    yield d

            if end_date == now:
                break

            start_date += timedelta(weeks=1)
            end_date += timedelta(weeks=1)


def fetch_past_data_selective(conn, start_date, cc, test_name, inp):
    """Fetch past data in large chunks
    """
    chunk_size = 200_000
    q = """
    SELECT
        coalesce(false) as anomaly,
        coalesce(false) as confirmed,
        input,
        measurement_start_time,
        probe_cc,
        probe_asn,
        scores::text,
        test_name,
        tid
    FROM fastpath
    WHERE measurement_start_time >= %(start_date)s
    AND probe_cc = %(cc)s
    AND test_name = %(test_name)s
    AND input = %(inp)s

    UNION

    SELECT
        anomaly,
        confirmed,
        input,
        measurement_start_time,
        probe_cc,
        probe_asn,
        coalesce('') as scores,
        test_name,
        coalesce('') as tid

    FROM measurement
    JOIN report ON report.report_no = measurement.report_no
    JOIN input ON input.input_no = measurement.input_no
    WHERE measurement_start_time >= %(start_date)s
    AND probe_cc = %(cc)s
    AND test_name = %(test_name)s
    AND input = %(inp)s

    ORDER BY measurement_start_time
    """
    p = dict(cc=cc, inp=inp, start_date=start_date, test_name=test_name)

    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(q, p)
        while True:
            rows = cur.fetchmany(chunk_size)
            if not rows:
                break
            log.info("Fetched msmt chunk of size %d", len(rows))
            for r in rows:
                d = dict(r)
                if d["scores"]:
                    d["scores"] = ujson.loads(d["scores"])

                yield d


def backfill_scores(d):
    """Generate scores dict for measurements from the traditional pipeline
    """
    if d.get("scores", None):
        return
    b = (
        scoring.anomaly
        if d["anomaly"]
        else 0 + scoring.confirmed
        if d["confirmed"]
        else 0
    )
    d["scores"] = dict(blocking_general=b)


def detect_blocking_changes_1s_g(g, cc, test_name, inp, start_date):
    """Used by webapp
    :returns: (msmts, changes)
    """
    means = {}
    msmts = []
    changes = []

    for msm in g:
        backfill_scores(msm)
        k = (msm["probe_cc"], msm["test_name"], msm["input"])
        assert isinstance(msm["scores"], dict), repr(msm["scores"])
        change = detect_blocking_changes(means, msm, warmup=True)
        date, mean, bblocked = means[k]
        val = msm["scores"]["blocking_general"]
        if change:
            changes.append(change)

        msmts.append((date, val, mean))

    log.debug("%d msmts processed", len(msmts))
    assert isinstance(msmts[0][0], datetime)
    return (msmts, changes)


def detect_blocking_changes_one_stream(conn, cc, test_name, inp, start_date):
    """Used by webapp
    :returns: (msmts, changes)
    """
    # TODO: move into webapp?
    g = fetch_past_data_selective(conn, start_date, cc, test_name, inp)
    return detect_blocking_changes_1s_g(g, cc, test_name, inp, start_date)


def load_asn_db():
    db_f = conf.vardir / "ASN.csv"
    log.info("Loading %s", db_f)
    if not db_f.is_file():
        log.info("No ASN file")
        return {}

    d = {}
    with db_f.open() as f:
        for line in f:
            try:
                asn, name = line.split(",", 1)
                asn = int(asn)
                name = name.strip()[1:-2].strip()
                d[asn] = name
            except:
                continue

    log.info("%d ASNs loaded", len(d))
    return d


def prevent_future_date(msm):
    """If the msmt time is in the future replace it with utcnow
    """
    # Timestamp are untrusted as they are generated by the probes
    # This makes the process non-deterministic and non-reproducible
    # but we can run unit tests against good inputs or mock utctime
    #
    # Warning: measurement_start_time is used for ranged queries against the DB
    # and to pinpoint measurements and changes
    now = datetime.utcnow()
    if msm["measurement_start_time"] > now:
        delta = msm["measurement_start_time"] - now
        some_id = msm.get("tid", None) or msm.get("report_id", "")
        log.info("Masking measurement %s %s in the future", some_id, delta)
        msm["measurement_start_time"] = now


def detect_blocking_changes_asn_one_stream(conn, cc, test_name, inp, start_date):
    """Used by webapp
    :returns: (msmts, changes)
    """
    g = fetch_past_data_selective(conn, start_date, cc, test_name, inp)
    means = {}
    msmts = []
    changes = []
    asn_breakdown = {}

    for msm in g:
        backfill_scores(msm)
        prevent_future_date(msm)
        k = (msm["probe_cc"], msm["test_name"], msm["input"])
        assert isinstance(msm["scores"], dict), repr(msm["scores"])
        change = detect_blocking_changes(means, msm, warmup=True)
        date, mean, _ = means[k]
        val = msm["scores"]["blocking_general"]
        if change:
            changes.append(change)

        msmts.append((date, val, mean))
        del date
        del val
        del mean
        del change

        # Generate charts for popular AS
        asn = msm["probe_asn"]
        a = asn_breakdown.get(asn, dict(means={}, msmts=[], changes=[]))
        change = detect_blocking_changes(a["means"], msm, warmup=True)
        date, mean, _ = a["means"][k]
        val = msm["scores"]["blocking_general"]
        a["msmts"].append((date, val, mean))
        if change:
            a["changes"].append(change)
        asn_breakdown[asn] = a

    log.debug("%d msmts processed", len(msmts))
    return (msmts, changes, asn_breakdown)


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

MeanStatus = namedtuple("MeanStatus", ["measurement_start_time", "val", "blocked"])


def detect_blocking_changes(means: dict, msm: dict, warmup=False):
    """Detect changes in blocking patterns
    :returns: Change or None
    """
    # TODO: move out params
    upper_limit = 0.10
    lower_limit = 0.05
    # P: averaging value
    # p=1: no averaging
    # p=0.000001: very strong averaging
    p = 0.02

    inp = msm["input"]
    if inp is None:
        return

    if not isinstance(inp, str):
        # Some inputs are lists. TODO: handle them?
        log.debug("odd input")
        return

    k = (msm["probe_cc"], msm["test_name"], inp)
    tid = msm.get("tid", None)
    report_id = msm.get("report_id", None) or None

    assert isinstance(msm["scores"], dict), repr(msm["scores"])
    blocking_general = msm["scores"]["blocking_general"]
    measurement_start_time = msm["measurement_start_time"]
    assert isinstance(measurement_start_time, datetime), repr(measurement_start_time)

    if k not in means:
        # cc/test_name/input tuple never seen before
        blocked = blocking_general > upper_limit
        means[k] = MeanStatus(measurement_start_time, blocking_general, blocked)
        if blocked:
            if not warmup:
                log.info("%r new and blocked", k)
                metrics.incr("detected_blocked")

            return Change(
                measurement_start_time=measurement_start_time,
                blocked=blocked,
                mean=blocking_general,
                probe_cc=msm["probe_cc"],
                input=msm["input"],
                test_name=msm["test_name"],
                tid=tid,
                report_id=report_id,
            )

        else:
            return None

    old = means[k]
    assert isinstance(old, MeanStatus)
    # tdelta = measurement_start_time - old.time
    # TODO: average weighting by time delta; add timestamp to status and means
    # TODO: record msm leading to status change
    new_val = (1 - p) * old.val + p * blocking_general
    means[k] = MeanStatus(measurement_start_time, new_val, old.blocked)

    if old.blocked and new_val < lower_limit:
        # blocking cleared
        means[k] = MeanStatus(measurement_start_time, new_val, False)
        if not warmup:
            log.info("%r cleared %.2f", k, new_val)
            metrics.incr("detected_cleared")

        return Change(
            measurement_start_time=measurement_start_time,
            blocked=False,
            mean=new_val,
            probe_cc=msm["probe_cc"],
            input=msm["input"],
            test_name=msm["test_name"],
            tid=tid,
            report_id=report_id,
        )

    if not old.blocked and new_val > upper_limit:
        means[k] = MeanStatus(measurement_start_time, new_val, True)
        if not warmup:
            log.info("%r blocked %.2f", k, new_val)
            metrics.incr("detected_blocked")

        return Change(
            measurement_start_time=measurement_start_time,
            blocked=True,
            mean=new_val,
            probe_cc=msm["probe_cc"],
            input=msm["input"],
            test_name=msm["test_name"],
            tid=tid,
            report_id=report_id,
        )


def parse_date(d):
    return datetime.strptime(d, "%Y-%m-%d").date()


def setup_dirs(conf, root):
    """Setup directories, creating them if needed
    """
    conf.vardir = root / "var/lib/detector"
    conf.outdir = conf.vardir / "output"
    conf.rssdir = conf.outdir / "rss"
    conf.rssdir_by_cc = conf.rssdir / "by-country"
    conf.rssdir_by_tname_inp = conf.rssdir / "type-inp"
    conf.rssdir_by_cc_tname_inp = conf.rssdir / "cc-type-inp"
    conf.eventdir = conf.outdir / "events"
    conf.statusdir = conf.outdir / "status"
    conf.pickledir = conf.outdir / "_internal"
    for p in (
        conf.vardir,
        conf.outdir,
        conf.rssdir,
        conf.rssdir_by_cc,
        conf.rssdir_by_tname_inp,
        conf.rssdir_by_cc_tname_inp,
        conf.eventdir,
        conf.statusdir,
        conf.pickledir,
    ):
        p.mkdir(parents=True, exist_ok=True)


def setup():
    os.environ["TZ"] = "UTC"
    global conf
    ap = ArgumentParser(__doc__)
    ap.add_argument("--devel", action="store_true", help="Devel mode")
    ap.add_argument("--webapp", action="store_true", help="Run webapp")
    ap.add_argument("--start-date", type=lambda d: parse_date(d))
    ap.add_argument("--db-host", default=None, help="Database hostname")
    ap.add_argument(
        "--ro-db-host", default=None, help="Read-only database hostname"
    )
    conf = ap.parse_args()
    if conf.devel:
        format = "%(relativeCreated)d %(process)d %(levelname)s %(name)s %(message)s"
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format=format)
    else:
        log.addHandler(JournalHandler(SYSLOG_IDENTIFIER="detector"))
        log.setLevel(logging.DEBUG)


    # Run inside current directory in devel mode
    root = Path(os.getcwd()) if conf.devel else Path("/")
    conf.conffile = root / "etc/detector.conf"
    log.info("Using conf file %r", conf.conffile.as_posix())
    cp = ConfigParser()
    with open(conf.conffile) as f:
        cp.read_file(f)
        conf.db_host = conf.db_host or cp["DEFAULT"]["db-host"]
        conf.ro_db_host = conf.ro_db_host or cp["DEFAULT"]["ro-db-host"]

    setup_dirs(conf, root)


@metrics.timer("handle_new_measurement")
def handle_new_msg(msg, means, rw_conn):
    """Handle one measurement received in realtime from PostgreSQL
    notifications
    """
    msm = ujson.loads(msg.payload)
    assert isinstance(msm["scores"], dict), type(msm["scores"])
    msm["measurement_start_time"] = datetime.strptime(
        msm["measurement_start_time"], "%Y-%m-%d %H:%M:%S"
    )
    log.debug("Notify for msmt from %s", msm.get("probe_cc", "<no cc>"))
    prevent_future_date(msm)
    change = detect_blocking_changes(means, msm, warmup=False)
    if change is not None:
        upsert_change(change)


def connect_to_db(db_host, db_user, db_name, db_password):
    dsn = f"host={db_host} user={db_user} dbname={db_name} password={db_password}"
    log.info("Connecting to database: %r", dsn)
    conn = psycopg2.connect(dsn)
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    return conn


def snapshot_means(msm, last_snapshot_date, means):
    """Save means to disk every month
    """
    # TODO: add config parameter to recompute past data
    t = msm["measurement_start_time"]
    month = date(t.year, t.month, 1)
    if month == last_snapshot_date:
        return last_snapshot_date

    log.info("Saving %s monthly snapshot", month)
    save_means(means, month)
    return month


def process_historical_data(ro_conn, rw_conn, start_date, means):
    """Process past data
    """
    assert start_date
    log.info("Running process_historical_data from %s", start_date)
    t = metrics.timer("process_historical_data").start()
    cnt = 0
    # fetch_past_data returns measurements ordered by measurement_start_time
    last_snap = None
    for past_msm in fetch_past_data(ro_conn, start_date):
        backfill_scores(past_msm)
        prevent_future_date(past_msm)
        last_snap = snapshot_means(past_msm, last_snap, means)
        change = detect_blocking_changes(means, past_msm, warmup=True)
        cnt += 1
        if change is not None:
            upsert_change(change)

        metrics.incr("processed_msmt")

    t.stop()
    for m in means.values():
        assert isinstance(m[2], bool), m

    blk_cnt = sum(m[2] for m in means.values())  # count blocked
    p = 100 * blk_cnt / len(means)
    log.info("%d tracked items, %d blocked (%.3f%%)", len(means), blk_cnt, p)
    log.info("Processed %d measurements. Speed: %d K-items per second", cnt, cnt / t.ms)


def create_url(change):
    return f"{WEBAPP_URL}/chart?cc={change.probe_cc}&test_name={change.test_name}&input={change.input}&start_date="


def basefn(cc, test_name, inp):
    """Generate opaque filesystem-safe filename
    inp can be "" or None (returning different hashes)
    """
    d = f"{cc}:{test_name}:{inp}"
    h = hashlib.shake_128(d.encode()).hexdigest(16)
    return h


# TODO rename changes to events?


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


def update_status_files(blocking_events):
    # The files are served by Nginx
    return  # FIXME

    # This contains the last status change for every cc/test_name/input
    # that ever had a block/unblock event
    status = {k: v[-1] for k, v in blocking_events.items()}

    statusfile = conf.statusdir / f"status.json"
    d = dict(format=1, status=status)
    with statusfile.open("w") as f:
        ujson.dump(d, f)

    log.debug("Wrote %s", statusfile)


@metrics.timer("upsert_change")
def upsert_change(change):
    """Create / update RSS and JSON files with a new change
    """
    # Create DB tables in future if needed
    debug_url = create_url(change)
    log.info("Change! %r %r", change, debug_url)
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

    update_status_files(ecache["blocking_events"])


def load_means():
    """Load means from a pkl file
    The file is safely owned by the detector.
    """
    pf = conf.pickledir / "means.pkl"
    log.info("Loading means from %s", pf)
    if pf.is_file():
        perms = pf.stat().st_mode
        assert (perms & 2) == 0, "Insecure pickle permissions %s" % oct(perms)
        with pf.open("rb") as f:
            means = pickle.load(f)

        assert means
        earliest = min(m.measurement_start_time for m in means.values())
        latest = max(m.measurement_start_time for m in means.values())
        # Cleanup
        # t = datetime.utcnow()
        # for k, m in means.items():
        #     if m.measurement_start_time > t:
        #         log.info("Fixing time")
        #         means[k] = MeanStatus(t, m.val, m.blocked)

        latest = max(m[0] for m in means.values())
        log.info("Earliest mean: %s", earliest)
        return means, latest

    log.info("Creating new means file")
    return {}, None


def save_means(means, date):
    """Save means atomically. Protocol 4
    """
    tstamp = date.strftime(".%Y-%m-%d") if date else ""
    pf = conf.pickledir / f"means{tstamp}.pkl"
    pft = pf.with_suffix(".tmp")
    if not means:
        log.error("No means to save")
        return
    log.info("Saving %d means to %s", len(means), pf)
    latest = max(m[0] for m in means.values())
    log.info("Latest mean: %s", latest)
    with pft.open("wb") as f:
        pickle.dump(means, f, protocol=4)
    pft.rename(pf)
    log.info("Saving completed")


# FIXME: for performance reasons we want to minimize heavy DB queries.
# Means are cached in a pickle file to allow restarts and we pick up where
# we stopped based on measurement_start_time. Yet the timestamp are untrusted
# as they are generated by the probes.


def load_country_name_map():
    """Load country-list.json and create a lookup dictionary
    """
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


# TODO: handle input = None both in terms of filename collision and RSS feed
# and add functional tests


def main():
    setup()
    log.info("Starting")

    global cc_to_country_name
    cc_to_country_name = load_country_name_map()

    ro_conn = connect_to_db(conf.ro_db_host, RO_DB_USER, DB_NAME, RO_DB_PASSWORD)

    if conf.webapp:
        import detector.detector_webapp as wa

        wa.db_conn = ro_conn
        wa.asn_db = load_asn_db()
        log.info("Starting webapp")
        wa.bottle.TEMPLATE_PATH.insert(0, f"{PKGDIR}/detector/views")
        wa.bottle.run(port=8880, debug=conf.devel)
        log.info("Exiting webapp")
        return

    means, latest_mean = load_means()
    log.info("Latest mean: %s", latest_mean)

    # Register exit handlers
    def save_means_on_exit(*a):
        log.info("Received SIGINT / SIGTERM")
        save_means(means, None)
        log.info("Exiting")
        sys.exit()

    signal.signal(signal.SIGINT, save_means_on_exit)
    signal.signal(signal.SIGTERM, save_means_on_exit)

    rw_conn = connect_to_db(conf.db_host, DB_USER, DB_NAME, DB_PASSWORD)

    td = timedelta(weeks=6)
    start_date = latest_mean - td if latest_mean else DEFAULT_STARTTIME
    process_historical_data(ro_conn, rw_conn, start_date, means)
    save_means(means, None)

    log.info("Starting real-time processing")
    with rw_conn.cursor() as cur:
        cur.execute("LISTEN fastpath;")

    while True:
        if select.select([rw_conn], [], [], 60) == ([], [], []):
            continue  # timeout

        rw_conn.poll()
        while rw_conn.notifies:
            msg = rw_conn.notifies.pop(0)
            try:
                handle_new_msg(msg, means, rw_conn)
            except Exception as e:
                log.exception(e)


if __name__ == "__main__":
    main()
