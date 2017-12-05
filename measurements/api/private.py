"""
prefix: /api/_

In here live private API endpoints for use only by OONI services. You should
not rely on these as they are likely to change, break in unexpected ways. Also
there is no versioning on them.
"""
from datetime import datetime

from six.moves.urllib.parse import urljoin

import requests

from pycountry import countries

from flask import Blueprint, current_app, request
from flask.json import jsonify

from sqlalchemy import func, or_

from werkzeug.exceptions import BadRequest

from measurements.models import Report, Measurement, Input
from measurements.models import TEST_NAMES

# prefix: /api/_
api_private_blueprint = Blueprint('api_private', 'measurements')

@api_private_blueprint.route('/asn_by_month')
def api_private_asn_by_month():
    NOW = datetime.now()
    result = []
    r = current_app.db_session.query(
            Report.test_start_time,
            Report.probe_asn) \
        .order_by(Report.test_start_time)

    # XXX this can be done better in a SQL that is not sqlite
    monthly_buckets = {}
    for tst, asn in r:
        asn = 'AS%d' % asn
        if tst > NOW:
            # We ignore measurements from time travelers
            continue
        bkt = tst.strftime("%Y-%m-01")
        monthly_buckets[bkt] = monthly_buckets.get(bkt, [])
        if asn not in monthly_buckets[bkt]:
            monthly_buckets[bkt].append(asn)

    for bkt in monthly_buckets.keys():
        result.append({
            'date': bkt,
            'value': len(monthly_buckets[bkt])
        })
    return jsonify(result)


@api_private_blueprint.route('/countries_by_month')
def api_private_counties_by_month():
    NOW = datetime.now()
    result = []
    r = current_app.db_session.query(
            Report.test_start_time,
            Report.probe_cc) \
        .order_by(Report.test_start_time)

    # XXX this can be done better in a SQL that is not sqlite
    monthly_buckets = {}
    for tst, country in r:
        if tst > NOW:
            # We ignore measurements from time travelers
            continue
        bkt = tst.strftime("%Y-%m-01")
        monthly_buckets[bkt] = monthly_buckets.get(bkt, [])
        if country not in monthly_buckets[bkt]:
            monthly_buckets[bkt].append(country)

    for bkt in monthly_buckets.keys():
        result.append({
            'date': bkt,
            'value': len(monthly_buckets[bkt])
        })
    return jsonify(result)


@api_private_blueprint.route('/runs_by_month')
def api_private_runs_by_month():
    NOW = datetime.now()
    result = []
    r = current_app.db_session.query(
            Report.test_start_time) \
        .order_by(Report.test_start_time)

    # XXX this can be done better in a SQL that is not sqlite
    monthly_buckets = {}
    for res in r:
        tst = res.test_start_time
        if tst > NOW:
            # We ignore measurements from time travelers
            continue
        bkt = tst.strftime("%Y-%m-01")
        monthly_buckets[bkt] = monthly_buckets.get(bkt, 0)
        monthly_buckets[bkt] += 1

    for bkt in monthly_buckets.keys():
        result.append({
            'date': bkt,
            'value': monthly_buckets[bkt]
        })

    return jsonify(result)

@api_private_blueprint.route('/reports_per_day')
def api_private_reports_per_day():
    q = current_app.db_session.query(
        func.count(func.date_trunc('day', Report.test_start_time)),
        func.date_trunc('day', Report.test_start_time)
    ).group_by(func.date_trunc('day', Report.test_start_time)).order_by(
        func.date_trunc('day', Report.test_start_time)
    )
    result = []
    for count, date in q:
        result.append({
            'count': count,
            'date': date.strftime("%Y-%m-%d")
        })
    return jsonify(result)

@api_private_blueprint.route('/test_names', methods=["GET"])
def api_private_test_names():
    return jsonify({
        "test_names": [{ 'id': k, 'name': v } for k, v in TEST_NAMES.items()]
    })

@api_private_blueprint.route('/countries', methods=["GET"])
def api_private_countries():
    with_counts = request.args.get("with_counts")
    country_list = []
    if not with_counts:
        country_list = [{ 'alpha_2': c.alpha_2, 'name': c.name } for c in countries]
    else:
        # XXX we probably actually want to get this from redis or compute it
        # periodically since it take 60 seconds to run.
        q = current_app.db_session.query(
                func.count(Measurement.id),
                Report.probe_cc.label('probe_cc')
        ).join(Report, Report.report_no == Measurement.report_no) \
         .group_by(Report.probe_cc)
        for count, probe_cc in q:
            if probe_cc.upper() == 'ZZ':
                continue

            try:
                c = countries.lookup(probe_cc)
                country_list.append({
                    'count': count,
                    'alpha_2': c.alpha_2,
                    'name': c.name,
                })
            except Exception as exc:
                current_app.logger.warning("Failed to lookup: %s" % probe_cc)

    return jsonify({
        "countries": country_list
    })


@api_private_blueprint.route('/blockpages', methods=["GET"])
def api_private_blockpage_list():
    probe_cc = request.args.get('probe_cc')
    if probe_cc is None:
        raise Exception('err')

    q = current_app.db_session.query(
        Report.report_id.label('report_id'),
        Report.probe_cc.label('probe_cc'),
        Report.probe_asn.label('probe_asn'),
        Report.test_start_time.label('test_start_time'),
        Input.input.label('input')
    ).join(Measurement, Measurement.report_no == Report.report_no) \
     .join(Input, Measurement.input_no == Input.input_no) \
     .filter(Measurement.confirmed == True) \
     .filter(or_(
        Report.test_name == 'http_requests',
        Report.test_name == 'web_connectivity'
      )) \
     .filter(Report.probe_cc == probe_cc)

    results = []
    for row in q:
        results.append({
            'report_id': row.report_id,
            'probe_cc': row.probe_cc,
            'probe_asn': "AS{}".format(row.probe_asn),
            'test_start_time': row.test_start_time,
            'input': row.input
        })

    return jsonify({
        'results': results
    })

@api_private_blueprint.route('/measurement_count_by_country', methods=["GET"])
def api_private_measurement_count_by_country():
    url = urljoin(current_app.config['CENTRIFUGATION_BASE_URL'], 'count-by-country.json')
    resp = requests.get(url)
    return current_app.response_class(
        resp.text,
        mimetype=current_app.config['JSONIFY_MIMETYPE']
    )


@api_private_blueprint.route('/measurement_count_total', methods=["GET"])
def api_private_measurement_count_total():
    url = urljoin(current_app.config['CENTRIFUGATION_BASE_URL'], 'count-total.json')
    resp = requests.get(url)
    return current_app.response_class(
        resp.text,
        mimetype=current_app.config['JSONIFY_MIMETYPE']
    )
