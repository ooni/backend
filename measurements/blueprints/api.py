import math
import time
import os

from datetime import datetime
from dateutil.parser import parse as parse_date

from pycountry import countries

from flask import Blueprint, render_template, current_app, request
from flask.json import jsonify
from werkzeug.exceptions import HTTPException, BadRequest

from sqlalchemy import func
from sqlalchemy.orm import lazyload

from six.moves.urllib.parse import urljoin, urlencode

from measurements.app import cache
from measurements.config import BASE_DIR
from measurements.filestore import get_download_url
from measurements.models import ReportFile, Report, Input, Measurement, Software
from measurements.models import REPORT_INDEX_OFFSET, TEST_NAMES

# prefix: /api/v1
api_blueprint = Blueprint('api', 'measurements')
# prefix: /api
api_docs_blueprint = Blueprint('api_docs', 'measurements')
# prefix: /api/_
api_private_blueprint = Blueprint('api_private', 'measurements')


@api_blueprint.errorhandler(HTTPException)
@api_blueprint.errorhandler(BadRequest)
def api_error_handler(error):
    response = jsonify({
        'error_code': error.code,
        'error_message': error.description
    })
    response.status_code = 400
    return response


@api_docs_blueprint.route('/', methods=["GET"])
def api_docs():
    with open(os.path.join(BASE_DIR, 'markdown', 'api_docs.md')) as in_file:
        docs_text = in_file.read()
    return render_template('api.html', docs_text=docs_text)


@api_private_blueprint.route('/asn_by_month')
@cache.cached(timeout=60*60)
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
@cache.cached(timeout=60*60)
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
@cache.cached(timeout=60*60)
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
@cache.cached(timeout=60*60)
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
    return jsonify({
        "countries": [{ 'alpha_2': c.alpha_2, 'name': c.name } for c in countries]
    })

@api_blueprint.route('/files', methods=["GET"])
def api_list_report_files():
    probe_cc = request.args.get("probe_cc")

    probe_asn = request.args.get("probe_asn")
    if probe_asn:
        if probe_asn.startswith('AS'):
            probe_asn = probe_asn[2:]
        probe_asn = int(probe_asn)

    test_name = request.args.get("test_name")

    since = request.args.get("since")
    try:
        if since:
            since = parse_date(since)
    except ValueError:
        raise BadRequest("Invalid since")

    until = request.args.get("until")
    try:
        if until:
            until = parse_date(until)
    except ValueError:
        raise BadRequest("Invalid until")

    since_index = request.args.get("since_index")
    if since_index:
        report_no = max(0, since_index - REPORT_INDEX_OFFSET)

    order_by = request.args.get("order_by", "index")
    if order_by in ("index", "idx"):
        order_by = "report_no"

    order = request.args.get("order", 'desc')

    try:
        offset = int(request.args.get("offset", "0"))
        limit = int(request.args.get("limit", "100"))
    except ValueError:
        raise BadRequest("Invalid offset or limit")

    q = current_app.db_session.query(
        Report.textname,
        Report.test_start_time,
        Report.probe_cc,
        Report.probe_asn,
        Report.report_no,
        Report.test_name
    )

    # XXX maybe all of this can go into some sort of function.
    if probe_cc:
        q = q.filter(Report.probe_cc == probe_cc)
    if probe_asn:
        q = q.filter(Report.probe_asn == probe_asn)
    if test_name:
        q = q.filter(Report.test_name == test_name)
    if since:
        q = q.filter(Report.test_start_time > since)
    if until:
        q = q.filter(Report.test_start_time <= until)
    if since_index:
        q = q.filter(Report.report_no > report_no)

    # XXX these are duplicated above, refactor into function
    if order.lower() not in ('asc', 'desc'):
        raise BadRequest("Invalid order")
    if order_by not in ('test_start_time', 'probe_cc', 'report_id',
                        'test_name', 'probe_asn', 'report_no'):
        raise BadRequest("Invalid order_by")

    q = q.order_by('{} {}'.format(order_by, order))
    count = q.count()
    pages = math.ceil(count / limit)
    current_page = math.ceil(offset / limit) + 1

    q = q.limit(limit).offset(offset)
    next_args = request.args.to_dict()
    next_args['offset'] = "%s" % (offset + limit)
    next_args['limit'] = "%s" % limit
    next_url = urljoin(
        current_app.config['BASE_URL'],
        '/api/v1/files?%s' % urlencode(next_args)
    )
    if current_page >= pages:
        next_url = None

    metadata = {
        'offset': offset,
        'limit': limit,
        'count': count,
        'pages': pages,
        'current_page': current_page,
        'next_url': next_url
    }
    results = []
    for row in q:
        bucket_date, filename = row.textname.split('/')
        url = get_download_url(current_app, bucket_date, filename)
        results.append({
            'download_url': url,
            'probe_cc': row.probe_cc,
            'probe_asn': "AS{}".format(row.probe_asn),
            'test_name': row.test_name,
            'index': int(row.report_no) + REPORT_INDEX_OFFSET,
            'test_start_time': row.test_start_time.strftime('%Y-%m-%dT%H:%M:%SZ')
        })
    return jsonify({
        'metadata': metadata,
        'results': results
    })


@api_blueprint.route('/measurement/<measurement_id>', methods=["GET"])
def api_get_measurement(measurement_id):
    return jsonify({
        'data_format_version': 'XXX',
        'id': measurement_id,
        'input': 'XXX',
        'measurement_start_time': 'XXX',
        'options': [],
        'probe_asn': 'XXX',
        'probe_cc': 'XXX',
        'probe_ip': 'XXX',
        'report_filename': 'XXX',
        'software_name': 'XXX',
        'software_version': 'XXX',
        'test_helpers': {},
        'test_keys': {},
        'test_name': 'XXX',
        'test_runtime': 0.1,
        'test_start_time': 'XXX'
    })

@api_blueprint.route('/measurements', methods=["GET"])
def api_list_measurements():
    report_id = request.args.get("report_id")
    input_ = request.args.get("input")

    probe_cc = request.args.get("probe_cc")
    probe_asn = request.args.get("probe_asn")
    if probe_asn:
        if probe_asn.startswith('AS'):
            probe_asn = probe_asn[2:]
        probe_asn = int(probe_asn)

    test_name = request.args.get("test_name")

    since = request.args.get("since")
    try:
        if since:
            since = parse_date(since)
    except ValueError:
        raise BadRequest("Invalid since")

    until = request.args.get("until")
    try:
        if until:
            until = parse_date(until)
    except ValueError:
        raise BadRequest("Invalid until")

    order_by = request.args.get("order_by")
    if order_by and order_by not in ('measurement_start_time', 'probe_cc',
                                     'report_id', 'test_name', 'probe_asn'):
        raise BadRequest("Invalid order_by")

    order = request.args.get("order", 'asc')
    if order.lower() not in ('asc', 'desc'):
        raise BadRequest("Invalid order")

    try:
        offset = int(request.args.get("offset", "0"))
        limit = int(request.args.get("limit", "100"))
    except ValueError:
        raise BadRequest("Invalid offset or limit")

    q = current_app.db_session.query(
            Input.input_no.label('input_no'),
            Input.input.label('input'),
            Measurement.input_no.label('m_input_no'),
            Measurement.measurement_start_time.label('measurement_start_time'),
            Measurement.id.label('m_id'),
            Measurement.report_no.label('m_report_no'),
            Report.report_id.label('report_id'),
            Report.probe_cc.label('probe_cc'),
            Report.probe_asn.label('probe_asn'),
            Report.test_name.label('test_name'),
            Report.report_no.label('report_no')
    ).join(Measurement, Measurement.input_no == Input.input_no)\
     .join(Report, Report.report_no == Measurement.report_no)

    if report_id:
        q = q.filter(Report.report_id == report_id)
    if input_:
        q = q.filter(Input.input.like('%{}%'.format(input_)))
    if probe_cc:
        q = q.filter(Report.probe_cc == probe_cc)
    if probe_asn:
        q = q.filter(Report.probe_asn == probe_asn)
    if test_name:
        q = q.filter(Report.test_name == test_name)
    if since:
        q = q.filter(Measurement.measurement_start_time > since)
    if until:
        q = q.filter(Measurement.measurement_start_time <= until)

    if order_by:
        q = q.order_by('{} {}'.format(order_by, order))

    query_time = 0
    q = q.limit(limit).offset(offset)

    iter_start_time= time.time()
    results = []
    for row in q:
        url = 'MISSING'
        results.append({
            'measurement_url': url,
            'measurement_id': row.m_id,
            'report_id': row.report_id,
            'probe_cc': row.probe_cc,
            'probe_asn': "AS{}".format(row.probe_asn),
            'test_name': row.test_name,
            'index': int(row.report_no) + REPORT_INDEX_OFFSET,
            'measurement_start_time': row.measurement_start_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'input': row.input if row.m_input_no else None,
        })

    pages = -1
    count = -1
    current_page = math.ceil(offset / limit) + 1

    # We got less results than what we expected, we know the count and that we are done
    if len(results) < limit:
        count = offset + len(results)
        pages = math.ceil(count / limit)
        next_url = None
    else:
        # XXX this is too intensive. find a workaround
        #count_start_time = time.time()
        #count = q.count()
        #pages = math.ceil(count / limit)
        #current_page = math.ceil(offset / limit) + 1
        #query_time += time.time() - count_start_time
        next_args = request.args.to_dict()
        next_args['offset'] = "%s" % (offset + limit)
        next_args['limit'] = "%s" % limit
        next_url = urljoin(
            current_app.config['BASE_URL'],
            '/api/v1/measurements?%s' % urlencode(next_args)
        )

    query_time += time.time() - iter_start_time
    metadata = {
        'offset': offset,
        'limit': limit,
        'count': count,
        'pages': pages,
        'current_page': current_page,
        'next_url': next_url,
        'query_time': query_time
    }
    return jsonify({
        'metadata': metadata,
        'results': results
    })
