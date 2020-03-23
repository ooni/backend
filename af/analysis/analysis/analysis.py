#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""ooni-pipeline: * -> Analysis

Configured with /etc/analysis.conf

Runs as a system daemon but can also be used from command line in devel mode

Creates and updates unlogged tables.
Shows confirmed correlated by country, ASN, input URL over time.

Inputs: Database tables:
    confirmed_stats
    msm_count_by_day_by_country
    countries
    interesting_inputs

Outputs:
    Files in /var/lib/analysis
    Node exporter / prometheus metrics
    Dedicated unlogged database tables and charts
        tables:
            currently_blocked


"""

# Compatible with Python3.7 - linted with Black

# TODO:
# Enable unused code
# Switch print() to logging
# Overall datapoints count per country per day
# Add ASN to confirmed_stats and use one table only if performance is
# acceptable.
# Move slicing and manipulation entirely in Pandas and drop complex SQL queries
# Support feeder.py for continuous ingestion
# Implement a crude precision metric based on msm_count and time window

from argparse import ArgumentParser, Namespace
from configparser import ConfigParser
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from threading import Thread
from urllib.parse import urlencode
import os
import time
import logging
import sys

try:
    from systemd.journal import JournalHandler  # debdeps: python3-systemd
    import sdnotify  # debdeps: python3-sdnotify

    has_systemd = True
except ImportError:
    # this will be the case on macOS for example
    has_systemd = False

from bottle import template  # debdeps: python3-bottle
from sqlalchemy import create_engine  # debdeps: python3-sqlalchemy-ext
import matplotlib  # debdeps: python3-matplotlib
import pandas as pd  # debdeps: python3-pandas
import prometheus_client as prom  # debdeps: python3-prometheus-client
import psycopg2  # debdeps: python3-psycopg2

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns  # debdeps: python3-seaborn

from analysis.metrics import setup_metrics  # debdeps: python3-statsd

# Imported from the fastpath package
from fastpath import domain_input as domain_input_updater

from analysis.counters_table_updater import counters_table_updater

# Global conf
conf = Namespace()

# Global db connectors
dbengine = None
conn = None

log = logging.getLogger("analysis")
metrics = setup_metrics(name="analysis")

node_exporter_path = "/run/nodeexp/analysis.prom"


@contextmanager
def database_connection(c):
    conn = psycopg2.connect(
        dbname=c["dbname"], user=c["dbuser"], host=c["dbhost"], password=c["dbpassword"]
    )
    try:
        yield conn
    finally:
        conn.close()


def setup_database_connections(c):
    conn = psycopg2.connect(
        dbname=c["dbname"], user=c["dbuser"], host=c["dbhost"], password=c["dbpassword"]
    )

    dbengine = create_engine("postgresql+psycopg2://", creator=lambda: conn)
    return conn, dbengine


def gen_table(name, df, cmap="RdYlGn"):
    if cmap is None:
        tb = df.style
    else:
        tb = df.style.background_gradient(cmap=cmap)
    # df.style.bar(subset=['A', 'B'], align='mid', color=['#d65f5f', '#5fba7d'])
    html = tb.render()
    fn = os.path.join(conf.output_directory, name + ".html")
    log.info("Rendering", fn)
    with open(fn, "w") as f:
        f.write(html)


def save(name, plt):
    fn = os.path.join(conf.output_directory, name + ".png")
    log.info("Rendering", fn)
    plt.get_figure().savefig(fn)


def gen_plot(name, df, *a, **kw):
    plt = df.plot(*a, **kw)
    save(name, plt)


def heatmap(name, *a, **kw):
    fn = os.path.join(conf.output_directory, name + ".png")
    log.info("Rendering", fn)
    h = sns.heatmap(*a, **kw)
    h.get_figure().savefig(fn)


def insert_into(tablename, q):
    assert tablename in ("confirmed_stats", "confirmed_stats_asn")
    # TODO: autoreconnect
    with metrics.timer("insert_into." + tablename):
        dbengine.execute(q)


def query(q):
    # TODO: add a label to generate metrics
    log.info(" ".join(q.replace("\n", " ").split())[:300], "...")
    # TODO: autoreconnect
    with metrics.timer("query.unnamed"):
        r = pd.read_sql_query(q, conn)
    return r


@metrics.timer("populate_interesting_inputs")
def populate_interesting_inputs():
    ## Used only once to create a persistent list of targets
    dbengine.execute(
        """
        CREATE UNLOGGED TABLE interesting_inputs (
            test_name  ootest NOT NULL ,
            input text NOT NULL,
            weight integer DEFAULT 1,
            PRIMARY KEY (test_name, input)
        )"""
    )
    insert_into(
        "interesting_inputs",
        """
        INSERT INTO interesting_inputs
        SELECT
            test_name,
            input,
        COUNT(*) as cnt
        FROM measurement
        JOIN input ON input.input_no = measurement.input_no
        JOIN report ON report.report_no = measurement.report_no
        WHERE measurement_start_time > current_date - interval '2 days'
        GROUP BY test_name, input
    """,
    )


@metrics.timer("populate_countries")
def populate_countries():
    ## Used only once to create a persistent list of countries
    dbengine.execute(
        """
        CREATE UNLOGGED TABLE countries (
            probe_cc CHARACTER(2) NOT NULL,
            msm_count BIGINT NOT NULL
        );
        CREATE INDEX ON countries (msm_count);
        """
    )
    insert_into(
        "countries",
        """
        INSERT INTO countries
        SELECT
            probe_cc as country,
        COUNT(*) as msm_count
        FROM measurement
        JOIN report ON report.report_no = measurement.report_no
        WHERE measurement_start_time >= current_date - interval '5 day'
        AND measurement_start_time < current_date - interval '1 day'
        GROUP BY
            country
    """,
    )


@metrics.timer("append_confirmed_stats")
def append_confirmed_stats():
    ## Append confirmed_stats daily
    log.info("Updating confirmed_stats")
    dbengine.execute(
        """
        CREATE UNLOGGED TABLE IF NOT EXISTS confirmed_stats (
            day TIMESTAMP NOT NULL,
            probe_cc CHARACTER(2) NOT NULL,
            target TEXT,
            msm_count BIGINT NOT NULL,
            confirmed_count BIGINT NOT NULL,
            CONSTRAINT confirmed_stats_day_cc_target_u UNIQUE (day, probe_cc, target)
        ) ;
        CREATE INDEX ON confirmed_stats (day);
    """
    )
    insert_into(
        "confirmed_stats",
        """
        INSERT INTO confirmed_stats
        SELECT
            date_trunc('day', measurement_start_time) as day,
            probe_cc,
            concat(test_name, '::', input) as target,
        COUNT(*) as msm_count,
        COALESCE(SUM(CASE WHEN confirmed = TRUE THEN 1 ELSE 0 END), 0) as confirmed_count
        FROM measurement
        JOIN input ON input.input_no = measurement.input_no
        JOIN report ON report.report_no = measurement.report_no
        JOIN autoclaved ON autoclaved.autoclaved_no = report.autoclaved_no
        WHERE measurement_start_time < current_date - interval '1 day'
        AND measurement_start_time >= current_date - interval '2 day'
        GROUP BY
            day,
            probe_cc,
            target
        ON CONFLICT DO NOTHING
    """,
    )


@metrics.timer("append_confirmed_stats_asn")
def append_confirmed_stats_asn():
    ## Append confirmed_stats_asn daily
    log.info("Updating confirmed_stats_asn")
    dbengine.execute(
        """
        CREATE UNLOGGED TABLE IF NOT EXISTS confirmed_stats_asn (
            day TIMESTAMP NOT NULL,
            probe_cc CHARACTER(2) NOT NULL,
            probe_asn INTEGER NOT NULL,
            target TEXT,
            msm_count BIGINT NOT NULL,
            confirmed_count BIGINT NOT NULL,
            CONSTRAINT confirmed_stats_asn_day_cc_asn_target_u UNIQUE (day, probe_cc, probe_asn, target)
        ) ;
        CREATE INDEX ON confirmed_stats (day);
    """
    )
    insert_into(
        "confirmed_stats_asn",
        """
        INSERT INTO confirmed_stats_asn
        SELECT
            date_trunc('day', measurement_start_time) as day,
            probe_cc,
            probe_asn,
            concat(test_name, '::', input) as target,
        COUNT(*) as msm_count,
        COALESCE(SUM(CASE WHEN confirmed = TRUE THEN 1 ELSE 0 END), 0) as confirmed_count
        FROM measurement
        JOIN input ON input.input_no = measurement.input_no
        JOIN report ON report.report_no = measurement.report_no
        JOIN autoclaved ON autoclaved.autoclaved_no = report.autoclaved_no
        WHERE measurement_start_time < current_date - interval '1 day'
        AND measurement_start_time >= current_date - interval '2 day'
        GROUP BY
            day,
            probe_cc,
            probe_asn,
            target
        ON CONFLICT DO NOTHING
    """,
    )


def blocked_sites_per_country_per_week_heatmap():
    # Ratio of blocked sites per country per week
    q = query(
        """
    SELECT
    date_trunc('week', test_day) as week,
    probe_cc as country,
    SUM(confirmed_count)::decimal / SUM(msm_count) as ratio
    FROM ooexpl_wc_confirmed
    WHERE test_day > current_date - interval '1 day' - interval '10 week'
    AND test_day < current_date - interval '1 day'
    GROUP BY
    probe_cc, week
    ;
    """
    )
    x = q.pivot_table(index="week", columns="country", values="ratio")
    plt.figure(figsize=(26, 6))
    heatmap("block_ratio", x, cmap="Blues")


def input_per_day_per_country_density_heatmap():
    # Measure input-per-day-per-country datapoint density
    q = query(
        """
    SELECT
    date_trunc('week', test_day) as week,
    probe_cc as country,
    SUM(msm_count) as count
    FROM ooexpl_wc_confirmed
    WHERE test_day > current_date - interval '1 day' - interval '10 week'
    AND test_day < current_date - interval '1 day'
    GROUP BY
    week, country
    ;
    """
    )
    p = q.pivot_table(index="week", columns="country", values="count")
    heatmap("input_per_day_per_country_density", p)


def msm_count_per_week_high_countries_gentable():
    pop = query(
        """
    SELECT
    probe_cc as country,
    date_trunc('week', test_day) as week,
    SUM(msm_count) as cnt
    FROM msm_count_by_day_by_country
    WHERE test_day >= current_date - interval '1 day' - interval '6 week'
    AND test_day < current_date - interval '1 day'
    AND msm_count > 2000
    GROUP BY
    week,
    probe_cc
    ;
    """
    )
    p2 = pop.pivot_table(index="country", columns="week", values="cnt").fillna(0)
    gen_table("msm_count_per_week_high_countries", p2)


def msm_count_per_week_high_countries_gentable2():
    # Number of datapoints per week in popular countries
    q = query(
        """
    SELECT
    probe_cc as country,
    date_trunc('week', test_day) as week,
    SUM(msm_count) as cnt
    FROM msm_count_by_day_by_country
    WHERE test_day >= current_date - interval '1 day' - interval '6 week'
    AND test_day < current_date - interval '1 day'
    AND probe_cc IN (
    SELECT probe_cc
    FROM msm_count_by_day_by_country
    WHERE test_day >= current_date - interval '1 day' - interval '3 weeks'
    AND test_day < current_date - interval '1 day'
    GROUP BY probe_cc
    ORDER BY SUM(msm_count) DESC
    LIMIT 20
    )
    GROUP BY
    week,
    country
    ;
    """
    )
    p = q.pivot_table(index="country", columns="week", values="cnt").fillna(0)

    gen_table("msm_count_per_week_high_countries", p)


def msm_count_per_month_high_countries():
    # Number of datapoints per day in popular countries
    q = query(
        """
    SELECT
    probe_cc as country,
    test_day,
    SUM(msm_count) as cnt
    FROM msm_count_by_day_by_country
    WHERE test_day >= current_date - interval \'1 day\' - interval \'3 week\'
    AND test_day < current_date - interval \'1 day\'
    AND probe_cc IN (
    SELECT probe_cc
    FROM countries
    WHERE msm_count > 2000
    ORDER BY msm_count DESC
    )
    GROUP BY
    test_day,
    country
    ;
    """
    )
    p = q.pivot_table(index="country", columns="test_day", values="cnt").fillna(0)

    gen_table("msm_count_per_month_high_countries", p)


def msm_count_per_month_low_countries():
    # Number of datapoints over the last month in countries with few probes
    q = query(
        """
    SELECT probe_cc as country,
        SUM(msm_count) as cnt
    FROM msm_count_by_day_by_country
    WHERE test_day >= current_date - interval \'1 day\' - interval \'1 months\'
    AND test_day < current_date - interval \'1 day\'
    GROUP BY probe_cc
    ORDER BY cnt
    LIMIT 80
    """
    )
    p = q.pivot_table(index="country", values="cnt").fillna(0)

    gen_table("msm_count_per_month_low_countries", p)


def coverage_variance():
    ## Variance of number of datapoints over countries: high values mean unequal coverage
    q = query(
        """
    SELECT
    probe_cc as country,
    test_day,
    msm_count as cnt
    FROM msm_count_by_day_by_country
    WHERE test_day >= current_date - interval '1 day' - interval '6 week'
    AND test_day < current_date - interval '1 day'
    ;
    """
    )

    # pivot and fill NaN before calculating variance
    p = q.pivot_table(index="country", columns="test_day", values="cnt")
    p = p.fillna(0)
    relvar = p.std() / p.mean()

    plt.figure(1)
    plt.subplot(311)
    plt.plot(p.sum())
    plt.subplot(312)
    plt.plot(relvar)
    plt.subplot(313)
    plt.plot(p.var())
    fig = plt.gcf()
    fig.savefig("output/msm_count_and_variance_over_countries.png")

    ## Total number of datapoints and variance across countries per day


@metrics.timer("summarize_core_density")
def summarize_core_density():
    ## Core density
    ## Measure coverage of interesting_inputs on well-monitored countries
    core = query(
        """
    SELECT
    date_trunc('day', measurement_start_time) as day,
    probe_cc,
    concat(test_name, '::', input) as target,
    COUNT(*) as msm_count
    FROM measurement
    JOIN report ON report.report_no = measurement.report_no
    JOIN input ON input.input_no = measurement.input_no
    WHERE measurement_start_time >= current_date - interval '2 days'
    AND measurement_start_time < current_date - interval '1 days'
    AND (test_name, input) IN (
    SELECT
        test_name,
        input
    FROM interesting_inputs
    )
    AND probe_cc IN (
    SELECT
        probe_cc
    FROM
        countries
    WHERE
        msm_count > 2000
    )
    GROUP BY
    probe_cc,
    day,
    target
    """
    )

    day_slice = core.pivot_table(
        index="probe_cc", columns="target", values="msm_count", fill_value=0
    )

    log.info("Countries: ", day_slice.shape[0], "Targets:", day_slice.shape[1])
    metrics.gauge("countries_with_high_msm_count_1_day", day_slice.shape[0])
    metrics.gauge("targets_high_msm_countries_1_day", day_slice.shape[1])

    area = day_slice.shape[0] * day_slice.shape[1]
    log.info("Slice area:", area)

    c1 = core["target"].count() / area
    log.info("Coverage-1: cells with at least one datapoint", c1)
    metrics.gauge("coverage_1_day_1dp", c1)

    c5 = core[core["msm_count"] > 5]["target"].count() / area
    log.info("Coverage-5: cells with at least 5 datapoints", c5)
    metrics.gauge("coverage_1_day_5dp", c1)


def summarize_total_density_UNUSED():
    ## Total density
    ## Measure coverage of interesting_inputs on well-monitored countries
    core = query(
        """
    SELECT
    day,
    probe_cc,
    target,
    msm_count
    FROM msm_count_core
    WHERE day >= current_date - interval \'3 days\'
    AND day < current_date - interval \'2 days\'
    ;
    """
    )

    day_slice = core.pivot_table(
        index="probe_cc", columns="target", values="msm_count", fill_value=0
    )
    log.info("Countries: ", day_slice.shape[0], "Targets:", day_slice.shape[1])
    metrics.gauge("")
    metrics.gauge("")
    area = day_slice.shape[0] * day_slice.shape[1]
    log.info("Slice area:", area)
    metrics.gauge("")
    c1 = core["target"].count() / area
    log.info("Coverage-1: cells with at least one datapoint", c1)
    metrics.gauge("")
    c5 = core[core["msm_count"] > 5]["target"].count() / area
    log.info("Coverage-5: cells with at least 5 datapoints", c5)
    metrics.gauge("")

    ## Another attempt at visualizing confirmed_states
    q = query(
        """
    SELECT probe_cc, target, msm_count, confirmed_count FROM confirmed_stats
    WHERE day >= current_date - interval '8 day'
    AND day < current_date - interval '1 day'
    AND probe_cc IN (
    SELECT
        probe_cc
    FROM
        countries
    WHERE
        msm_count > 1000
    )
    AND target IN (
    SELECT
        concat(test_name, '::', input) as target
    FROM interesting_inputs
    WHERE interesting_inputs.weight > 80
    )
    ;
    """
    )

    msm = q.pivot_table(
        index="target", columns="probe_cc", values="msm_count", fill_value=0
    )
    # sort targets
    msm.sort_values(ascending=False, inplace=True, by="RU")

    # sort countries
    msm.sort_values(
        ascending=False,
        inplace=True,
        by="web_connectivity::https://www.ndi.org/",
        axis=1,
    )

    heatmap(
        "core_density",
        msm,
        cbar=False,
        annot=False,
        cmap="RdYlGn",
        xticklabels=True,
        yticklabels=False,
        vmax=10.0,
    )


@metrics.timer("measure_blocking_globally")
def measure_blocking_globally():
    ## Extract per-country blacking over time
    q = query(
        """
    SELECT
        date_trunc('week', day),
        probe_cc,
    SUM(msm_count) as msm_count,
    SUM(confirmed_count) as confirmed_count,
    SUM(confirmed_count) / SUM(msm_count) as block_ratio
    FROM confirmed_stats
    WHERE day >= current_date - interval '1 day' - interval '6 week'
    AND day < current_date - interval '1 day'
    AND target IN (
    SELECT
        concat(test_name, '::', input) as target
    FROM interesting_inputs
    WHERE interesting_inputs.weight > 80
    )
    GROUP BY
        day,
        probe_cc
    """
    )
    obt = q[q["block_ratio"] > 0.000001]
    oc = obt.pivot_table(
        index="date_trunc", columns="probe_cc", values="block_ratio", fill_value=0
    )
    gen_plot("blocked_vs_nonblocked_by_country", oc)


def create_currently_blocked_table_if_needed():
    q = """
    CREATE UNLOGGED TABLE IF NOT EXISTS currently_blocked (
        analysis_date timestamp without time zone NOT NULL,
        probe_cc CHARACTER(2) NOT NULL,
        probe_asn integer,
        target TEXT NOT NULL,
        description TEXT NOT NULL
    ) ;
    """
    dbengine.execute(q)


@metrics.timer("detect_blocking_granularity_cc_target")
def detect_blocking_granularity_cc_target(
    msm_count_threshold, block_ratio_threshold, interval="1 day"
):
    q = query(
        """
      SELECT
        probe_cc,
        target,
        SUM(msm_count) as msm_count,
        SUM(confirmed_count) as confirmed_count,
        SUM(confirmed_count) / SUM(msm_count) as block_ratio
      FROM confirmed_stats
      WHERE day >= current_date - interval '1 day' - interval '{}'
      AND day < current_date - interval '1 day'
      AND probe_cc IN (
        SELECT
          probe_cc
        FROM
          countries
        WHERE
          msm_count > 1000
      )
      AND target IN (
        SELECT
          concat(test_name, '::', input) as target
        FROM interesting_inputs
        WHERE interesting_inputs.weight > 80
      )
      GROUP BY
        probe_cc,
        target
    """.format(
            interval
        )
    )
    r = q[
        (q["msm_count"] > msm_count_threshold)
        & (q["block_ratio"] > block_ratio_threshold)
    ]
    r["description"] = "by_cc_t"
    return r


@metrics.timer("detect_blocking_granularity_cc_asn_target")
def detect_blocking_granularity_cc_asn_target(
    msm_count_threshold, block_ratio_threshold, interval="1 day"
):
    q = query(
        """
      SELECT
        probe_cc,
        probe_asn,
        target,
        SUM(msm_count) as msm_count,
        SUM(confirmed_count) as confirmed_count_with_asn,
        SUM(confirmed_count) / SUM(msm_count) as block_ratio
      FROM confirmed_stats_asn
      WHERE day >= current_date - interval '1 day' - interval '{}'
      AND day < current_date - interval '1 day'
      AND probe_cc IN (
        SELECT
          probe_cc
        FROM
          countries
        WHERE
          msm_count > 1000
      )
      AND target IN (
        SELECT
          concat(test_name, '::', input) as target
        FROM interesting_inputs
        WHERE interesting_inputs.weight > 80
      )
      GROUP BY
        probe_cc,
        probe_asn,
        target
    """.format(
            interval
        )
    )
    r = q[
        (q["msm_count"] > msm_count_threshold)
        & (q["block_ratio"] > block_ratio_threshold)
    ]
    r["description"] = "by_cc_asn_t"
    return r


@metrics.timer("detect_blocking_granularity_cc")
def detect_blocking_granularity_cc(
    msm_count_threshold, block_ratio_threshold, interval="1 day"
):
    ## Overall, per-country blocking ratio
    ## Useful to detect if a country suddenly starts blocking many targets
    q = query(
        """
      SELECT
        probe_cc,
        SUM(msm_count) as msm_count,
        SUM(confirmed_count) as confirmed_count_with_asn,
        SUM(confirmed_count) / SUM(msm_count) as block_ratio
      FROM confirmed_stats_asn
      WHERE day >= current_date - interval '1 day' - interval '{}'
      AND day < current_date - interval '1 day'
      AND probe_cc IN (
        SELECT
          probe_cc
        FROM
          countries
        WHERE
          msm_count > 1000
      )
      AND target IN (
        SELECT
          concat(test_name, '::', input) as target
        FROM interesting_inputs
        WHERE interesting_inputs.weight > 80
      )
      GROUP BY
        probe_cc
    """.format(
            interval
        )
    )
    r = q[
        (q["msm_count"] > msm_count_threshold)
        & (q["block_ratio"] > block_ratio_threshold)
    ]
    r["description"] = "by_cc"
    return r


@metrics.timer("detect_blocking")
def detect_blocking():
    ## Detect blocking by slicing the target/CC/ASN/time cubes.
    ## Slicing is done multiple times with decreasing granularity:
    ##  - target + CC + ASN
    ##  - target + CC
    ##  - CC
    ## Also the slicing is done over different time ranges:
    ##  Short time: detect blocking quickly in countries with high msm_count
    ##  Long time: detect blocking in countries with low msm_count

    ## Extract country-target time cylinders with enough datapoints to do reliable detection
    ## The thresold is controlled by the time interval and the total msm_count
    ## This allows adaptive detection over different sampling frequencies using multiple time windows

    # TODO:
    # - avoid caching tables, do everything in Pandas
    # - implement optional continuous run to prevent recreating the Cube

    # config params
    msm_count_threshold = 8
    block_ratio_threshold = 0.3
    # TODO: use different thresholds for different granularities
    # TODO: add tunable filtering by country weight and interesting_inputs

    # Detect by CC, ASN and target
    cc_asn_t_1d = detect_blocking_granularity_cc_asn_target(
        msm_count_threshold, block_ratio_threshold, interval="1 day"
    )
    metrics.gauge("cc_asn_t_1d_count", len(cc_asn_t_1d.index))

    # Detect by CC and target
    cc_t_1d = detect_blocking_granularity_cc_target(
        msm_count_threshold, block_ratio_threshold, interval="1 day"
    )
    metrics.gauge("cc_t_1d_count", len(cc_t_1d.index))
    cc_t_2w = detect_blocking_granularity_cc_target(
        msm_count_threshold, block_ratio_threshold, interval="2 weeks"
    )
    metrics.gauge("cc_t_2w_count", len(cc_t_2w.index))

    # Detect by CC only. Very low granularity but allows spotting very large
    # blocking events in low-coverage countries
    cc_1d = detect_blocking_granularity_cc(
        msm_count_threshold, block_ratio_threshold, interval="1 day"
    )
    metrics.gauge("cc_1d_count", len(cc_1d.index))

    # Create df of blocking events
    blocked = pd.concat((cc_asn_t_1d, cc_t_1d, cc_t_2w, cc_1d), sort=False)
    cols = ["probe_cc", "probe_asn", "target", "description"]
    blocked = blocked[cols]
    metrics.gauge("currently_blocked", len(blocked.index))

    log.info("currently_blocked", len(blocked.index))
    with metrics.timer("write_blocked_now"):
        blocked.to_sql("blocked", con=dbengine, if_exists="replace")


def parse_args():
    ap = ArgumentParser("Analysis script " + __doc__)
    ap.add_argument(
        "--no-update-confirmed-stats",
        action="store_true",
        help="Do not update confirmed_stats table",
    )
    ap.add_argument("--devel", action="store_true", help="Devel mode")
    ap.add_argument("--stdout", action="store_true", help="Log to stdout")
    return ap.parse_args()


def to_html(c):
    return f"""<html><body>{c}</body></html>
    """


def to_table(colnames, rowdicts) -> str:
    tpl = """
    <table>
        <tr>
        % for c in colnames:
        <th>{{c}}</th>
        % end
        </tr>
        % for d in rowdicts:
        <tr>
            % for c in colnames:
                <td>{{!d[c]}}</td>
            % end
        </tr>
        % end
    </table>
    """
    return template(tpl, colnames=colnames, rowdicts=rowdicts)


def gen_prometheus_url(expr, range_input="12h"):
    """Generate URL to point to a metric in Prometheus"""
    baseurl = "https://mon.ooni.nu/prometheus/graph?"
    return baseurl + urlencode(
        {"g0.range_input": "12h", "g0.expr": expr, "g0.tab": "0"}
    )


def html_anchor(url, text):
    return f"""<a href="{url}">{text}</a>"""


@metrics.timer("generate_slow_query_summary")
def generate_slow_query_summary(conf):
    """Generate HTML pages with a summary of heavy queries
    for active and standby database a bit like the "top" command.
    Send metrics to node exporter / Prometheus
    Show links to related charts
    """
    sql = """
        SELECT
            calls,
            mean_time / 1000 AS mean_s,
            round(total_time / 1000) AS total_seconds,
            queryid,
            query
        FROM
            pg_stat_statements
        ORDER BY
            total_time DESC
        LIMIT 16;
    """
    prom_reg = prom.CollectorRegistry()
    gauge_family = prom.Gauge(
        "db_total_query_time",
        "DB cumulative query time",
        labelnames=["db_role", "queryid"],
        registry=prom_reg,
    )
    calls_cnt = prom.Gauge(
        "db_total_query_count",
        "DB cumulative query count",
        labelnames=["db_role", "queryid"],
        registry=prom_reg,
    )
    # Monitoring URL creation
    expr_tpl = """delta(%s{db_role="%s",queryid="%s"}[1h])"""

    for role in ("active", "standby"):
        log.info("Connecting")
        conn, dbengine = setup_database_connections(getattr(conf, role))
        rows = dbengine.execute(sql)
        rows = [dict(r) for r in rows]
        for r in rows:
            queryid = r.pop("queryid")
            gauge_family.labels(role, queryid).set(r["total_seconds"])
            calls_cnt.labels(role, queryid).set(r["calls"])
            expr = expr_tpl % ("db_total_query_time", role, queryid)
            url = gen_prometheus_url(expr)
            r["total_seconds"] = html_anchor(url, r["total_seconds"])

            expr = expr_tpl % ("db_total_query_count", role, queryid)
            url = gen_prometheus_url(expr)
            r["calls"] = html_anchor(url, r["calls"])

        colnames = ["calls", "mean_s", "total_seconds", "query"]
        tbl = to_table(colnames, rows)
        html = to_html(tbl)

        fi = conf.output_directory / f"db_slow_queries_{role}.html"
        log.info("Writing %s", fi)
        fi.write_text(html)
        conn.close()

    log.info("Writing metrics to node exporter")
    prom.write_to_textfile(node_exporter_path, prom_reg)


@metrics.timer("monitor_measurement_creation")
def monitor_measurement_creation(conf):
    """Monitors measurements created by fastpath and traditional pipeline
    to detect and alert on inconsistency.
    Queries the fastpath and measurements DB tables and compare their rows
    across different time ranges and generates metrics for Prometheus.

    Runs in a dedicated thread and writes in its own .prom file

    This is the most important function, therefore it pings the SystemD watchdog
    """
    log.info("MMC: Started monitor_measurement_creation thread")
    # TODO: switch to OOID

    INTERVAL = 60 * 5
    nodeexp_path = "/run/nodeexp/db_metrics.prom"
    if has_systemd:
        watchdog = sdnotify.SystemdNotifier()

    prom_reg = prom.CollectorRegistry()
    gauge_family = prom.Gauge(
        "measurements_flow",
        "Measurements being created",
        labelnames=["type"],
        registry=prom_reg,
    )
    queries = dict(
        fastpath_count="""SELECT COUNT(*)
            FROM fastpath
            WHERE measurement_start_time > %(since)s
            AND measurement_start_time <= %(until)s
        """,
        pipeline_count="""SELECT COUNT(*)
            FROM measurement
            WHERE measurement_start_time > %(since)s
            AND measurement_start_time <= %(until)s
        """,
        pipeline_not_fastpath_count="""SELECT COUNT(*)
        FROM measurement
        LEFT OUTER JOIN input ON input.input_no = measurement.input_no
        JOIN report ON report.report_no = measurement.report_no
        WHERE NOT EXISTS (
            SELECT
            FROM fastpath fp
            WHERE measurement_start_time > %(since_ext)s
            AND measurement_start_time <= %(until_ext)s
            AND fp.report_id = report.report_id
            AND fp.test_name = report.test_name
            AND COALESCE(fp.input, '') = COALESCE(input.input, '')
        )
        AND measurement_start_time > %(since)s
        AND measurement_start_time <= %(until)s
        """,
        fastpath_not_pipeline_count="""SELECT COUNT(*)
        FROM fastpath fp
        WHERE NOT EXISTS (
            SELECT
            FROM measurement
            LEFT OUTER JOIN input ON input.input_no = measurement.input_no
            JOIN report ON report.report_no = measurement.report_no
            WHERE measurement_start_time > %(since_ext)s
            AND measurement_start_time <= %(until_ext)s
            AND fp.report_id = report.report_id
            AND fp.test_name = report.test_name
            AND COALESCE(fp.input, '') = COALESCE(input.input, '')
        )
        AND measurement_start_time > %(since)s
        AND measurement_start_time <= %(until)s
        """,
    )
    sql_replication_delay = "SELECT now() - pg_last_xact_replay_timestamp()"

    # test connection and notify systemd
    conn, _ = setup_database_connections(conf.standby)
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
    conn.close()
    if has_systemd:
        watchdog.notify("READY=1")

    cycle_seconds = 0

    while True:
        if has_systemd:
            watchdog.notify("WATCHDOG=1")
            watchdog.notify("STATUS=Running")

        try:
            log.info("MMC: Gathering fastpath count")
            conn, dbengine = setup_database_connections(conf.standby)
            delta = timedelta(minutes=5)
            now = datetime.utcnow()
            since = now - delta
            with conn.cursor() as cur:
                sql = queries["fastpath_count"]
                cur.execute(sql, dict(since=since, until=now))
                new_fp_msmt_count = cur.fetchone()[0]

            gauge_family.labels("fastpath_new_5m").set(new_fp_msmt_count)

            log.info("MMC: Gathering database replica status")
            with conn.cursor() as cur:
                cur.execute(sql_replication_delay)
                delay = cur.fetchone()[0].total_seconds()

            log.info("MMC: Comparing active and standby xlog location")
            with database_connection(conf.active) as active_conn:
                with active_conn.cursor() as cur:
                    cur.execute("SELECT pg_current_xlog_location()")
                    active_xlog_location = cur.fetchone()[0]

            with conn.cursor() as cur:
                cur.execute("SELECT pg_last_xlog_receive_location()")
                standby_xlog_location = cur.fetchone()[0]

            gauge_family.labels("raw_replication_delay").set(delay)

            if active_xlog_location == standby_xlog_location:
                gauge_family.labels("replication_delay").set(0)
            else:
                gauge_family.labels("replication_delay").set(delay)

            prom.write_to_textfile(nodeexp_path, prom_reg)

            # The following queries are heavier
            if cycle_seconds == 0:
                log.info("MMC: Running extended DB metrics gathering")
                today = datetime.utcnow().date()
                with conn.cursor() as cur:
                    # Compare different days in the past: pipeline and fastpath
                    # might be catching up on older data and we want to monitor
                    # that.
                    for age_in_days in range(3):
                        d1 = timedelta(days=1)
                        end = today - timedelta(days=age_in_days) + d1
                        times = dict(
                            until_ext=end + d1 + d1 + d1,
                            until=end,
                            since=end - d1,
                            since_ext=end - d1 - d1 - d1 - d1,
                        )
                        for query_name, sql in queries.items():
                            cur.execute(sql, times)
                            val = cur.fetchone()[0]
                            log.info(
                                "MMC: %s %s %s %d",
                                times["since"],
                                times["until"],
                                query_name,
                                val,
                            )
                            gauge_family.labels(
                                f"{query_name}_{age_in_days}_days_ago"
                            ).set(val)

                prom.write_to_textfile(nodeexp_path, prom_reg)

            cycle_seconds = (cycle_seconds + INTERVAL) % 3600

        except Exception as e:
            log.error(e, exc_info=True)

        finally:
            conn.close()
            log.debug("MMC: Done")
            if has_systemd:
                watchdog.notify("STATUS=MMC Sleeping")

            endtime = time.time() + INTERVAL
            while time.time() < endtime:
                if has_systemd:
                    watchdog.notify("WATCHDOG=1")
                time.sleep(10)


def domain_input_update_runner():
    """Runs domain_input_updater every 2 hours.
    Spawn a domain_input_updater.run() thread for each run.
    """

    def _runner():
        conf = Namespace(dry_run=False, db_uri=None)
        with metrics.timer("domain_input_updater_runtime"):
            log.info("domain_input_updater: starting")
            try:
                domain_input_updater.run(conf)
                metrics.gauge("domain_input_updater_success", 1)
                log.info("domain_input_updater: success")
            except Exception as e:
                metrics.gauge("domain_input_updater_success", 0)
                log.error("domain_input_updater: failure %r", e)

    while True:
        Thread(target=_runner).start()
        time.sleep(3600 * 2)


def main():
    global conf
    log.info("Analysis starting")
    cp = ConfigParser()
    with open("/etc/analysis.conf") as f:
        cp.read_file(f)

    conf = parse_args()
    if conf.devel or conf.stdout or not has_systemd:
        format = "%(relativeCreated)d %(process)d %(levelname)s %(name)s %(message)s"
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format=format)

    else:
        log.addHandler(JournalHandler(SYSLOG_IDENTIFIER="analysis"))
        log.setLevel(logging.DEBUG)

    for role in ("active", "standby"):
        setattr(conf, role, dict(cp[role]))

    conf.output_directory = (
        Path("./var/lib/analysis") if conf.devel else Path("/var/lib/analysis")
    )
    os.makedirs(conf.output_directory, exist_ok=True)

    t = Thread(target=monitor_measurement_creation, args=(conf,))
    t.start()

    Thread(target=domain_input_update_runner).start()

    t = Thread(target=counters_table_updater, args=(conf,))
    t.start()

    log.info("Starting generate_slow_query_summary loop")
    while True:
        generate_slow_query_summary(conf)
        time.sleep(3600)

    # # Update confirmed_stats table. The update is idempotent. The table is used
    # # in the next steps.
    # if conf.no_update_confirmed_stats == False:
    #     append_confirmed_stats()
    #     append_confirmed_stats_asn()

    # measure_blocking_globally()
    # detect_blocking()


if __name__ == "__main__":
    main()
