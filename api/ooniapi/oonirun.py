"""
OONIRun link management

https://github.com/ooni/spec/blob/master/backends/bk-005-ooni-run-v2.md
"""

from datetime import datetime
from typing import Dict, Any
import json
import logging

from flask import Blueprint, current_app, request, Response

from ooniapi.auth import (
    role_required,
    get_client_role,
    get_account_id_or_raise,
    get_account_id_or_none,
)
from ooniapi.config import metrics
from ooniapi.database import query_click, optimize_table, insert_click, raw_query
from ooniapi.errors import jerror
from ooniapi.urlparams import commasplit
from ooniapi.utils import nocachejson, cachedjson, generate_random_intuid

from ooniapi.errors import InvalidRequest, EmptyTranslation

log: logging.Logger

# The table creation for CI purposes is in tests/integ/clickhouse_1_schema.sql

oonirun_blueprint = Blueprint("oonirun_api", "oonirun")


def from_timestamp(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ")


def to_timestamp(t: datetime) -> str:
    ts = t.strftime("%Y-%m-%dT%H:%M:%S.%f")
    return ts[:-3] + "Z"


def to_db_date(t: datetime) -> str:
    return t.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def validate_translations_not_empty(descriptor: dict) -> None:
    for f in ("description_intl", "short_description_intl", "name_intl"):
        d = descriptor.get(f, {}) or {}
        for lang, txn in d.items():
            if txn == "":
                raise EmptyTranslation()


def compare_descriptors(previous_descriptor: dict, descriptor: dict) -> bool:
    """Return True if anything other than the localized fields changed"""
    if previous_descriptor["nettests"] != descriptor["nettests"]:
        return True
    if previous_descriptor["author"] != descriptor["author"]:
        return True
    if previous_descriptor["icon"] != descriptor["icon"]:
        return True

    return False


@oonirun_blueprint.route("/api/_/ooni_run/create", methods=["POST"])
@role_required(["admin", "user"])
def create_oonirun() -> Response:
    """Create a new oonirun link or a new version for an existing one.
    ---
    parameters:
      - in: body
        required: true
        description: OONIRun descriptor content
        schema:
          type: object
      #- id: oonirun id or null
      #  description: used to create a new version of an existing OONIRun
      #  in: query
      #  type: string
      #  required: false
    responses:
      '200':
        schema:
          type: object
          properties:
            ooni_run_link_id:
              type: integer
            v:
              type: integer
              description: response format version
    """
    global log
    log = current_app.logger
    log.debug("creating oonirun")
    account_id = get_account_id_or_raise()
    descriptor = request.json
    assert descriptor
    ooni_run_link_id_raw = request.args.get("ooni_run_link_id")

    if descriptor.get("name", "") == "":
        log.info("'name' field empty")
        return jerror("'name' field must not be empty")

    validate_translations_not_empty(descriptor)

    desc_s = json.dumps(descriptor)

    now = datetime.utcnow()
    now_ts = to_timestamp(now)

    if ooni_run_link_id_raw is None:
        # Generate new ID
        ooni_run_link_id = generate_random_intuid(current_app)
        increase_descriptor_creation_time = True

    else:
        # We need a previous oonirun belonging to the same user
        ooni_run_link_id = int(ooni_run_link_id_raw)
        query = """SELECT descriptor, descriptor_creation_time
        FROM oonirun
        WHERE ooni_run_link_id = %(ooni_run_link_id)s AND creator_account_id = %(account_id)s
        ORDER BY descriptor_creation_time DESC
        LIMIT 1
        """
        query_params = dict(account_id=account_id, ooni_run_link_id=ooni_run_link_id)
        q = query_click(query, query_params)
        if not len(q):
            return jerror("OONIRun descriptor not found")

        # A descriptor is already in the database and belongs to account_id
        # Check if we need to update the descriptor timestamp or only txn
        previous_descriptor = json.loads(q[0]["descriptor"])
        increase_descriptor_creation_time = compare_descriptors(
            previous_descriptor, descriptor
        )
        del previous_descriptor

        previous_descriptor_creation_time = q[0]["descriptor_creation_time"]

    if increase_descriptor_creation_time:
        descriptor_creation_time = now
    else:
        descriptor_creation_time = previous_descriptor_creation_time

    row = dict(
        author=descriptor["author"],
        creator_account_id=account_id,
        descriptor=desc_s,
        descriptor_creation_time=descriptor_creation_time,
        ooni_run_link_id=ooni_run_link_id,
        name=descriptor["name"],
        short_description=descriptor.get("short_description", ""),
        translation_creation_time=now,
        icon=descriptor.get("icon", ""),
    )
    log.info(
        f"Inserting oonirun {ooni_run_link_id} {increase_descriptor_creation_time} {row}"
    )
    sql_ins = """INSERT INTO oonirun (ooni_run_link_id, descriptor, creator_account_id,
        author, descriptor_creation_time, translation_creation_time, name,
        short_description, icon) VALUES"""
    insert_click(sql_ins, [row])

    optimize_table("oonirun")
    return nocachejson(v=1, ooni_run_link_id=ooni_run_link_id)


@oonirun_blueprint.route(
    "/api/_/ooni_run/archive/<int:ooni_run_link_id>", methods=["POST"]
)
@role_required(["admin", "user"])
def archive_oonirun(ooni_run_link_id) -> Response:
    """Archive an OONIRun descriptor and all its past versions.
    ---
    parameters:
      - name: ooni_run_link_id
        in: path
        type: integer
        required: true
    responses:
      '200':
        schema:
          type: object
          properties:
            v:
              type: integer
              description: response format version
    """
    global log
    log = current_app.logger
    log.debug(f"archive oonirun {ooni_run_link_id}")
    account_id = get_account_id_or_raise()

    # Async mutation on all servers
    query = "ALTER TABLE oonirun UPDATE archived = 1 WHERE ooni_run_link_id = %(ooni_run_link_id)s"
    if get_client_role() != "admin":
        query += " AND creator_account_id = %(account_id)s"

    query_params = dict(ooni_run_link_id=ooni_run_link_id, account_id=account_id)
    raw_query(query, query_params)
    optimize_table("oonirun")
    return nocachejson(v=1)


@metrics.timer("fetch_oonirun_descriptor")
@oonirun_blueprint.route(
    "/api/_/ooni_run/fetch/<int:ooni_run_link_id>", methods=["GET"]
)
def fetch_oonirun_descriptor(ooni_run_link_id) -> Response:
    """Fetch OONIRun descriptor by creation time or the newest one
    ---
    parameters:
      - name: ooni_run_link_id
        in: path
        type: integer
        required: true
      - name: creation_time or null
        in: query
        type: string
        example: "2023-06-02T12:33:43.123Z"
        required: false
    responses:
      '200':
        description: OONIRun metadata and descriptor
        schema:
          type: object
          properties:
            archived:
              type: boolean
              description: the descriptor is archived
            descriptor:
              type: object
              description: descriptor data
            descriptor_creation_time:
              type: string
              description: descriptor creation time
            mine:
              type: boolean
              description: the descriptor belongs to the logged-in user. Optional.
            translation_creation_time:
              type: string
              description: translation creation time
            v:
              type: integer
              description: response format version
    """
    # Return the latest version of the translations
    global log
    log = current_app.logger
    log.debug("fetching oonirun")
    descriptor_creation_time = request.args.get("creation_time")
    account_id = get_account_id_or_none()
    query_params = dict(ooni_run_link_id=ooni_run_link_id, account_id=account_id)
    if descriptor_creation_time is None:
        # Fetch latest version
        creation_time_filter = ""
    else:
        ct = from_timestamp(descriptor_creation_time)
        query_params["dct"] = to_db_date(ct)
        creation_time_filter = "AND descriptor_creation_time = %(dct)s"

    query = f"""SELECT
        descriptor_creation_time, translation_creation_time, descriptor,
        archived, creator_account_id = %(account_id)s AS mine
        FROM oonirun
        WHERE ooni_run_link_id = %(ooni_run_link_id)s {creation_time_filter}
        ORDER BY descriptor_creation_time DESC
        LIMIT 1
    """
    q = query_click(query, query_params)
    if not len(q):
        return jerror("oonirun descriptor not found")

    r = q[0]
    descriptor = json.loads(r["descriptor"])

    kw = dict(
        archived=bool(r["archived"]),
        descriptor=descriptor,
        descriptor_creation_time=r["descriptor_creation_time"],
        mine=bool(r["mine"]),
        translation_creation_time=r["translation_creation_time"],
        v=1,
    )
    return cachedjson("1h", **kw)


@oonirun_blueprint.route("/api/_/ooni_run/list", methods=["GET"])
def list_oonirun_descriptors() -> Response:
    """List OONIRun descriptors
    ---
    parameters:
      - name: ooni_run_link_ids
        in: query
        type: string
        description: OONIRun descriptors comma separated
      - name: only_latest
        in: query
        type: boolean
      - name: only_mine
        in: query
        type: boolean
      - name: include_archived
        in: query
        type: boolean
    responses:
      '200':
        description: OONIRun metadata and descriptor
        schema:
          type: object
          properties:
            v:
              type: integer
              description: response format version
            descriptors:
              type: array
              description: OONIRun descriptors metadata
              items:
                type: object
                properties:
                  ooni_run_link_id:
                    type: string
                    description: descriptor ID
                  archived:
                    type: boolean
                  author:
                    type: string
                  creation_time:
                    type: string
                    description: descriptor creation time
                  mine:
                    type: boolean
                    description: the descriptor belongs to the logged-in user. Optional.
                  name:
                    type: string
                  short_description:
                    type: string
                  icon:
                    type: string
    """
    global log
    log = current_app.logger
    log.debug("list oonirun")
    account_id = get_account_id_or_none()

    query_params: Dict[str, Any] = dict(account_id=account_id)
    try:
        filters = []
        only_latest = bool(request.args.get("only_latest"))
        if only_latest:
            filters.append(
                """
            (ooni_run_link_id, translation_creation_time) IN (
                SELECT ooni_run_link_id,
                MAX(translation_creation_time) AS translation_creation_time
                FROM oonirun
                GROUP BY ooni_run_link_id
            )"""
            )

        include_archived = bool(request.args.get("include_archived"))
        if not include_archived:
            filters.append(
                """
            archived = 0
            """
            )

        only_mine = bool(request.args.get("only_mine"))
        if only_mine:
            filters.append("creator_account_id = %(account_id)s")

        ids_s = request.args.get("ooni_run_link_ids")
        if ids_s:
            ids = commasplit(ids_s)
            filters.append("ooni_run_link_id IN %(ids)s")
            query_params["ids"] = ids

        # name_match = request.args.get("name_match", "").strip()
        # if name_match:
        #     filters.append("ooni_run_link_id IN %(ids)s")
        #     query_params["ids"] = ids

    except Exception as e:
        log.debug(f"list_oonirun_descriptors: invalid parameter. {e}")
        return jerror("Incorrect parameter used")

    if account_id is None:
        mine_col = "0"
    else:
        mine_col = "creator_account_id = %(account_id)s"

    if filters:
        fil = " WHERE " + " AND ".join(filters)
    else:
        fil = ""

    query = f"""SELECT archived, author, ooni_run_link_id, icon, descriptor_creation_time,
    translation_creation_time, {mine_col} AS mine, name, short_description
    FROM oonirun
    {fil}
    ORDER BY descriptor_creation_time, translation_creation_time
    """
    descriptors = list(query_click(query, query_params))
    for d in descriptors:
        d["mine"] = bool(d["mine"])
        d["archived"] = bool(d["archived"])
    log.debug(f"Returning {len(descriptors)} descriptor[s]")
    return nocachejson(v=1, descriptors=descriptors)
