from __future__ import absolute_import

import datetime
import logging
import os
import re
import sys

from flask import Flask, json

from flask_cors import CORS  # debdeps: python3-flask-cors

# python3-flask-cors has unnecessary dependencies :-/
from ooniapi.rate_limit_quotas import FlaskLimiter

try:
    from systemd.journal import JournalHandler  # debdeps: python3-systemd

    enable_journal = True
except ImportError:  # pragma: no cover
    enable_journal = False

from flasgger import Swagger

from decimal import Decimal
from ooniapi.database import init_postgres_db, init_clickhouse_db

APP_DIR = os.path.dirname(__file__)


class FlaskJSONEncoder(json.JSONEncoder):
    # Special JSON encoder that handles dates
    def default(self, o):
        if isinstance(o, datetime.datetime):
            if o.tzinfo:
                # eg: '2015-09-25T23:14:42.588601+00:00'
                return o.isoformat("T")
            else:
                # No timezone present - assume UTC.
                # eg: '2015-09-25T23:14:42.588601Z'
                return o.isoformat("T") + "Z"

        if isinstance(o, datetime.date):
            return o.isoformat()

        if isinstance(o, Decimal):
            return float(o)

        if isinstance(o, set):
            return list(o)

        return json.JSONEncoder.default(self, o)


def validate_conf(app, conffile):
    """Fail early if the app configuration looks incorrect"""
    conf_keys = (
        "BASE_URL",
        "COLLECTORS",
        "DATABASE_STATEMENT_TIMEOUT",
        "DATABASE_URI_RO",
        "CLICKHOUSE_HOST",
        "USE_CLICKHOUSE",
        "GITHUB_ORIGIN_REPO",
        "GITHUB_PUSH_REPO",
        "GITHUB_TOKEN",
        "GITHUB_USER",
        "GITHUB_WORKDIR",
        "JWT_ENCRYPTION_KEY",
        "LOGIN_BASE_URL",
        "MAIL_PASSWORD",
        "MAIL_PORT",
        "MAIL_SERVER",
        "MAIL_SOURCE_ADDRESS",
        "MAIL_USERNAME",
        "MAIL_USE_SSL",
        "MSMT_SPOOL_DIR",
        "PSIPHON_CONFFILE",
        "S3_ACCESS_KEY_ID",
        "S3_ENDPOINT_URL",
        "S3_SECRET_ACCESS_KEY",
        "S3_SESSION_TOKEN",
        "TOR_TARGETS_CONFFILE",
    )
    for k in conf_keys:
        if k not in app.config:
            app.logger.error(f"Missing configuration key {k} in {conffile}")
            # exit with 4 to terminate gunicorn
            sys.exit(4)


def parse_cors_origins(app):
    out = []
    for i in app.config["CORS_URLS"]:
        if i.startswith("^"):
            i = re.compile(i)
        out.append(i)
    app.config["CORS_URLS"] = out


def init_app(app, testmode=False):
    # Load configurations defaults from ooniapi/config.py
    # and then from the file pointed by CONF
    # (defaults to /etc/ooni/api.conf)
    log = logging.getLogger("ooni-api")
    app.config.from_object("ooniapi.config")
    conffile = os.getenv("CONF", "/etc/ooni/api.conf")
    if enable_journal:
        log.addHandler(JournalHandler(SYSLOG_IDENTIFIER="ooni-api"))
    log.setLevel(logging.DEBUG)
    log.info(f"Starting OONI API. Loading conf from {conffile}")
    app.config.from_pyfile(conffile)
    validate_conf(app, conffile)
    #parse_cors_origins(app)
    # TODO: fix logging
    log.info("Configuration loaded")
    CORS(app)


def create_app(*args, testmode=False, **kw):
    from ooniapi import views

    app = Flask(__name__)
    app.json_encoder = FlaskJSONEncoder
    log = app.logger

    # Order matters
    init_app(app, testmode=testmode)

    if app.config["DATABASE_URI_RO"]:
        init_postgres_db(app)  # pragma: no cover
    if app.config["USE_CLICKHOUSE"]:
        init_clickhouse_db(app)

    # Setup rate limiting
    # NOTE: the limits apply per-process. The number of processes is set in:
    # https://github.com/ooni/sysadmin/blob/master/ansible/roles/ooni-measurements/tasks/main.yml
    limits = dict(
        ipaddr_per_month=60000,
        token_per_month=6000,
        ipaddr_per_week=20000,
        token_per_week=2000,
        ipaddr_per_day=4000,
        token_per_day=500,
    )
    # Whitelist Prometheus and AMS Explorer
    # TODO: move addrs to an external config file /etc/ooniapi.conf ?
    whitelist = ["37.218.245.43", "37.218.242.149"]
    unmetered_pages = ["/", "/health", "/report*"]
    app.limiter = FlaskLimiter(
        limits=limits,
        app=app,
        whitelisted_ipaddrs=whitelist,
        unmetered_pages=unmetered_pages,
    )

    Swagger(app, parse=True)

    # FIXME
    views.register(app)

    # why is it `teardown_appcontext` and not `teardown_request` ?...
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        if hasattr(app, "db_session"):
            app.db_session.remove()  # pragma: no cover

    @app.route("/health")
    def health():
        """Health check
        ---
        responses:
          '200':
            description: Status
        """
        return "UP"
        # TODO: ping database?
        # option httpchk GET /check
        # http-check expect string success

    if False:
        log.debug("Routes:")
        for r in app.url_map.iter_rules():
            log.debug(f" {r.match} ")
        log.debug("----")

    return app
