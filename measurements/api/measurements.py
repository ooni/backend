import os
import io
import re
import math
import time

from dateutil.parser import parse as parse_date

import connexion
import requests
import lz4framed

from sentry_sdk import configure_scope

from flask import Blueprint, current_app, request, make_response
from flask.json import jsonify
from werkzeug.exceptions import HTTPException, BadRequest

from sqlalchemy import func, or_, and_, false, true, text
from sqlalchemy.orm import lazyload, exc
from psycopg2.extensions import QueryCanceledError

from urllib.parse import urljoin, urlencode

from measurements import __version__
from measurements.config import REPORT_INDEX_OFFSET, REQID_HDR, request_id
from measurements.models import Report, Input, Measurement, Autoclaved

MSM_ID_PREFIX = 'temp-id'
RE_MSM_ID = re.compile('^{}-(\d+)$'.format(MSM_ID_PREFIX))

class QueryTimeoutError(HTTPException):
    code = 504
    description = (
        "The database query timed out.",
        "Try changing the query parameters."
    )

def get_version():
    return jsonify({
        "version": __version__
    })

def list_files(
        probe_asn=None,
        probe_cc=None,
        test_name=None,
        since=None,
        until=None,
        since_index=None,
        order_by='index',
        order='desc',
        offset=0,
        limit=100
    ):

    if probe_asn is not None:
        if probe_asn.startswith('AS'):
            probe_asn = probe_asn[2:]
        probe_asn = int(probe_asn)

    try:
        if since is not None:
            since = parse_date(since)
    except ValueError:
        raise BadRequest("Invalid since")

    try:
        if until is not None:
            until = parse_date(until)
    except ValueError:
        raise BadRequest("Invalid until")

    if since_index is not None:
        since_index = int(since_index)
        report_no = max(0, since_index - REPORT_INDEX_OFFSET)

    if order_by in ('index', 'idx'):
        order_by = 'report_no'

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
            'test_start_time': row.test_start_time
        })
    return jsonify({
        'metadata': metadata,
        'results': results
    })

def get_measurement(measurement_id, download=None):
    # XXX this query is SUPER slow
    m = RE_MSM_ID.match(measurement_id)
    if not m:
        raise BadRequest("Invalid measurement_id")
    msm_no = int(m.group(1))

    q = current_app.db_session.query(
            Measurement.report_no.label('report_no'),
            Measurement.frame_off.label('frame_off'),
            Measurement.frame_size.label('frame_size'),
            Measurement.intra_off.label('intra_off'),
            Measurement.intra_size.label('intra_size'),
            Report.textname.label('textname'),
            Report.report_no.label('r_report_no'),
            Report.autoclaved_no.label('r_autoclaved_no'),
            Autoclaved.filename.label('a_filename'),
            Autoclaved.autoclaved_no.label('a_autoclaved_no'),

    ).filter(Measurement.msm_no == msm_no)\
        .join(Report, Report.report_no == Measurement.report_no)\
        .join(Autoclaved, Autoclaved.autoclaved_no == Report.autoclaved_no)
    try:
        msmt = q.one()
    except exc.MultipleResultsFound:
        current_app.logger.warning("Duplicate rows for measurement_id: %s" % measurement_id)
        msmt = q.first()
    except exc.NoResultFound:
        # XXX we should actually return a 404 here
        raise BadRequest("No measurement found")

    # Usual size of LZ4 frames is 256kb of decompressed text.
    # Largest size of LZ4 frame was ~55Mb compressed and ~56Mb decompressed. :-/
    range_header = "bytes={}-{}".format(msmt.frame_off, msmt.frame_off + msmt.frame_size - 1)
    r = requests.get(urljoin(current_app.config['AUTOCLAVED_BASE_URL'], msmt.a_filename),
            headers={"Range": range_header, REQID_HDR: request_id()})
    r.raise_for_status()
    blob = r.content
    if len(blob) != msmt.frame_size:
        raise RuntimeError('Failed to fetch LZ4 frame', len(blob), msmt.frame_size)
    blob = lz4framed.decompress(blob)[msmt.intra_off:msmt.intra_off+msmt.intra_size]
    if len(blob) != msmt.intra_size or blob[:1] != b'{' or blob[-1:] != b'}':
        raise RuntimeError('Failed to decompress LZ4 frame to measurement.json', len(blob), msmt.intra_size, blob[:1], blob[-1:])
    # There is no replacement of `measurement_id` with `msm_no` or anything
    # else to keep sanity. Maybe it'll happen as part of orchestration update.
    # Also, blob is not decoded intentionally to save CPU
    filename = "ooni-msmt-{}-{}".format(measurement_id, msmt.textname.replace('/', '-'))
    response = make_response(blob)
    response.headers.set('Content-Type', 'application/json')
    if download is not None:
        response.headers.set('Content-Disposition',
                'attachment', filename=filename)
    return response

def list_measurements(
        report_id=None,
        probe_asn=None,
        probe_cc=None,
        test_name=None,
        since=None,
        until=None,
        since_index=None,
        order_by='test_start_time',
        order='desc',
        offset=0,
        limit=100,
        failure=None,
        anomaly=None,
        confirmed=None
    ):
    input_ = request.args.get("input")

    if probe_asn is not None:
        if probe_asn.startswith('AS'):
            probe_asn = probe_asn[2:]
        probe_asn = int(probe_asn)

    # When the user specifies a list that includes all the possible values for
    # boolean arguments, that is logically the same of applying no filtering at
    # all.
    if failure is not None:
        if set(failure) == set(['true', 'false']):
            failure = None
        else:
            failure = set(failure) == set(['true'])
    if anomaly is not None:
        if set(anomaly) == set(['true', 'false']):
            anomaly = None
        else:
            anomaly = set(anomaly) == set(['true'])
    if confirmed is not None:
        if set(confirmed) == set(['true', 'false']):
            confirmed = None
        else:
            confirmed = set(confirmed) == set(['true'])

    try:
        if since is not None:
            since = parse_date(since)
    except ValueError:
        raise BadRequest("Invalid since")

    try:
        if until is not None:
            until = parse_date(until)
    except ValueError:
        raise BadRequest("Invalid until")

    if order.lower() not in ('asc', 'desc'):
        raise BadRequest("Invalid order")


    c_anomaly = func.coalesce(Measurement.anomaly, false())\
                    .label('anomaly')
    c_confirmed = func.coalesce(Measurement.confirmed, false())\
                    .label('confirmed')
    c_msm_failure = func.coalesce(Measurement.msm_failure, false())\
                    .label('msm_failure')

    cols = [
        Measurement.input_no.label('m_input_no'),
        Measurement.measurement_start_time.label('measurement_start_time'),
        Measurement.msm_no.label('msm_no'),
        Measurement.report_no.label('m_report_no'),

        c_anomaly,
        c_confirmed,
        c_msm_failure,

        Measurement.exc.label('exc'),
        Measurement.residual_no.label('residual_no'),

        Report.report_id.label('report_id'),
        Report.probe_cc.label('probe_cc'),
        Report.probe_asn.label('probe_asn'),
        Report.test_name.label('test_name'),
        Report.report_no.label('report_no'),
        func.coalesce(Input.input, None).label('input')
    ]

    q = current_app.db_session.query(*cols)\
            .join(Report, Report.report_no == Measurement.report_no)

    if input_:
        q = q.join(Input, Measurement.input_no == Input.input_no)\
             .filter(Input.input.like('%{}%'.format(input_)))
    else:
        q = q.outerjoin(Input, Measurement.input_no == Input.input_no)

    if report_id:
        q = q.filter(Report.report_id == report_id)
    if probe_cc:
        q = q.filter(Report.probe_cc == probe_cc)
    if probe_asn is not None:
        q = q.filter(Report.probe_asn == probe_asn)
    if test_name is not None:
        q = q.filter(Report.test_name == test_name)
    if since is not None:
        q = q.filter(Measurement.measurement_start_time > since)
    if until is not None:
        q = q.filter(Measurement.measurement_start_time <= until)

    if confirmed is not None:
        q = q.filter(c_confirmed == confirmed)
    if anomaly is not None:
        q = q.filter(c_anomaly == anomaly)
    if failure is True:
        q = q.filter(or_(
            Measurement.exc != None,
            Measurement.residual_no != None,
            c_msm_failure == True,
        ))
    if failure is False:
        q = q.filter(and_(
            Measurement.exc == None,
            Measurement.residual_no == None,
            c_msm_failure == False
        ))

    if order_by is not None:
        q = q.order_by(text('{} {}'.format(order_by, order)))

    query_time = 0
    q = q.limit(limit).offset(offset)

    iter_start_time = time.time()
    results = []

    with configure_scope() as scope:
        scope.set_extra("sql_query", str(q))

        try:
            for row in q:
                measurement_id = '{}-{}'.format(MSM_ID_PREFIX, row.msm_no)
                url = urljoin(
                    current_app.config['BASE_URL'],
                    '/api/v1/measurement/%s' % measurement_id
                )
                results.append({
                    'measurement_url': url,
                    'measurement_id': measurement_id,
                    'report_id': row.report_id,
                    'probe_cc': row.probe_cc,
                    'probe_asn': "AS{}".format(row.probe_asn),
                    'test_name': row.test_name,
                    'measurement_start_time': row.measurement_start_time,
                    'input': row.input,
                    'anomaly': row.anomaly,
                    'confirmed': row.confirmed,
                    'failure': (row.exc != None
                                or row.residual_no != None
                                or row.msm_failure),
                })
        except exc.OperationalError as exc:
            if isinstance(exc.orig, QueryCanceledError):
                raise QueryTimeoutError()
            raise exc

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
