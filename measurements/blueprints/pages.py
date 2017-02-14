import operator
import os
import re
from datetime import timedelta, datetime

from flask import Blueprint, render_template, current_app, request, redirect, \
    Response, stream_with_context
from pycountry import countries
from sqlalchemy import func
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound
from werkzeug.exceptions import BadRequest, NotFound, HTTPException

from measurements.filestore import get_download_url, gen_file_chunks, \
    FileNotFound, S3NotConfigured
from measurements.models import ReportFile

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
    if q.first() is None:
        raise StopIteration

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
        count, alpha_2 = row
        country = "Unknown"
        if alpha_2 != "ZZ":
            try:
                country = countries.get(alpha_2=alpha_2).name
            except KeyError:
                country = "Unknown (%s)" % alpha_2
        results.append({
            'count': count,
            'alpha2': alpha_2,
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

    if report_file is None:
        raise NotFound("No file with that filename found")

    if current_app.config['REPORTS_DIR'].startswith("s3://"):
        return redirect(
            get_download_url(
                current_app,
                report_file.bucket_date,
                report_file.filename
            )
        )

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
DAY_REGEXP = re.compile("^\d{4}\-[0-1]\d\-[0-3]\d$")
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
