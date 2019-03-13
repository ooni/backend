"""
prefix: /api/_

In here live private API endpoints for use only by OONI services. You should
not rely on these as they are likely to change, break in unexpected ways. Also
there is no versioning on them.
"""
from datetime import datetime
from dateutil.relativedelta import relativedelta

from urllib.parse import urljoin

import json
import requests

from pycountry import countries

from flask import Blueprint, current_app, request
from flask.json import jsonify

from sqlalchemy import func, and_, or_, distinct, sql, select

from werkzeug.exceptions import BadRequest

from measurements.models import Report, Measurement, Input
from measurements.models import TEST_NAMES, TEST_GROUPS, get_test_group_case
from measurements.config import REQID_HDR, request_id

# prefix: /api/_
api_private_blueprint = Blueprint('api_private', 'measurements')


def api_private_stats_by_month(orm_stat):
    # data for https://api.ooni.io/stats
    # Report.test_start_time protection against time travellers may be
    # implemented in a better way, but that sanity check is probably enough.
    ## ooni_epoch = datetime(2012, 12, 1)

    now = datetime.now()
    end_date = datetime(now.year, now.month, 1)
    start_date = end_date - relativedelta(months=24)

    r = current_app.db_session.query(
            func.date_trunc('month', Report.test_start_time).label('test_start_month'),
            orm_stat
        ).filter(Report.test_start_time >= start_date).filter(Report.test_start_time < end_date
        ).group_by('test_start_month')
    result = [{
        'date': (bkt + relativedelta(months=+1, days=-1)).strftime("%Y-%m-%d"),
        'value': value,
    } for bkt, value in sorted(r)]
    return jsonify(result)

@api_private_blueprint.route('/asn_by_month')
def api_private_asn_by_month():
    # The query takes ~6s on local SSD @ AMS on 2018-04-04.
    # It was taking ~45s when it was fetching all the table from DB and doing grouping locally.
    return api_private_stats_by_month( func.count(distinct(Report.probe_asn)) )

@api_private_blueprint.route('/countries_by_month')
def api_private_countries_by_month():
    # The query takes ~10s on local SSD @ AMS on 2018-04-04.
    # It was taking ~25s when it was fetching all the table from DB and doing grouping locally.
    return api_private_stats_by_month( func.count(distinct(Report.probe_cc)) )

@api_private_blueprint.route('/runs_by_month')
def api_private_runs_by_month():
    # The query takes ~6s on local SSD @ AMS on 2018-04-04.
    # It was taking ~20s when it was fetching all the table from DB and doing grouping locally.
    return api_private_stats_by_month( func.count() )

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

# XXX Everything below here are ghetto hax to support legacy OONI Explorer
@api_private_blueprint.route('/blockpages', methods=["GET"])
def api_private_blockpages():
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

@api_private_blueprint.route('/website_measurements', methods=["GET"])
def api_private_website_measurements():
    input_ = request.args.get('input')
    if input_ is None:
        raise Exception('err')

    q = current_app.db_session.query(
        Report.report_id.label('report_id'),
        Report.probe_cc.label('probe_cc'),
        Report.probe_asn.label('probe_asn'),
        Report.test_start_time.label('test_start_time'),
        Input.input.label('input'),
    ).join(Measurement, Measurement.report_no == Report.report_no) \
     .join(Input, Measurement.input_no == Input.input_no) \
     .filter(Measurement.confirmed == True) \
     .filter(or_(
        Report.test_name == 'http_requests',
        Report.test_name == 'web_connectivity'
      )) \
     .filter(Input.input.contains(input_))

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


@api_private_blueprint.route('/blockpage_detected', methods=["GET"])
def api_private_blockpage_detected():
    q = current_app.db_session.query(
        distinct(Report.probe_cc).label('probe_cc'),
    ).join(Measurement, Measurement.report_no == Report.report_no) \
     .filter(Measurement.confirmed == True) \
     .filter(or_(
        Report.test_name == 'http_requests',
        Report.test_name == 'web_connectivity'
      ))

    results = []
    for row in q:
        results.append({
            'probe_cc': row.probe_cc
        })

    return jsonify({
        'results': results
    })


@api_private_blueprint.route('/blockpage_count', methods=["GET"])
def api_private_blockpage_count():
    probe_cc = request.args.get('probe_cc')
    if probe_cc is None:
        raise Exception('err')
    url = urljoin(current_app.config['CENTRIFUGATION_BASE_URL'],
                  'blockpage-count-%s.json' % probe_cc)
    resp_text = json.dumps({'results': []})
    resp = requests.get(url, headers={REQID_HDR: request_id()})
    if resp.status_code != 404:
        resp_text = resp.text
    return current_app.response_class(
        resp_text,
        mimetype=current_app.config['JSONIFY_MIMETYPE']
    )

@api_private_blueprint.route('/measurement_count_by_country', methods=["GET"])
def api_private_measurement_count_by_country():
    url = urljoin(current_app.config['CENTRIFUGATION_BASE_URL'], 'count-by-country.json')
    resp = requests.get(url, headers={REQID_HDR: request_id()})
    return current_app.response_class(
        resp.text,
        mimetype=current_app.config['JSONIFY_MIMETYPE']
    )


@api_private_blueprint.route('/measurement_count_total', methods=["GET"])
def api_private_measurement_count_total():
    url = urljoin(current_app.config['CENTRIFUGATION_BASE_URL'], 'count-total.json')
    resp = requests.get(url, headers={REQID_HDR: request_id()})
    return current_app.response_class(
        resp.text,
        mimetype=current_app.config['JSONIFY_MIMETYPE']
    )

def get_recent_network_coverage(probe_cc, test_groups):
    where_clause = [
        sql.text("test_start_time > current_date - interval '30 day'"),
        sql.text("probe_cc = :probe_cc"),
    ]
    if test_groups is not None:
        tg_or = []
        for tg in test_groups:
            try:
                tg_names = TEST_GROUPS[tg]
                tg_or += [sql.literal_column("test_name") == tg_name for tg_name in tg_names]
            except KeyError:
                raise Exception('invalid test_group')
        where_clause.append(or_(*tg_or))

    s = select([
        sql.text("COUNT(DISTINCT probe_asn)"),
        sql.text("date_trunc('day', test_start_time) as day")
    ]).where(
        and_(*where_clause)
    ).group_by(
        sql.text("day")
    ).order_by(
        sql.text("day")
    ).select_from(sql.table('ooexpl_recent_msmt_count'))
    network_coverage = []
    q = current_app.db_session.execute(s, {'probe_cc': probe_cc})
    for count, date in q:
        network_coverage.append({
            'count': int(count),
            'date': str(date)
        })
    return network_coverage

def get_recent_test_coverage(probe_cc):
    s = select([
        sql.text("SUM(msmt_count)"),
        sql.text("date_trunc('day', test_start_time) as day"),
        sql.text(get_test_group_case() + ' AS test_group')
    ]).where(
        and_(
            sql.text("test_start_time > current_date - interval '30 day'"),
            sql.text("probe_cc = :probe_cc"),
        )
    ).group_by(
        sql.text("test_group, day")
    ).order_by(
        sql.text("test_group, day")
    ).select_from(sql.table('ooexpl_recent_msmt_count'))

    test_coverage = []
    q = current_app.db_session.execute(s, {'probe_cc': probe_cc})
    for count, date, test_group in q:
        test_coverage.append({
            'count': int(count),
            'date': str(date),
            'test_group': test_group
        })
    return test_coverage

@api_private_blueprint.route('/test_coverage', methods=["GET"])
def api_private_test_coverage():
    probe_cc = request.args.get('probe_cc')
    if probe_cc is None or len(probe_cc) != 2:
        raise Exception('missing probe_cc')

    network_where_clause = [
        sql.text("test_start_time > current_date - interval '30 day'"),
        sql.text("probe_cc = :probe_cc"),
    ]
    test_groups = request.args.get('test_groups')
    if test_groups is not None:
        test_groups = test_groups.split(',')

    return jsonify({
        'test_coverage': get_recent_test_coverage(probe_cc),
        'network_coverage': get_recent_network_coverage(probe_cc, test_groups)
    })
