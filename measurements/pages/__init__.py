import operator
import os
import re
from datetime import timedelta, datetime

from urllib.parse import urljoin

import requests
import lz4framed

from flask import (
    Blueprint,
    render_template,
    current_app,
    request,
    redirect,
    Response,
    stream_with_context,
)

from sqlalchemy import func, or_, desc
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound
from werkzeug.exceptions import BadRequest, NotFound, HTTPException

from measurements.models import Report, Measurement, Autoclaved
from measurements.config import REQID_HDR, request_id
from measurements.countries import lookup_country

# Exporting it
from .docs import api_docs_blueprint

pages_blueprint = Blueprint(
    "pages", "measurements", static_folder="static", static_url_path="/static/"
)


DAY_REGEXP = re.compile("^\d{4}\-[0-1]\d\-[0-3]\d$")


@pages_blueprint.route("/")
def index():
    return render_template("index.html")


@pages_blueprint.route("/stats")
def stats():
    return redirect("https://explorer.ooni.org", 301)


@pages_blueprint.route("/files")
def files_index():
    return redirect("https://explorer.ooni.org/search", 301)


@pages_blueprint.route("/files/by_date")
def files_by_date():
    return redirect("https://explorer.ooni.org/search", 301)


@pages_blueprint.route("/files/by_date/<date>")
def files_on_date(date):
    if not DAY_REGEXP.match(date):
        raise BadRequest("Invalid date format")

    since = date
    until = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )
    return redirect(
        "https://explorer.ooni.org/search?until={}&since={}".format(until, since), 301
    )


@pages_blueprint.route("/files/by_country")
def files_by_country():
    return redirect("https://explorer.ooni.org/search", 301)


@pages_blueprint.route("/files/by_country/<country_code>")
def files_in_country(country_code):
    if len(country_code) != 2:
        raise BadRequest("Country code must be two characters")
    country_code = country_code.upper()
    return redirect(
        "https://explorer.ooni.org/search?probe_cc={}".format(country_code), 301
    )


def decompress_autoclaved(
    autoclaved_filename, frame_off, total_frame_size, intra_off, report_size
):
    def generator():
        try:
            url = urljoin(
                current_app.config["AUTOCLAVED_BASE_URL"], autoclaved_filename
            )
            # byte positions specified are inclusive -- https://tools.ietf.org/html/rfc7233#section-2.1
            headers = {
                "Range": "bytes={}-{}".format(
                    frame_off, frame_off + total_frame_size - 1
                ),
                REQID_HDR: request_id(),
            }
            r = requests.get(url, headers=headers, stream=True)
            r.raise_for_status()
            beginning = True
            # Create a copy because we are in a closure
            to_read = report_size
            while to_read > 1:
                for d in lz4framed.Decompressor(r.raw):
                    if beginning and intra_off > 0:
                        d = d[intra_off:]
                    if len(d) > to_read:
                        d = d[:to_read]

                    # Sanity checks to ensure the streamed data start with
                    # `{` and ends with `\n`
                    if beginning and d[:1] != b"{":
                        raise HTTPException("Chunk starts with %r != {" % d[:1])
                    if to_read == len(d) and d[-1:] != b"\n":
                        raise HTTPException("Chunk ends with %r != \\n" % d[-1:])

                    yield d
                    to_read -= len(d)
                    if len(d):  # valid lz4 frame may have 0 bytes
                        beginning = False
            # `autoclaved` file format may have `\n` in separate LZ4 frame,
            # database stores offset for JSON blobs without trailing newline,
            # here is hack adding newline as next frame boundaries are unknown.
            if r.raw.read(1) != b"":  # stream must be already EOFed
                raise HTTPException("Unprocessed LZ4 data left")
            if to_read == 1:
                yield b"\n"
        except Exception as exc:
            raise HTTPException("Failed to fetch data: %s" % exc)

    return generator


@pages_blueprint.route("/files/download/<path:textname>")
def files_download(textname):
    if "/" not in textname:
        # This is for backward compatibility with the new pipeline.
        # See: https://github.com/TheTorProject/ooni-measurements/issues/44
        q = current_app.db_session.query(Report.textname).filter(
            Report.textname.endswith(textname)
        )
        first = q.first()
        if first is None:
            raise NotFound("No file with that filename found")

        return redirect("/files/download/%s" % first[0])

    subquery = (
        current_app.db_session.query(
            Measurement.frame_off.label("frame_off"),
            Measurement.frame_size.label("frame_size"),
            Measurement.intra_off.label("intra_off"),
            Measurement.intra_size.label("intra_size"),
            func.row_number().over(order_by="frame_off, intra_off").label("row_number"),
            func.count().over().label("total_count"),
            func.sum(Measurement.intra_size + 1).over().label("report_size"),
            Autoclaved.filename.label("filename"),
        )
        .filter(Report.textname == textname)
        .join(Report, Report.report_no == Measurement.report_no)
        .join(Autoclaved, Autoclaved.autoclaved_no == Report.autoclaved_no)
        .subquery()
    )

    q = current_app.db_session.query(
        subquery.c.frame_off,
        subquery.c.frame_size,
        subquery.c.intra_off,
        subquery.c.intra_size,
        subquery.c.row_number,
        subquery.c.total_count,
        subquery.c.report_size,
        subquery.c.filename,
    ).filter(
        or_(subquery.c.row_number == 1, subquery.c.row_number == subquery.c.total_count)
    )

    msmts = q.all()
    if len(msmts) == 0:
        current_app.logger.debug("Could not find %s" % textname)
        raise NotFound("No file with that filename found")
    msmts.sort(
        key=operator.attrgetter("frame_off")
    )  # at most two rows, but it could be single

    autoclaved_filename = msmts[0].filename
    intra_off = msmts[0].intra_off
    frame_off = msmts[0].frame_off
    total_frame_size = msmts[-1].frame_off - msmts[0].frame_off + msmts[-1].frame_size
    report_size = msmts[0].report_size

    current_app.logger.debug("Computed boundaries for: %s" % autoclaved_filename)
    current_app.logger.debug("  intra_off: %d" % intra_off)
    current_app.logger.debug("  frame_off: %d" % frame_off)
    current_app.logger.debug("  total_frame_size: %d" % total_frame_size)
    current_app.logger.debug("  report_size: %d" % report_size)

    resp_generator = decompress_autoclaved(
        autoclaved_filename, frame_off, total_frame_size, intra_off, report_size
    )
    return Response(stream_with_context(resp_generator()), mimetype="text/json")


# These two are needed to avoid breaking older URLs
@pages_blueprint.route("/<date>/<report_file>")
def backward_compatible_download(date, report_file):
    if DAY_REGEXP.match(date) and report_file.endswith(".json"):
        # XXX maybe do some extra validation on report_file
        return redirect("/files/download/%s" % report_file)
    raise NotFound


@pages_blueprint.route("/<date>")
def backward_compatible_by_date(date):
    if DAY_REGEXP.match(date):
        since = date
        until = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)).strftime(
            "%Y-%m-%d"
        )
        return redirect(
            "https://explorer.ooni.org/search?until={}&since={}".format(until, since),
            301,
        )
    raise NotFound
