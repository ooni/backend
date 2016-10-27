from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os
import re
import math

from six.moves.urllib.parse import urljoin, urlencode

from flask import request, render_template, redirect
from flask import current_app, Response
from flask.json import jsonify
from flask.blueprints import Blueprint

from dateutil.parser import parse as parse_date

from sqlalchemy import func
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound

from werkzeug.exceptions import NotFound, BadRequest, HTTPException

from .config import BASE_DIR
from .models import ReportFile
from .app import cache

DAY_REGEXP = re.compile("^\d{4}\-[0-1]\d\-[0-3]\d$")

pages_blueprint = Blueprint('pages', 'measurements',
                            static_folder='static',
                            static_url_path='/static/')

@pages_blueprint.route('/')
def index():
    return render_template('index.html')

@pages_blueprint.route('/files')
def files_index():
    return render_template('files/index.html')

def _files_by_date():
    results = []
    q = current_app.db_session.query(
        func.count(ReportFile.bucket_date),
        ReportFile.bucket_date
    ).group_by(ReportFile.bucket_date).order_by(ReportFile.bucket_date)
    for row in q:
        count, day = row
        results.append({
            'count': count,
            'date': day
        })
    return results

@pages_blueprint.route('/files/by_date')
def files_by_date():
    return render_template('files/by_date.html',
                           report_dates=_files_by_date())


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
        results.append({
            'count': count,
            'alpha2': alpha2,
            'country': alpha2
        })
    return results

@pages_blueprint.route('/files/by_country')
def files_by_country():
    return render_template('files/by_country.html',
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

def _report_file_generator(filepath):
    CHUNK_SIZE = 1024
    with open(filepath) as in_file:
        while True:
            data = in_file.read(CHUNK_SIZE)
            if not data:
                break
            yield data

@pages_blueprint.route('/files/download/<filename>')
def files_download(filename):
    try:
        report_file = current_app.db_session.query(ReportFile) \
                        .filter(ReportFile.filename == filename).first()
        # XXX suriprisingly this actually fails in some cases.
        # We have duplicate measurements :(
        #   ReportFile.filename == filename).one()
    except NoResultFound:
        raise NotFound("No file with that filename found")
    except MultipleResultsFound:
        # This should never happen.
        raise HTTPException("Duplicate measurement detected")

    filepath = os.path.join(
        current_app.config['REPORTS_DIRECTORY'],
        report_file.bucket_date,
        report_file.filename
    )
    # XXX maybe have to do more to properly make it a download
    return Response(_report_file_generator(filepath),
                    mimetype='text/json')

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
    print("Handling error")
    print(dir(error))
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
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    order_by = request.args.get("order_by", 'test_start_time')
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
        ReportFile.probe_asn
    )

    # XXX maybe all of this can go into some sort of function.
    if probe_cc:
        q = q.filter(ReportFile.probe_cc == probe_cc)
    if probe_asn:
        q = q.filter(ReportFile.probe_asn == probe_asn)
    if test_name:
        q = q.filter(ReportFile.test_name == test_name)
    if start_date:
        try:
            start_date = parse_date(start_date)
        except ValueError:
            raise BadRequest("Invalid start_date")
        q = q.filter(ReportFile.test_start_time >= start_date)
    if end_date:
        try:
            end_date = parse_date(end_date)
        except ValueError:
            raise BadRequest("Invalid end_date")
        q = q.filter(ReportFile.test_start_time <= end_date)

    # XXX these are duplicated above, refactor into function
    if order.lower() not in ('asc', 'desc'):
        raise BadRequest()
    if order_by not in ('test_start_time', 'probe_cc', 'report_id',
                        'test_name', 'probe_asn'):
        raise BadRequest()

    q = q.order_by('%s %s' % (order_by, order))
    count = q.count()
    pages = math.ceil(count / limit)

    q = q.limit(limit).offset(offset)
    next_args = request.args.to_dict()
    next_args['offset'] = "%s" % (offset + limit)
    next_args['limit'] = "%s" % limit

    metadata = {
        'offset': offset,
        'limit': limit,
        'count': count,
        'pages': pages,
        'next_url': urljoin(
            current_app.config['BASE_URL'],
            '/files?%s' % urlencode(next_args)
        )
    }
    results = []
    for row in q:
        url = urljoin(
            current_app.config['BASE_URL'],
            '/files/download/%s' % row.filename
        )
        results.append({
            'url': url,
            'probe_cc': row.probe_cc,
            'probe_asn': row.probe_asn,
            'test_start_time': row.test_start_time
        })
    return jsonify({
        'metadata': metadata,
        'results': results
    })
#@api_blueprint.route('/measurement', methods=["GET"])
def api_list_measurement():
    probe_cc = request.args.get("probe_cc")
    probe_asn = request.args.get("probe_asn")
    test_name = request.args.get("test_name")
    input = request.args.get("input")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    order_by = request.args.get("order_by", 'test_start_time')
    order = request.args.get("order", 'desc')
    mrange = request.headers.get('Range', '0-100')

    return jsonify(
      probe_cc=probe_cc,
      probe_asn=probe_asn,
      mrange=mrange
    )

@api_private_blueprint.route('/asn_by_month')
@cache.cached(timeout=60*60)
def api_private_asn_by_month():
    result = []
    r = current_app.db_session.query(
            ReportFile.test_start_time,
            ReportFile.probe_asn) \
        .order_by(ReportFile.test_start_time)

    # XXX this can be done in a SQL that is not sqlite
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

    # XXX this can be done in a SQL that is not sqlite
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

    # XXX this can be done in a SQL that is not sqlite
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
