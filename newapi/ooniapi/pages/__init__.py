"""
OONI API - various pages e.g.
    /  <index>
    /files

    Redirects:
    /stats
    /files
    /files/by_date
"""


import operator
import re
from datetime import timedelta, datetime

from urllib.parse import urljoin

import requests
try:
    import lz4framed
except ImportError:
    pass

from flask import (
    Blueprint,
    render_template,
    current_app,
    redirect,
    Response,
    stream_with_context,
    send_file,
)

from werkzeug.exceptions import BadRequest, NotFound, HTTPException

from ooniapi.config import REQID_HDR, request_id

# Exporting it
from .docs import api_docs_blueprint

pages_blueprint = Blueprint(
    "pages", "measurements", static_folder="static", static_url_path="/static/"
)


DAY_REGEXP = re.compile(r"^\d{4}\-[0-1]\d\-[0-3]\d$")


@pages_blueprint.route("/")
def index():
    """TODO
    ---
    responses:
      '200':
        description: TODO
    """
    return render_template("index.html")


@pages_blueprint.route("/css/bootstrap.min.css")
def serve_bootstrap_css():
    """TODO
    ---
    responses:
      '200':
        description: TODO
    """
    tpl = "/usr/%s/nodejs/bootstrap/dist/css/bootstrap.min.css"
    try:
        return send_file(tpl % "lib")
    except FileNotFoundError:
        return send_file(tpl % "share")


@pages_blueprint.route("/css/bootstrap.min.js")
def serve_bootstrap():
    """TODO
    ---
    responses:
      '200':
        description: TODO
    """
    tpl = "/usr/%s/nodejs/bootstrap/dist/js/bootstrap.min.js"
    try:
        return send_file(tpl % "lib")
    except FileNotFoundError:
        return send_file(tpl % "share")


@pages_blueprint.route("/stats")
def stats():
    """TODO
    ---
    responses:
      '200':
        description: TODO
    """
    return redirect("https://explorer.ooni.org", 301)


@pages_blueprint.route("/files")
def files_index():
    """TODO
    ---
    responses:
      '200':
        description: TODO
    """
    return redirect("https://explorer.ooni.org/search", 301)


@pages_blueprint.route("/files/by_date")
def files_by_date():
    """TODO
    ---
    responses:
      '200':
        description: TODO
    """
    return redirect("https://explorer.ooni.org/search", 301)


@pages_blueprint.route("/files/by_date/<date>")
def files_on_date(date):
    """TODO
    ---
    responses:
      '200':
        description: TODO
    """
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
    """TODO
    ---
    responses:
      '200':
        description: TODO
    """
    return redirect("https://explorer.ooni.org/search", 301)


@pages_blueprint.route("/files/by_country/<country_code>")
def files_in_country(country_code):
    """TODO
    ---
    responses:
      '200':
        description: TODO
    """
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


# These two are needed to avoid breaking older URLs
@pages_blueprint.route("/<date>/<report_file>")
def backward_compatible_download(date, report_file):
    """TODO
    ---
    responses:
      '200':
        description: TODO
    """
    if DAY_REGEXP.match(date) and report_file.endswith(".json"):
        # XXX maybe do some extra validation on report_file
        return redirect("/files/download/%s" % report_file)
    raise NotFound


@pages_blueprint.route("/<date>")
def backward_compatible_by_date(date):
    """TODO
    ---
    responses:
      '200':
        description: TODO
    """
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
