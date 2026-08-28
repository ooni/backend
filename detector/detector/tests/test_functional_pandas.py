"""
Event detector functional tests

Run as:
pytest tests/test_functional_pandas.py -s

"""

from argparse import Namespace
from pathlib import Path

from clickhouse_driver import Client as Clickhouse
from numpy import nan
import altair as alt
import pandas as pd
import pytest

try:
    from tqdm import tqdm
except ImportError:

    def tqdm(x):
        return x


import detector.detector as dt
from detector.detector import TCAI


@pytest.fixture(scope="session", autouse=True)
def setup():
    dt.conf = Namespace()
    dt.conf.reprocess = False
    dt.conf.devel = True
    DBURI = "clickhouse://localhost/default"
    dt.click = Clickhouse.from_url(DBURI)
    dt.conf.rssdir = Path("tests/out_rss")
    dt.setup_dirs(Path("devel"))


S3BASEURL = "https://ooni-data-eu-fra-test.s3.eu-central-1.amazonaws.com/ci/"

# # utils and fixtures # #

# input dataframe #


def load_cached_input_df(fn):
    """Creates the input dataframe from CSV from S3.
    The CSV was generated with a query on the fastpath.
    Use locally cached file if found.
    """
    try:
        return pd.read_csv(fn)
    except IOError:
        print("Dloading ", S3BASEURL + fn)
        df = pd.read_csv(S3BASEURL + fn)
        print("Saving dowloaded file to ", fn)
        df.to_csv(fn)
        return df


def load_idf_1():
    fn = "event_detector_20221013_20221213_input.csv.gz"
    idf = load_cached_input_df(fn)
    if "Unnamed: 0" in idf.columns:
        idf.drop(["Unnamed: 0"], axis=1, inplace=True)

    assert sorted(idf.columns) == [
        "accessible_perc",
        "cnt",
        "confirmed_perc",
        "input",
        "probe_asn",
        "probe_cc",
        "pure_anomaly_perc",
        "t",
        "test_name",
    ]
    # granularity: 10 minutes
    assert idf.t.nunique() == 24 * 6 * 61  # every 10m, 61 days
    assert idf.shape == (274524, 9)
    assert idf.t.min() == "2022-10-13 00:00:00"
    assert idf.t.max() == "2022-12-12 23:50:00"
    x = idf.groupby(["input"]).t.nunique()
    assert x["https://twitter.com/"] == 24 * 6 * 61
    assert x["https://www.whatsapp.com/"] == 5697
    return idf


@pytest.fixture(scope="session")
def idf_1():
    return load_idf_1()


def filter_idf(idf, days=1, skipdays=0, probe_cc=None, probe_asn=None, inp=""):
    # Filter input dataframe by time, cc, asn, input
    timeslots = idf.t.unique()
    start = 6 * 24 * skipdays
    end = 6 * 24 * (skipdays + days)
    timeslots = timeslots[start:end]
    # The data processing assumes that we do a run for each timeslot without
    # skipping any interval.
    assert timeslots[0].endswith("00:00:00"), "Missing time slots"
    # We should reach the last timeslot of the day:
    assert timeslots[-1].endswith("23:50:00"), "Missing time slots"
    idf = idf[idf.t.isin(timeslots)]
    idf = idf.set_index(["t", "test_name", "probe_cc", "probe_asn", "input"])
    if probe_cc is not None:
        idf = idf[idf.index.get_level_values(2) == probe_cc]

    if isinstance(probe_asn, int):
        idf = idf[idf.index.get_level_values(3) == probe_asn]
    elif isinstance(probe_asn, list):
        idf = idf[idf.index.get_level_values(3).isin(probe_asn)]
    else:
        assert 0, type(probe_asn)

    if inp:
        idf = idf[idf.index.get_level_values(4) == inp]

    return idf


# end of input dataframe #


def plot(h, tcai, exp):
    """Generate status_history plot into an HTML file"""
    tn, cc, asn, inp = tcai
    scale = alt.Scale(
        domain=["BLOCKED", "OK", "unknown"],
        range=["red", "green", "blue"],
    )
    col = alt.Color("status", scale=scale)
    h = h.reset_index()
    h = h.loc[(h.probe_cc == cc) & (h.probe_asn == asn) & (h.input == inp)]
    assert len(h.groupby(TCAI).count()) == 1

    # Add exp col
    h["exp"] = "na"
    for tstamp, st in exp:
        if tstamp == "last":
            # hh.iloc[-1].status == st
            continue

        if " " not in tstamp:
            tstamp += " 00:00:00"
        # h.loc[h.t == tstamp, "exp"] = h[h.t == tstamp].iloc[0].status == st
        h.loc[h.t == tstamp, "exp"] = st

    c = alt.Chart(h).properties(width=1000, height=60)
    x = alt.X("t:T", axis=alt.Axis(labels=True))
    cnt = c.mark_line().encode(x=x, y="cnt", color="status")
    ap = c.mark_line().encode(x=x, y="accessible_perc", color="status")
    stability = c.mark_circle().encode(
        x=x, y=alt.Y("stability", scale=alt.Scale(zero=False)), color=col
    )
    rap = c.mark_circle().encode(x=x, y="input_ap")
    rcnt = c.mark_circle(opacity=0.4).encode(x=x, y="input_cnt", color=col)
    # Plot expected values as big dots
    expchart = c.mark_circle(size=200).encode(
        x=x,
        y="exp",
        color=col,
        opacity=alt.condition("datum.exp == 'na'", alt.value(0), alt.value(1)),
    )
    stack = rcnt & rap & cnt & ap & stability & expchart
    stack.save(f"history_{asn}_{cc}.html")


def check(status_history, tcai, exp):
    """Validate detection but also generate plots"""
    h = filter_history(status_history, tcai)
    plot(h, tcai, exp)
    for tstamp, st in exp:
        expect_status(h, tstamp, st)


def expect_status(h, tstamp, st):
    if tstamp == "last":
        assert h.iloc[-1].status == st
        return

    if " " not in tstamp:
        tstamp += " 00:00:00"
    assert h[h.t == tstamp].iloc[0].status == st


def filter_history(status_history, tcai):
    h = status_history.reset_index()
    tn, cc, asn, inp = tcai
    if asn:
        h = h[h.probe_asn == asn]
    if cc:
        h = h[h.probe_cc == cc]
    if inp:
        h = h[h.input == inp]
    return h


@pytest.fixture(scope="session")
def ru_twitter():
    # Process data for Twitter in RU for a set of ASNs
    cc = "RU"
    inp = "https://twitter.com/"
    days = 90
    inp2 = inp.replace("/", "_").replace(":", "_")
    cache_fn = f"_cache_processed_{cc}_{inp2}_{days}.csv.gz"
    kinds = ("events", "status", "history")
    try:
        # Use cached data
        out = tuple(pd.read_csv(k + cache_fn) for k in kinds)
        return out
    except FileNotFoundError:
        print("Cached ru_twitter output not found, processing now")

    idf = load_idf_1()
    asns = [8331, 12668, 13335, 44020, 44493, 48642, 49392, 51659]
    idf = filter_idf(idf, days=days, probe_cc=cc, inp=inp, probe_asn=asns)
    # idf is indexed on t+TCAI
    assert len(idf.index.names) == 5
    # Reprocess now and save to cache
    out = dt.reprocess_data_from_df(idf, debug=True)
    for item, k in zip(out, kinds):
        print("Writing out ", k, cache_fn)
        if item is None and k == "events":
            # fixme columns
            item = pd.DataFrame(["probe_asn", "probe_cc", "time", "input", "test_name"])
        item.to_csv(k + cache_fn)

    return out


# # tests # #


def NO_test_1(idf_1):
    idf = idf_1
    events, status, status_history = dt.reprocess_data(
        idf,
        days=10,
        probe_asn=12389,
        inp="https://twitter.com/",
        debug=True,
    )
    status_history.to_csv("status_history_1.csv.zstd")
    assert status_history.shape[0] == 142
    assert status.to_dict() == {
        "status": {0: nan},
        "old_status": {0: nan},
        "change": {0: nan},
        "stability": {0: 0.950923061161454},
        "test_name": {0: "web_connectivity"},
        "probe_cc": {0: "RU"},
        "probe_asn": {0: 12389},
        "input": {0: "https://twitter.com/"},
        "accessible_perc": {0: 0.0},
        "cnt": {0: 0.5823395977809029},
        "confirmed_perc": {0: 0.0},
        "pure_anomaly_perc": {0: 100.0},
    }
    assert events.to_dict() == {
        0: {
            0: "test_name",
            1: "input",
            2: "probe_cc",
            3: "probe_asn",
            4: "status",
            5: "time",
        }
    }


def NO_test_2(idf_1):
    idf = idf_1
    events, status, status_history = dt.reprocess_data(
        idf,
        days=10,
        inp="https://twitter.com/",
        debug=True,
    )
    status_history.to_csv("status_history_2.csv.zstd")
    assert status_history.shape[0] == 9336
    assert status.shape[0] == 88
    assert events.shape[0] == 0


# Test specific ASNs (in numerical order)


def test_ru_asn_8331(ru_twitter):
    events, status, status_history = ru_twitter
    assert len(status) > 10, status
    tcai = ("web_connectivity", "RU", 8331, "https://twitter.com/")
    exp = [("2022-11-02", "BLOCKED"), ("last", "BLOCKED")]
    check(status_history, tcai, exp)


def test_ru_asn_12668(ru_twitter):
    events, status, status_history = ru_twitter
    assert len(status) > 10, status
    tcai = ("web_connectivity", "RU", 12668, "https://twitter.com/")
    exp = [
        ("2022-10-20", "UNKNOWN"),
        ("2022-10-23", "BLOCKED"),
        ("2022-10-25", "BLOCKED"),
        ("2022-11-06", "BLOCKED"),
        ("last", "BLOCKED"),
    ]
    check(status_history, tcai, exp)
    h = status_history.reset_index()
    h = h[h.probe_asn == tcai[2]]


def test_ru_asn_13335(ru_twitter):
    events, status, status_history = ru_twitter
    assert len(status) > 10, status
    tcai = ("web_connectivity", "RU", 13335, "https://twitter.com/")
    exp = [("2022-10-20", "OK"), ("2022-10-23", "OK"), ("last", "OK")]
    check(status_history, tcai, exp)


def test_ru_asn_44020(ru_twitter):
    events, status, status_history = ru_twitter
    assert len(status) > 10, status
    tcai = ("web_connectivity", "RU", 44020, "https://twitter.com/")
    exp = [("2022-10-20", "OK"), ("2022-10-23", "OK"), ("last", "BLOCKED")]
    check(status_history, tcai, exp)


def test_ru_asn_44493(ru_twitter):
    events, status, status_history = ru_twitter
    assert len(status) > 10, status
    tcai = ("web_connectivity", "RU", 44493, "https://twitter.com/")
    exp = [("2022-10-20", "OK"), ("2022-10-23", "OK")]
    check(status_history, tcai, exp)
    # ("last", "OK")


def test_ru_asn_48642(ru_twitter):
    events, status, status_history = ru_twitter
    assert len(status) > 10, status
    tcai = ("web_connectivity", "RU", 48642, "https://twitter.com/")
    exp = [("2022-10-20", "OK"), ("2022-10-28", "BLOCKED"), ("last", "BLOCKED")]
    check(status_history, tcai, exp)


def test_ru_asn_49392(ru_twitter):
    events, status, status_history = ru_twitter
    assert len(status) > 10, status
    tcai = ("web_connectivity", "RU", 49392, "https://twitter.com/")
    exp = [("2022-10-30", "OK"), ("2022-11-20", "BLOCKED"), ("last", "BLOCKED")]
    check(status_history, tcai, exp)


def test_ru_asn_51659(ru_twitter):
    events, status, status_history = ru_twitter
    assert len(status) > 10, status
    tcai = ("web_connectivity", "RU", 51659, "https://twitter.com/")
    exp = []
    check(status_history, tcai, exp)


def test_summarize_changes(ru_twitter):
    events, status, status_history = ru_twitter
    assert events.shape == (7, 6)
    print(events)

    # status_history = status_history[status_history.probe_asn == 51659]
    # print("")
    # print(status_history.shape)
    # assert 0
    # assert status_history.shape == (1259383, 16)
    # s = status_history.groupby(TCAI).count()
    # assert s.shape == (281, 12)
    # print(s)
    # assert 0
