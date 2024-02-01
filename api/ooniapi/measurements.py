"""
Measurements API
The routes are mounted under /api
"""

from datetime import datetime, timedelta
from dateutil.parser import parse as parse_date
from pathlib import Path
from typing import Optional, Any, Dict
import gzip
import json
import logging
import math
import time

import ujson  # debdeps: python3-ujson
import urllib3  # debdeps: python3-urllib3

from flask import current_app, request, make_response, abort, redirect, Response
from flask.json import jsonify
from werkzeug.exceptions import HTTPException, BadRequest

# debdeps: python3-sqlalchemy
from sqlalchemy import and_, text, select, sql, column
from sqlalchemy.exc import OperationalError
from psycopg2.extensions import QueryCanceledError  # debdeps: python3-psycopg2

from urllib.request import urlopen
from urllib.parse import urljoin, urlencode

from ooniapi.auth import role_required, get_account_id_or_none
from ooniapi.config import metrics
from ooniapi.utils import cachedjson, nocachejson, jerror
from ooniapi.database import query_click, query_click_one_row
from ooniapi.urlparams import (
    param_asn,
    param_bool,
    param_commasplit,
    param_date,
    param_input_or_none,
    param_report_id,
    param_report_id_or_none,
    param_measurement_uid,
)

from flask import Blueprint

api_msm_blueprint = Blueprint("msm_api", "measurements")

FASTPATH_MSM_ID_PREFIX = "temp-fid-"
FASTPATH_SERVER = "fastpath.ooni.nu"
FASTPATH_PORT = 8000

log = logging.getLogger()

urllib_pool = urllib3.PoolManager()

# type hints
ostr = Optional[str]


# # measurement feedback

from ooniapi.database import insert_click


"""
CREATE TABLE msmt_feedback
(
    `measurement_uid` String,
    `account_id` String,
    `status` String,
    `update_time` DateTime64(3) MATERIALIZED now64()
)
ENGINE = ReplacingMergeTree
ORDER BY (measurement_uid, account_id)
SETTINGS index_granularity = 4
"""

valid_feedback_status = [
    "blocked",
    "blocked.blockpage",
    "blocked.blockpage.http",
    "blocked.blockpage.dns",
    "blocked.blockpage.server_side",
    "blocked.blockpage.server_side.captcha",
    "blocked.dns",
    "blocked.dns.inconsistent",
    "blocked.dns.nxdomain",
    "blocked.tcp",
    "blocked.tls",
    "ok",
    "down",
    "down.unreachable",
    "down.misconfigured",
]


@api_msm_blueprint.route("/_/measurement_feedback/<measurement_uid>")
@metrics.timer("get_msmt_feedback")
def get_msmt_feedback(measurement_uid) -> Response:
    """Get measurement for the curred logged user for a given measurement
    ---
    produces:
      - application/json
    parameters:
      - name: measurement_uid
        in: path
        type: string
        description: Measurement ID
        minLength: 5
        required: true
    responses:
      200:
        description: status summary
    """
    account_id = get_account_id_or_none()
    query = """SELECT status, account_id = :aid AS is_mine, count() AS cnt
        FROM msmt_feedback FINAL
        WHERE measurement_uid = :muid
        GROUP BY status, is_mine
    """
    qp = dict(aid=account_id, muid=measurement_uid)
    rows = query_click(sql.text(query), qp)
    out: Dict[str, Any] = dict(summary={})
    for row in rows:
        status = row["status"]
        if row["is_mine"]:
            out["user_feedback"] = status
        out["summary"][status] = out["summary"].get(status, 0) + row["cnt"]

    return cachedjson("0s", **out)


@api_msm_blueprint.route("/_/measurement_feedback", methods=["POST"])
@metrics.timer("submit_msmt_feedback")
@role_required(["admin", "user"])
def submit_msmt_feedback() -> Response:
    """Submit measurement feedback. Only for registered users.
    ---
    produces:
      - application/json
    consumes:
      - application/json
    parameters:
      - in: body
        required: true
        schema:
          type: object
          properties:
            measurement_uid:
              type: string
              description: Measurement ID
            status:
              type: string
              description: Measurement status
              minLength: 2
    responses:
      200:
        description: Submission or update accepted
    """

    def jparam(name):
        return request.json.get(name, "").strip()

    account_id = get_account_id_or_none()
    status = jparam("status")
    if status not in valid_feedback_status:
        return jerror("Invalid status")
    measurement_uid = jparam("measurement_uid")

    query = "INSERT INTO msmt_feedback (measurement_uid, account_id, status) VALUES"
    query_params = [measurement_uid, account_id, status]
    insert_click(query, [query_params])
    return cachedjson("0s")
