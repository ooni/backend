from __future__ import absolute_import

import datetime
import logging
import os
import re
import sys
from collections import deque

from flask import Flask, json

from flask_cors import CORS  # debdeps: python3-flask-cors

import geoip2.database  # debdeps: python3-geoip2

# python3-flask-cors has unnecessary dependencies :-/
from ooniapi.rate_limit_quotas import FlaskLimiter

try:
    from systemd.journal import JournalHandler  # debdeps: python3-systemd

    enable_journal = True
except ImportError:  # pragma: no cover
    enable_journal = False

from flasgger import Swagger

from decimal import Decimal
from ooniapi.database import init_clickhouse_db

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
        "CLICKHOUSE_URL",
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


def setup_collectors_ring(config):
    """Create round-robin ring of collectors excluding localhost"""
    lh = config.get("HOSTNAME")
    if not lh:
        import socket

        lh = socket.gethostname()

    colls = config["COLLECTORS"]
    c = deque(sorted(set(colls)))
    if lh in c:
        while c[0] != lh:
            c.rotate()
        c.popleft()
        config["OTHER_COLLECTORS"] = c

    else:
        print(f"{lh} not found in collectors {colls}")
        config["OTHER_COLLECTORS"] = deque(c)


def setup_logging(log):
    if enable_journal:
        root_logger = log.root
        h = JournalHandler(SYSLOG_IDENTIFIER="ooni-api")
        formatter = logging.Formatter("%(levelname)s %(message)s")
        h.setFormatter(formatter)
        root_logger.addHandler(h)
        root_logger.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.DEBUG)
        logging.basicConfig(format="%(message)s")


def load_geoip_db(log, app):
    log.debug("Loading GeoIP DBs")
    ccfn = app.config.get("GEOIP_CC_DB")
    asnfn = app.config.get("GEOIP_ASN_DB")
    try:
        app.geoip_cc_reader = geoip2.database.Reader(ccfn)
        app.geoip_asn_reader = geoip2.database.Reader(asnfn)
    except Exception:
        log.error("Failed to load geoip DBs at", ccfn, asnfn, exc_info=True)


def init_app(app, testmode=False):
    # Load configurations defaults from ooniapi/config.py
    # and then from the file pointed by CONF
    # (defaults to /etc/ooni/api.conf)
    log = logging.getLogger("ooni-api")
    conffile = os.getenv("CONF", "/etc/ooni/api.conf")
    setup_logging(log)

    log.info(f"Starting OONI API. Loading conf from {conffile}")
    app.config.from_object("ooniapi.config")
    app.config.from_pyfile(conffile)
    validate_conf(app, conffile)
    # parse_cors_origins(app)
    setup_collectors_ring(app.config)

    log.info("Configuration loaded")
    load_geoip_db(log, app)
    CORS(app)


def create_app(*args, testmode=False, **kw):
    from ooniapi import views

    app = Flask(__name__)
    app.json_encoder = FlaskJSONEncoder
    log = app.logger

    # Order matters
    init_app(app, testmode=testmode)

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
