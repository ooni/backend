"""
Detector web application

Currently used only for tuning the detector, it runs event detection for one
cc / test_name / input independently from the event detector daemon.
The output are only displayed in charts and not used to generate RSS feeds
or other.

"""

# TODO: cleanup

from datetime import datetime, timedelta
import logging
import json

from bottle import request
import bottle

from detector.detector import (
    detect_blocking_changes_asn_one_stream,
)

from detector.metrics import setup_metrics

log = logging.getLogger("detector")
metrics = setup_metrics(name="detector")

db_conn = None  # Set by detector.py or during functional testing

asn_db = None  # Set by detector.py

def _datetime_handler(x):
    if isinstance(x, datetime):
        return x.isoformat()
    raise TypeError("unknown type")


bottle.install(
    bottle.JSONPlugin(json_dumps=lambda o: json.dumps(o, default=_datetime_handler))
)


def generate_chart(start_d, end_d, msmts, changes, title):
    """Render measurements and changes into a SVG chart
    :returns: dict
    """
    assert isinstance(msmts[0][0], datetime)
    x1 = 100
    x2 = 1100
    y1 = 50
    y2 = 300
    # scale x
    delta = (end_d - start_d).total_seconds()
    assert delta != 0
    x_scale = (x2 - x1) / delta

    return dict(
        msmts=msmts,
        changes=changes,
        x_scale=x_scale,
        start_d=start_d,
        end_d=end_d,
        x1=x1,
        x2=x2,
        y1=y1,
        y2=y2,
        title=title,
    )


@bottle.route("/")
@bottle.view("form")
def index():
    log.debug("Serving index")
    return {}


def plot_series(conn, ccs, test_names, inputs, start_date, split_asn):
    """Generates time-series for CC / test_name / input
    to be rendered as SVG charts
    :returns: list of charts
    """
    log.error(repr(split_asn))
    charts = []
    for cc in ccs:
        for test_name in test_names:
            for inp in inputs:
                log.info("Generating chart for %r %r %r", cc, test_name, inp)
                # TODO: merge inputs here and in event detection?

                (msmts, changes, asn_breakdown) = detect_blocking_changes_asn_one_stream(
                    conn, cc, test_name, inp, start_date
                )
                if len(msmts) < 2:
                    log.debug("Not enough data")
                    continue

                # Time range
                assert isinstance(msmts[0][0], datetime)
                start_d = min(e[0] for e in msmts)
                end_d = max(e[0] for e in msmts)
                delta = (end_d - start_d).total_seconds()
                assert delta > 0
                log.debug(delta)

                title = f"{cc} {test_name} {inp} {start_d} - {end_d}"
                country_chart = generate_chart(start_d, end_d, msmts, changes, title)

                charts.append(country_chart)

                if split_asn:
                    # Most popular ASNs
                    popular = sorted(
                        asn_breakdown, key=lambda asn: len(asn_breakdown[asn]["msmts"]), reverse=True
                    )
                    popular = popular[:20]
                    for asn in popular:
                        title = "AS{} {}".format(asn, asn_db.get(asn, ""))
                        a = asn_breakdown[asn]
                        try:
                            c = generate_chart(start_d, end_d, a["msmts"], a["changes"], title)
                            charts.append(c)
                        except:
                            log.error(a)

    return charts



@bottle.route("/chart")
@bottle.view("page")
@metrics.timer("generate_charts")
def genchart():
    params = ("ccs", "test_names", "inputs", "start_date", "split_asn")
    q = {k: (request.query.get(k, "").strip() or None) for k in params}
    assert q["ccs"], "missing ccs query param"

    ccs = [i.strip() for i in q["ccs"].split(",") if i.strip()]
    for cc in ccs:
        assert len(cc) == 2, "CC must be 2 letters"

    test_names = q["test_names"].split(",") or ["web_connectivity",]
    inputs = q["inputs"]
    assert inputs, "Inputs are required"
    inputs = [i.strip() for i in inputs.split(",") if i.strip()]
    split_asn = q["split_asn"] is not None
    start_date = q["start_date"]
    if start_date:
        start_date = datetime.strptime(start_date, "%Y-%m-%d")
    else:
        start_date = datetime.now() - timedelta(days=10)

    log.debug("Serving query %s %s %s %s", ccs, test_names, inputs, start_date)

    charts = plot_series(db_conn, ccs, test_names, inputs, start_date, split_asn)
    form = dict(
        inputs=",".join(inputs),
        test_names=",".join(test_names),
        ccs=",".join(ccs),
        start_date=start_date.strftime("%Y-%m-%d"),
        split_asn=split_asn,
    )
    return dict(charts=charts, title="Detector", form=form)


@bottle.error(500)
def error_handler_500(error):
    log.error(error.exception)
    return repr(error.exception)
