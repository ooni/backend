#
# Fastpath - event detector unit tests
#

from datetime import datetime
from pathlib import Path
import json


import bottle
import pytest

import detector.detector as dt
import detector.detector_webapp as webapp

bottle.TEMPLATE_PATH.insert(0, "detector/views")
data = Path("detector/tests/data")


def datadir(p):
    return data / p


def save(o, p):
    data.joinpath(p).write_text(json.dumps(o, sort_keys=True, default=lambda x: str(x)))


def load(p):
    with data.joinpath(p).open() as f:
        return json.load(f)


def jd(o):
    return json.dumps(o, indent=2, sort_keys=True, default=lambda x: str(x))


def trim(chart):
    [chart.pop(k) for k in list(chart) if k not in ("msmts", "changes")]


@pytest.fixture(scope="session")
def dbconn():
    # Used manually to access the database to gather and save test data
    # when writing new tests. Not used during unit testing.
    conn = dt.connect_to_db("127.0.0.1", "readonly", dt.DB_NAME, "")
    webapp.db_conn = conn
    return conn


def notest_chart_ww_BR_1(dbconn):
    cc = "BR"
    inp = "https://www.womenonwaves.org/"
    start_date = datetime(2018, 11, 1)
    test_name = "web_connectivity"
    chart = webapp.plot_series(webapp.db_conn, cc, test_name, inp, start_date)
    [chart.pop(k) for k in chart if k not in ("events", "changes")]
    expected = datadir("detector_chart_1.svg").read_text()
    assert chart == expected


def dbgenerator(fname):
    ## mock DB query
    for row in load(fname):
        st = row["measurement_start_time"]
        if isinstance(st, int):
            row["measurement_start_time"] = datetime.utcfromtimestamp(st)
        else:
            row["measurement_start_time"] = datetime.strptime(st, "%Y-%m-%d %H:%M:%S")

        yield row


def urgh(o):
    # FIXME: temporary hack to transform datetimes and truncate float numbers
    # to allow comparison
    return json.loads(jd(o))


def notest_chart_ww_BR_2():
    cc = "BR"
    inp = "https://www.womenonwaves.org/"
    start_date = datetime(2019, 1, 1)
    test_name = "web_connectivity"

    g = dbgenerator("detector_query_ww_BR_2.json")

    (msmts, changes) = dt.detect_blocking_changes_1s_g(
        g, cc, test_name, inp, start_date
    )
    # save(dict(msmts=msmts, changes=changes) , "detector_ww_BR_2_output.json")

    expected = load("detector_ww_BR_2_output.json")
    assert len(msmts) == 809
    assert urgh(msmts)[0] == expected["msmts"][0]
    assert urgh(msmts) == expected["msmts"]
    assert urgh(changes) == expected["changes"]


def test_chart_ww_BR_2019_generate_chart():
    cc = "BR"
    inp = "https://www.womenonwaves.org/"
    start_date = datetime(2019, 1, 1)
    test_name = "web_connectivity"

    g = dbgenerator("detector_query_ww_BR_2.json")

    (msmts, changes) = dt.detect_blocking_changes_1s_g(
        g, cc, test_name, inp, start_date
    )
    assert isinstance(msmts[0][0], datetime)
    # save(dict(msmts=msmts, changes=changes) , "detector_ww_BR_2019_output.json")
    expected = load("detector_ww_BR_2019_output.json")
    assert len(msmts) == 809
    u = urgh(msmts)
    for i in range(len(msmts)):
        assert u[i] == expected["msmts"][i]

    assert len(changes) == len(expected["changes"])
    for e, c in zip(expected["changes"], changes):
        ts, m, oldcode = e
        assert ts == str(c.measurement_start_time)
        assert m == c.mean

    with Path("detector/views/chart_alone.tpl").open() as f:
        tpl = webapp.bottle.SimpleTemplate(f.read())

    cd = webapp.generate_chart(msmts, changes, cc, test_name, inp)
    chart = tpl.render(**cd)
    assert chart
    data.joinpath("output/chart_ww_BR_2019.html").write_text(chart)


def test_chart_ww_BR_2018_generate_chart():
    cc = "BR"
    inp = "https://www.womenonwaves.org/"
    start_date = datetime(2018, 11, 1)
    test_name = "web_connectivity"

    # g = dt.fetch_past_data_selective(dbconn, start_date, cc, test_name, inp)
    # save(list(g), "detector_query_ww_BR_2018.json")
    g = dbgenerator("detector_query_ww_BR_2018.json")

    (msmts, changes) = dt.detect_blocking_changes_1s_g(
        g, cc, test_name, inp, start_date
    )
    assert isinstance(msmts[0][0], datetime)
    # save(dict(msmts=msmts, changes=changes) , "detector_ww_BR_2018_output.json")
    expected = load("detector_ww_BR_2018_output.json")
    assert len(msmts) == 911
    u = urgh(msmts)
    for i in range(len(msmts)):
        assert u[i] == expected["msmts"][i]

    assert len(changes) == len(expected["changes"])
    for e, c in zip(expected["changes"], changes):
        ts, m, oldcode = e
        assert ts == str(c.measurement_start_time)
        assert m == c.mean

    with Path("detector/views/chart_alone.tpl").open() as f:
        tpl = webapp.bottle.SimpleTemplate(f.read())

    cd = webapp.generate_chart(msmts, changes, cc, test_name, inp)
    chart = tpl.render(**cd)
    assert chart
    data.joinpath("output/chart_ww_BR_2018.html").write_text(chart)


def bench_detect_blocking_changes_1s_g(g):
    cc = "BR"
    inp = "foo"
    start_date = datetime(2019, 1, 1)
    test_name = "web_connectivity"
    return dt.detect_blocking_changes_1s_g(
        g, cc, test_name, inp, start_date
    )


def test_bench_detect_blocking_changes(benchmark):
    # debdeps: python3-pytest-benchmark
    g = []
    for x in range(1020):
        v = {
            "anomaly": None if (int(x / 100) % 2 == 0) else True,
            "confirmed": None,
            "input": "foo",
            "measurement_start_time": datetime.utcfromtimestamp(x + 1234567890),
            "probe_cc": "BR",
            "scores": "",
            "test_name": "web_connectivity",
            "tid": "",
        }
        g.append(v)
    (msmts, changes) = benchmark(bench_detect_blocking_changes_1s_g, g)

    with Path("detector/views/chart_alone.tpl").open() as f:
        tpl = webapp.bottle.SimpleTemplate(f.read())

    cc = "BR"
    inp = "foo"
    test_name = "web_connectivity"
    cd = webapp.generate_chart(msmts, changes, cc, test_name, inp)
    chart = tpl.render(**cd)
    assert chart
    data.joinpath("output/chart_ww_BR_bench.html").write_text(chart)
    last_mean = msmts[-1][-1]
    assert pytest.approx(0.415287511652) == last_mean


def notest_chart_ww_BR():
    cc = "BR"
    inp = "https://www.womenonwaves.org/"
    start_date = datetime(2018, 11, 1)
    test_name = "web_connectivity"
    chart1 = webapp.plot_series(webapp.db_conn, cc, test_name, inp, start_date)
    start_date = datetime(2019, 1, 1)
    chart2 = webapp.plot_series(webapp.db_conn, cc, test_name, inp, start_date)
    chart = chart1 + chart2
    # data.joinpath("detector_chart_ww_BR.svg").write_text(chart)
    # expected = data.joinpath("detector_chart_2.svg").read_text()
    # assert chart == expected
