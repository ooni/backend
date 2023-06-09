"""
OONIRun link management

https://github.com/ooni/spec/blob/master/backends/bk-005-ooni-run-v2.md
"""

from datetime import datetime
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
from ooniapi.utils import nocachejson, cachedjson, generate_random_intuid

log: logging.Logger

# The table creation for CI purposes is in tests/integ/clickhouse_1_schema.sql

oonirun_blueprint = Blueprint("oonirun_api", "oonirun")


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
      - name: id or null
        description: used to create a new version of an existing OONIRun
        in: query
        type: string
        required: false
    responses:
      '200':
        schema:
          type: object
          properties:
            v:
              type: integer
              description: response format version
            id:
              type: integer
    """
    global log
    log = current_app.logger
    log.debug("creating oonirun")
    account_id = get_account_id_or_raise()
    descriptor = request.json
    assert descriptor
    oonirun_id_raw = request.args.get("id")
    for i in ("name", "description", "author"):
        val = descriptor.get(i, "") or ""
        # Must be present and non empty
        if not val:
            return jerror(f"Field {i} required")

    sql_ins = (
        "INSERT INTO oonirun (id, descriptor, creator_account_id, "
        "name, author, description) VALUES"
    )
    if oonirun_id_raw is None:
        # new ID
        oonirun_id = generate_random_intuid(current_app)
    else:
        # We need a previous oonirun belonging to the same user
        oonirun_id = int(oonirun_id_raw)
        query = """SELECT 1
        FROM oonirun
        WHERE id = %(oonirun_id)s
        AND creator_account_id = %(account_id)s
        LIMIT 1
        """
        query_params = dict(account_id=account_id, oonirun_id=oonirun_id)
        q = query_click(query, query_params)
        if not len(q):
            return jerror(f"OONIRun descriptor not found")

    desc_s = json.dumps(descriptor)
    row = dict(
        id=oonirun_id,
        descriptor=desc_s,
        creator_account_id=account_id,
        name=descriptor["name"],
        author=descriptor["author"],
        description=descriptor["description"],
    )
    log.info(f"Creating oonirun {oonirun_id} {row}")
    insert_click(sql_ins, [row])
    optimize_table("oonirun")
    return nocachejson(v=1, id=oonirun_id)


@oonirun_blueprint.route("/api/_/ooni_run/archive/<int:oonirun_id>", methods=["POST"])
@role_required(["admin", "user"])
def archive_oonirun(oonirun_id) -> Response:
    """Archive an OONIRun descriptor and all its past versions.
    ---
    parameters:
      - name: oonirun_id
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
    log.debug(f"archive oonirun {oonirun_id}")
    account_id = get_account_id_or_raise()

    # Async mutation on all servers
    query = "ALTER TABLE oonirun UPDATE archived = 1 WHERE id = %(oonirun_id)s"
    if get_client_role() != "admin":
        query += " AND creator_account_id = %(account_id)s"

    query_params = dict(oonirun_id=oonirun_id, account_id=account_id)
    raw_query(query, query_params)
    optimize_table("oonirun")
    return nocachejson(v=1)


@metrics.timer("fetch_oonirun_descriptor")
@oonirun_blueprint.route("/api/_/ooni_run/fetch/<int:oonirun_id>", methods=["GET"])
def fetch_oonirun_descriptor(oonirun_id) -> Response:
    """Fetch OONIRun descriptor by creation time or the newest one
    ---
    parameters:
      - name: oonirun_id
        in: path
        type: integer
        required: true
      - name: creation_time or null
        in: query
        type: string
        example: "2023-06-02T12:33:43Z"
        required: false
    responses:
      '200':
        description: OONIRun metadata and descriptor
        schema:
          type: object
          properties:
            v:
              type: integer
              description: response format version
            creation_time:
              type: string
              description: descriptor creation time
            descriptor:
              type: object
              description: descriptor data
    """
    global log
    log = current_app.logger
    log.debug("fetching oonirun")
    creation_time = request.args.get("creation_time")
    if creation_time is None:
        # Fetch latest version
        query_params = dict(oonirun_id=oonirun_id)
        creation_time_filter = ""
    else:
        ct = datetime.strptime(creation_time, "%Y-%m-%dT%H:%M:%SZ")
        query_params = dict(oonirun_id=oonirun_id, creation_time=ct)
        creation_time_filter = "AND creation_time = %(creation_time)s"

    query = f"""SELECT creation_time, descriptor
        FROM oonirun
        WHERE id = %(oonirun_id)s {creation_time_filter}
        ORDER BY creation_time DESC
        LIMIT 1
    """
    q = query_click(query, query_params)
    if not len(q):
        return jerror("oonirun descriptor not found")

    r = q[0]
    desc = json.loads(r["descriptor"])
    return cachedjson("1h", descriptor=desc, creation_time=r["creation_time"], v=1)


@oonirun_blueprint.route("/api/_/ooni_run/list", methods=["GET"])
def list_oonirun_descriptors() -> Response:
    """List OONIRun descriptors
    ---
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
                  id:
                    type: string
                    description: descriptor ID
                  creation_time:
                    type: string
                    description: descriptor creation time
                  archived:
                    type: boolean
                  name:
                    type: string
                  description:
                    type: string
                  author:
                    type: string
                  mine:
                    type: boolean
                    description: the descriptor belongs to the logged-in user. Optional.
    """
    global log
    log = current_app.logger
    log.debug("list oonirun")
    account_id = get_account_id_or_none()
    cols = [
        "id",
        "creation_time",
        "archived",
        "name",
        "description",
        "author",
    ]
    if account_id is not None:
        cols.append("creator_account_id = %(account_id)s AS mine")

    query = f"""SELECT {", ".join(cols)}
    FROM oonirun
    ORDER BY id, creation_time
    """
    query_params = dict(account_id=account_id)
    q = query_click(query, query_params)
    return nocachejson(v=1, descriptors=q)
