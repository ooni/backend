import math
import time

from dateutil.parser import parse as parse_date

import requests
import lz4framed

from flask import Blueprint, current_app, request
from flask.json import jsonify
from werkzeug.exceptions import HTTPException, BadRequest

from sqlalchemy import func
from sqlalchemy.orm import lazyload, exc

from six.moves.urllib.parse import urljoin, urlencode

from measurements import __version__
from measurements.config import REPORT_INDEX_OFFSET
from measurements.models import Report, Input, Measurement, Autoclaved

# prefix: /api/v1
api_blueprint = Blueprint('api', 'measurements')

@api_blueprint.errorhandler(HTTPException)
@api_blueprint.errorhandler(BadRequest)
def api_error_handler(error):
    response = jsonify({
        'error_code': error.code,
        'error_message': error.description
    })
    response.status_code = 400
    return response


@api_blueprint.route('/version', methods=["GET"])
def api_get_version():
    return jsonify({
        "version": __version__
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
    if since_index is not None:
        since_index = int(since_index)
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
        download_url = urljoin(
            current_app.config['BASE_URL'],
            '/files/download/%s' % row.textname
        )
        results.append({
            'download_url': download_url,
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
    # XXX this query is SUPER slow
    q = current_app.db_session.query(
            Measurement.id.label('m_id'),
            Measurement.report_no.label('report_no'),
            Measurement.frame_off.label('frame_off'),
            Measurement.frame_size.label('frame_size'),
            Measurement.intra_off.label('intra_off'),
            Measurement.intra_size.label('intra_size'),
            Report.report_no.label('r_report_no'),
            Report.autoclaved_no.label('r_autoclaved_no'),
            Autoclaved.filename.label('a_filename'),
            Autoclaved.autoclaved_no.label('a_autoclaved_no'),

    ).filter(Measurement.id == measurement_id)\
        .join(Report, Report.report_no == Measurement.report_no)\
        .join(Autoclaved, Autoclaved.autoclaved_no == Report.autoclaved_no)
    try:
        msmt = q.one()
    except exc.MultipleResultsFound:
        current_app.logger.warning("Duplicate rows for measurement_id: %s" % measurement_id)
        msmt = q.first()

    r = requests.get(urljoin(current_app.config['AUTOCLAVED_BASE_URL'], msmt.a_filename),
            headers={"Range": "bytes={}-{}".format(msmt.frame_off, msmt.frame_off+msmt.frame_size)}, stream=True)

    # XXX use for streaming support lz4framed.Decompressor
    # @darkk how big can these lz4 frames even become? Should this be a concern?
    msmt_data = lz4framed.decompress(r.raw.read())[msmt.intra_off:msmt.intra_off+msmt.intra_size]
    return current_app.response_class(
        msmt_data,
        mimetype=current_app.config['JSONIFY_MIMETYPE']
    )

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

    iter_start_time = time.time()
    results = []
    for row in q:
        url = urljoin(
            current_app.config['BASE_URL'],
            '/api/v1/measurement/%s' % row.m_id
        )
        results.append({
            'measurement_url': url,
            'measurement_id': row.m_id,
            'report_id': row.report_id,
            'probe_cc': row.probe_cc,
            'probe_asn': "AS{}".format(row.probe_asn),
            'test_name': row.test_name,
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
