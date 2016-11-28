import math
import os

from dateutil.parser import parse as parse_date
from flask import Blueprint, render_template, current_app, request
from flask.json import jsonify
from werkzeug.exceptions import HTTPException, BadRequest

from six.moves.urllib.parse import urljoin, urlencode

from measurements.app import cache
from measurements.config import BASE_DIR
from measurements.filestore import get_download_url
from measurements.models import ReportFile

api_blueprint = Blueprint('api', 'measurements')
api_docs_blueprint = Blueprint('api_docs', 'measurements')
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
    result = []
    r = current_app.db_session.query(
            ReportFile.test_start_time,
            ReportFile.probe_asn) \
        .order_by(ReportFile.test_start_time)

    # XXX this can be done better in a SQL that is not sqlite
    monthly_buckets = {}
    for tst, asn in r:
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
    result = []
    r = current_app.db_session.query(
            ReportFile.test_start_time,
            ReportFile.probe_cc) \
        .order_by(ReportFile.test_start_time)

    # XXX this can be done better in a SQL that is not sqlite
    monthly_buckets = {}
    for tst, country in r:
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
    result = []
    r = current_app.db_session.query(
            ReportFile.test_start_time) \
        .order_by(ReportFile.test_start_time)

    # XXX this can be done better in a SQL that is not sqlite
    monthly_buckets = {}
    for res in r:
        tst = res.test_start_time
        bkt = tst.strftime("%Y-%m-01")
        monthly_buckets[bkt] = monthly_buckets.get(bkt, 0)
        monthly_buckets[bkt] += 1

    for bkt in monthly_buckets.keys():
        result.append({
            'date': bkt,
            'value': monthly_buckets[bkt]
        })

    return jsonify(result)


@api_blueprint.route('/files', methods=["GET"])
def api_list_report_files():
    probe_cc = request.args.get("probe_cc")
    probe_asn = request.args.get("probe_asn")
    test_name = request.args.get("test_name")

    since = request.args.get("since")
    until = request.args.get("until")
    since_index = request.args.get("since_index")

    order_by = request.args.get("order_by", "index")
    if order_by is "index":
        order_by = "idx"
    order = request.args.get("order", 'desc')

    try:
        offset = int(request.args.get("offset", "0"))
        limit = int(request.args.get("limit", "100"))
    except ValueError:
        raise BadRequest("Invalid offset or limit")

    q = current_app.db_session.query(
        ReportFile.filename,
        ReportFile.bucket_date,
        ReportFile.test_start_time,
        ReportFile.probe_cc,
        ReportFile.probe_asn,
        ReportFile.idx
    )

    # XXX maybe all of this can go into some sort of function.
    if probe_cc:
        q = q.filter(ReportFile.probe_cc == probe_cc)
    if probe_asn:
        q = q.filter(ReportFile.probe_asn == probe_asn)
    if test_name:
        q = q.filter(ReportFile.test_name == test_name)
    if since:
        try:
            since = parse_date(since)
        except ValueError:
            raise BadRequest("Invalid since")
        q = q.filter(ReportFile.test_start_time > since)
    if until:
        try:
            until = parse_date(until)
        except ValueError:
            raise BadRequest("Invalid until")
        q = q.filter(ReportFile.test_start_time <= until)

    if since_index:
        q = q.filter(ReportFile.idx > since_index)

    # XXX these are duplicated above, refactor into function
    if order.lower() not in ('asc', 'desc'):
        raise BadRequest("Invalid order")
    if order_by not in ('test_start_time', 'probe_cc', 'report_id',
                        'test_name', 'probe_asn', 'idx'):
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
        url = get_download_url(current_app, row.bucket_date, row.filename)
        results.append({
            'download_url': url,
            'probe_cc': row.probe_cc,
            'probe_asn': row.probe_asn,
            # Will we ever hit sys.maxint?
            'index': int(row.idx),
            'test_start_time': row.test_start_time.strftime('%Y-%m-%dT%H:%M:%SZ')
        })
    return jsonify({
        'metadata': metadata,
        'results': results
    })
