"""
OONI API - various pages e.g.
    /  <index>
    /files

    Redirects:
    /stats
    /files
    /files/by_date
"""


import re
from datetime import timedelta, datetime

from flask import Blueprint, render_template, redirect, send_file, make_response

from werkzeug.exceptions import BadRequest, NotFound
from werkzeug.wrappers import Response  # why not flask.Response?

# Exporting it
from .docs import api_docs_blueprint

pages_blueprint = Blueprint(
    "pages", "measurements", static_folder="static", static_url_path="/static/"
)


DAY_REGEXP = re.compile(r"^\d{4}\-[0-1]\d\-[0-3]\d$")


@pages_blueprint.route("/")
def index():
    """Landing page
    ---
    responses:
      '200':
        description: TODO
    """
    return render_template("index.html")


@pages_blueprint.route("/stats")
def stats() -> Response:
    """TODO
    ---
    responses:
      '200':
        description: TODO
    """
    return redirect("https://explorer.ooni.org", 301)


@pages_blueprint.route("/files")
def files_index() -> Response:
    """TODO
    ---
    responses:
      '200':
        description: TODO
    """
    return redirect("https://explorer.ooni.org/search", 301)


@pages_blueprint.route("/files/by_date")
def files_by_date() -> Response:
    """TODO
    ---
    responses:
      '200':
        description: TODO
    """
    return redirect("https://explorer.ooni.org/search", 301)


@pages_blueprint.route("/files/by_date/<date>")
def files_on_date(date) -> Response:
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
def files_by_country() -> Response:
    """TODO
    ---
    responses:
      '200':
        description: TODO
    """
    return redirect("https://explorer.ooni.org/search", 301)


@pages_blueprint.route("/files/by_country/<country_code>")
def files_in_country(country_code) -> Response:
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


@pages_blueprint.route("/robots.txt")
def robots_txt() -> Response:
    """Robots.txt
    ---
    responses:
      '200':
        description: robots.txt content
    """
    txt = """
User-agent: *
Disallow: /api/_
Disallow: /api/v1/aggregation
Disallow: /api/v1/test-list/urls
Disallow: /api/v1/torsf_stats
Disallow: /files
Disallow: /stats
Disallow: /201
Disallow: /202
Crawl-delay: 300
"""
    resp = make_response(txt)
    resp.headers["Content-type"] = "text/plain"
    resp.cache_control.max_age = 86400
    return resp


# These two are needed to avoid breaking older URLs
@pages_blueprint.route("/<date>/<report_file>")
def backward_compatible_download(date, report_file) -> Response:
    """Legacy entry point
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
def backward_compatible_by_date(date) -> Response:
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
