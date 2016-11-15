from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os
import re
import math
import operator

from datetime import datetime, timedelta

from six.moves.urllib.parse import urljoin, urlencode

from flask import request, render_template, redirect
from flask import current_app, Response, stream_with_context
from flask.json import jsonify
from flask.blueprints import Blueprint

from dateutil.parser import parse as parse_date

from sqlalchemy import func
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound

from werkzeug.exceptions import NotFound, BadRequest, HTTPException

from pycountry import countries

from measurements.config import BASE_DIR
from measurements.models import ReportFile
from measurements.app import cache
from measurements.filestore import FileNotFound, S3NotConfigured
from measurements.filestore import gen_file_chunks

DAY_REGEXP = re.compile("^\d{4}\-[0-1]\d\-[0-3]\d$")

ISO8601_UTC_FRMT = "%Y-%m-%dT%H:%M:%SZ"

pages_blueprint = Blueprint('pages', 'measurements',
                            static_folder='static',
                            static_url_path='/static/')

@pages_blueprint.route('/')
def index():
    return render_template('index.html')

@pages_blueprint.route('/stats')
def stats():
    return render_template('stats.html')

@pages_blueprint.route('/files')
def files_index():
    return render_template('files/index.html')

def _calendarized_count():
    DT_FRMT = '%Y-%m-%d'
    one_day = timedelta(days=1)

    q = current_app.db_session.query(
        func.count(ReportFile.bucket_date),
        ReportFile.bucket_date
    ).group_by(ReportFile.bucket_date).order_by(
        ReportFile.bucket_date
    )
    _, first_date = q.first()
    first_date = datetime.strptime(first_date, DT_FRMT)
    count_map = {}
    for count, day in q:
        count_map[day] = count
    last_date = datetime.strptime(day, DT_FRMT)
    start = first_date

    # here we pad up the days to the first week
    pad_from = first_date - timedelta(days=first_date.weekday())
    current_month = pad_from.month
    week = []
    month = []
    while pad_from <= first_date:
        week.append([pad_from, -1])
        pad_from += one_day

    while start <= last_date:
        if start.month != current_month:
            current_month = start.month
            month.append(week)
            yield month
            month = []
            pad_from = start - timedelta(days=start.weekday())
            week = []
            while pad_from < start:
                week.append([pad_from, -2])
                pad_from += one_day

        count = count_map.get(start.strftime(DT_FRMT), 0)
        week.append([start, count])
        if len(week) == 7:
            month.append(week)
            week = []

        start += one_day

    while len(week) < 7:
        week.append([start, -1])
        start += one_day

    if len(week) > 0:
        month.append(week)

    yield month

def _report_dates():
    q = current_app.db_session.query(
        func.count(ReportFile.bucket_date),
        ReportFile.bucket_date
    ).group_by(ReportFile.bucket_date).order_by(ReportFile.bucket_date)
    for row in q:
        count, day = row
        yield {
            'count': count,
            'date': day
        }

@pages_blueprint.route('/files/by_date')
def files_by_date():
    view = request.args.get("view", "list")
    if view == "calendar":
        return render_template('files/by_date_calendar.html',
                               calendar_count=_calendarized_count())
    else:
        return render_template('files/by_date_list.html',
                               report_dates=_report_dates())

def _files_on_date(date, order_by, order):
    q = current_app.db_session.query(ReportFile) \
            .filter(ReportFile.bucket_date == date) \
            .order_by("%s %s" % (order_by, order))
    return q

@pages_blueprint.route('/files/by_date/<date>')
def files_on_date(date):
    # XXX do some validation of date
    order_by = request.args.get('order_by', 'test_start_time')
    order = request.args.get('order', 'desc')
    if order.lower() not in ('desc', 'asc'):
        raise BadRequest()
    if order_by not in ('test_start_time', 'probe_cc', 'report_id',
                        'test_name', 'probe_asn'):
        raise BadRequest()
    return render_template('files/list.html',
                           report_files=_files_on_date(date,
                                                       order_by=order_by,
                                                       order=order),
                           by='date',
                           order=order,
                           order_by=order_by,
                           current_date=date)

def _files_by_country():
    results = []
    q = current_app.db_session.query(
        func.count(ReportFile.probe_cc),
        ReportFile.probe_cc
    ).group_by(ReportFile.probe_cc).order_by(ReportFile.probe_cc)
    for row in q:
        count, alpha2 = row
        country = "Unknown"
        if alpha2 != "ZZ":
            country = countries.get(alpha2=alpha2).name
        results.append({
            'count': count,
            'alpha2': alpha2,
            'country': country
        })
    results.sort(key=operator.itemgetter('country'))
    return results

@pages_blueprint.route('/files/by_country')
def files_by_country():
    view = request.args.get("view", "list")
    if view == "flag":
        return render_template('files/by_country_flag.html',
                               report_countries=_files_by_country())
    else:
        return render_template('files/by_country_list.html',
                               report_countries=_files_by_country())


def _files_in_country(country_code, order_by, order):
    q = current_app.db_session.query(ReportFile) \
            .filter(ReportFile.probe_cc == country_code) \
            .order_by("%s %s" % (order_by, order))
    return q

@pages_blueprint.route('/files/by_country/<country_code>')
def files_in_country(country_code):
    # XXX do some validation of date
    order_by = request.args.get('order_by', 'test_start_time')
    order = request.args.get('order', 'desc')
    if order.lower() not in ('desc', 'asc'):
        raise BadRequest()
    if order_by not in ('test_start_time', 'probe_cc', 'report_id',
                        'test_name', 'probe_asn'):
        raise BadRequest()
    return render_template('files/list.html',
                           report_files=_files_in_country(
                               country_code, order_by=order_by,
                               order=order),
                           by='country',
                           order=order,
                           order_by=order_by,
                           current_country=country_code)

@pages_blueprint.route('/files/download/<filename>')
def files_download(filename):
    try:
        report_file = current_app.db_session.query(ReportFile) \
                        .filter(ReportFile.filename == filename).first()
        # XXX
        # We have duplicate measurements :(
        # So the below exception actually happens. This should be resolved
        # in the data processing pipeline.
        #   ReportFile.filename == filename).one()
    except NoResultFound:
        raise NotFound("No file with that filename found")
    except MultipleResultsFound:
        # This should never happen.
        raise HTTPException("Duplicate measurement detected")

    filepath = os.path.join(
        current_app.config['REPORTS_DIR'],
        report_file.bucket_date,
        report_file.filename
    )

    try:
        file_chunks = gen_file_chunks(current_app, filepath)
    except FileNotFound:
        raise NotFound("File does not exist")
    except S3NotConfigured:
        raise HTTPException("S3 is not properly configured")

    response = Response(
        stream_with_context(file_chunks['content']),
        mimetype='text/json'
    )
    response.headers.add('Content-Length',
                         str(file_chunks['content_length']))
    return response

# These two are needed to avoid breaking older URLs
@pages_blueprint.route('/<date>/<report_file>')
def backward_compatible_download(date, report_file):
    if DAY_REGEXP.match(date) and report_file.endswith(".json"):
        # XXX maybe do some extra validation on report_file
        return redirect('/files/download/%s' % report_file)
    raise NotFound
@pages_blueprint.route('/<date>')
def backward_compatible_by_date(date):
    if DAY_REGEXP.match(date):
        return redirect('/files/by_date/%s' % date)
    raise NotFound

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
        url = urljoin(
            current_app.config['BASE_URL'],
            '/files/download/%s' % row.filename
        )
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

def register(app):
    app.register_blueprint(api_docs_blueprint, url_prefix='/api')
    app.register_blueprint(api_blueprint, url_prefix='/api/v1')
    app.register_blueprint(api_private_blueprint, url_prefix='/api/_')
    app.register_blueprint(pages_blueprint, url_prefix='')
