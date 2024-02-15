"""
OONIRun link management

https://github.com/ooni/spec/blob/master/backends/bk-005-ooni-run-v2.md
"""

from datetime import datetime
from os import urandom
from sys import byteorder
from typing import Dict, Any, List, Optional
import json
import logging

from fastapi import APIRouter, Depends, Query, HTTPException, Header
from pydantic import BaseModel, constr
from typing_extensions import Annotated

from ..config import settings, metrics

from ..utils import (
    commasplit,
    query_click,
    optimize_table,
    insert_click,
    raw_query,
    role_required,
    get_client_role,
    get_account_id_or_raise,
    get_account_id_or_none,
)
from ..dependencies import ClickhouseClient, get_clickhouse_client


log = logging.getLogger(__name__)

# The table creation for CI purposes is in tests/integ/clickhouse_1_schema.sql

router = APIRouter()


def from_timestamp(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ")


def to_timestamp(t: datetime) -> str:
    ts = t.strftime("%Y-%m-%dT%H:%M:%S.%f")
    return ts[:-3] + "Z"


def to_db_date(t: datetime) -> str:
    return t.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


class OONIRunCreated(BaseModel):
    ooni_run_link_id: int
    v: int


class OONIRunDescriptor(BaseModel):
    name: Annotated[str, constr(min_length=1)]
    name_intl: Optional[Dict[str, Annotated[str, constr(min_length=1)]]]
    short_description: Annotated[Optional[str], constr(min_length=1)]
    short_description_intl: Optional[Dict[str, Annotated[str, constr(min_length=1)]]]

    description: Annotated[Optional[str], constr(min_length=1)]
    description_intl: Optional[Dict[str, Annotated[str, constr(min_length=1)]]]
    icon: Optional[str]
    author: Optional[str]
    is_archived: Optional[bool]

    nettests: List[Dict]


def compare_descriptors(
    previous_descriptor: OONIRunDescriptor, descriptor: OONIRunDescriptor
) -> bool:
    """Return True if anything other than the localized fields changed"""
    if previous_descriptor.nettests != descriptor.nettests:
        return True
    if previous_descriptor.author != descriptor.author:
        return True
    if previous_descriptor.icon != descriptor.icon:
        return True

    return False


def generate_random_intuid() -> int:
    collector_id = 0
    randint = int.from_bytes(urandom(4), byteorder)
    return randint * 100 + collector_id


@router.post(
    "/api/_/ooni_run/create",
    tags=["oonirunv2"],
    dependencies=[Depends(role_required(["admin", "user"]))],
)
def create_oonirun(
    db: Annotated[ClickhouseClient, Depends(get_clickhouse_client)],
    descriptor: OONIRunDescriptor,
    ooni_run_link_id: Annotated[
        Optional[int],
        Query(description="ID of the OONI Run link ID being created"),
    ] = None,
    authorization: str = Header("authorization"),
) -> OONIRunCreated:
    """Create a new oonirun link or a new version for an existing one."""
    log.debug("creating oonirun")
    account_id = get_account_id_or_raise(authorization)
    assert descriptor

    now = datetime.utcnow()

    if ooni_run_link_id is None:
        # Generate new ID
        ooni_run_link_id = generate_random_intuid()
        descriptor_creation_time = now

    else:
        query = """SELECT descriptor, descriptor_creation_time
        FROM oonirun
        WHERE ooni_run_link_id = %(ooni_run_link_id)s AND creator_account_id = %(account_id)s
        ORDER BY descriptor_creation_time DESC
        LIMIT 1
        """
        query_params = dict(account_id=account_id, ooni_run_link_id=ooni_run_link_id)
        q = query_click(db, query, query_params)
        if not len(q):
            raise HTTPException(status_code=404, detail="OONIRun descriptor not found")

        # A descriptor is already in the database and belongs to account_id
        # Check if we need to update the descriptor timestamp or only txn
        previous_descriptor = OONIRunDescriptor(**json.loads(q[0]["descriptor"]))
        increase_descriptor_creation_time = compare_descriptors(
            previous_descriptor, descriptor
        )
        del previous_descriptor

        if increase_descriptor_creation_time:
            descriptor_creation_time = now
        else:
            descriptor_creation_time = q[0]["descriptor_creation_time"]

    row = dict(
        author=descriptor.author,
        creator_account_id=account_id,
        descriptor=json.dumps(descriptor),
        descriptor_creation_time=descriptor_creation_time,
        ooni_run_link_id=ooni_run_link_id,
        name=descriptor.name,
        short_description=descriptor.short_description or "",
        translation_creation_time=now,
        icon=descriptor.icon or "",
    )
    log.info(f"Inserting oonirun {ooni_run_link_id} {row}")
    sql_ins = """INSERT INTO oonirun (ooni_run_link_id, descriptor, creator_account_id,
        author, descriptor_creation_time, translation_creation_time, name,
        short_description, icon) VALUES"""
    insert_click(db, sql_ins, [row])

    optimize_table(db, "oonirun")
    return OONIRunCreated(v=1, ooni_run_link_id=ooni_run_link_id)


@router.post(
    "/api/_/ooni_run/archive/{ooni_run_link_id}",
    dependencies=[Depends(role_required(["admin", "user"]))],
    tags=["oonirun"],
)
def archive_oonirun(
    db: Annotated[ClickhouseClient, Depends(get_clickhouse_client)],
    ooni_run_link_id: int,
    authorization: str = Header("authorization"),
) -> OONIRunCreated:
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
    log.debug(f"archive oonirun {ooni_run_link_id}")
    account_id = get_account_id_or_raise(authorization)

    # Async mutation on all servers
    query = "ALTER TABLE oonirun UPDATE archived = 1 WHERE ooni_run_link_id = %(ooni_run_link_id)s"
    if get_client_role(authorization) != "admin":
        query += " AND creator_account_id = %(account_id)s"

    query_params = dict(ooni_run_link_id=ooni_run_link_id, account_id=account_id)
    raw_query(db, query, query_params)
    optimize_table(db, "oonirun")
    return OONIRunCreated(v=1, ooni_run_link_id=ooni_run_link_id)


class OONIRunDescriptorFetch(BaseModel):
    archived: bool
    descriptor: OONIRunDescriptor
    descriptor_creation_time: datetime
    mine: bool
    translation_creation_time: datetime
    v: int


@metrics.timer("fetch_oonirun_descriptor")
@router.get(
    "/api/_/ooni_run/fetch/{ooni_run_link_id}",
    tags=["oonirun"],
)
def fetch_oonirun_descriptor(
    db: Annotated[ClickhouseClient, Depends(get_clickhouse_client)],
    ooni_run_link_id: int,
    creation_time: Annotated[
        Optional[str],
        Query(
            description="filter by descriptor create time eg. `2023-06-02T12:33:43.123Z`"
        ),
    ] = None,
    authorization: str = Header("authorization"),
) -> OONIRunDescriptorFetch:
    """Fetch OONIRun descriptor by creation time or the newest one"""
    # Return the latest version of the translations
    log.debug("fetching oonirun")
    descriptor_creation_time = creation_time
    account_id = get_account_id_or_none(authorization)
    query_params: Dict[str, Any] = dict(
        ooni_run_link_id=ooni_run_link_id, account_id=account_id
    )
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
    q = query_click(db, query, query_params)
    if not len(q):
        raise HTTPException(status_code=404, detail="OONIRun descriptor not found")

    r = q[0]
    descriptor = json.loads(r["descriptor"])

    return OONIRunDescriptorFetch(
        archived=bool(r["archived"]),
        descriptor=descriptor,
        descriptor_creation_time=r["descriptor_creation_time"],
        mine=bool(r["mine"]),
        translation_creation_time=r["translation_creation_time"],
        v=1,
    )


class OONIRunDescriptorList(BaseModel):
    v: int
    descriptors: List[OONIRunDescriptorFetch]


@router.get("/api/_/ooni_run/list", tags=["oonirun"])
def list_oonirun_descriptors(
    db: Annotated[ClickhouseClient, Depends(get_clickhouse_client)],
    ooni_run_link_id: Annotated[
        Optional[str],
        Query(description="OONI Run descriptors comma separated"),
    ] = None,
    only_latest: Annotated[
        Optional[bool],
        Query(description="List only the latest versions"),
    ] = None,
    only_mine: Annotated[
        Optional[bool],
        Query(description="List only the my descriptors"),
    ] = None,
    include_archived: Annotated[
        Optional[bool],
        Query(description="List also archived descriptors"),
    ] = None,
    authorization: str = Header("authorization"),
) -> OONIRunDescriptorList:
    """List OONIRun descriptors"""
    log.debug("list oonirun")
    account_id = get_account_id_or_none(authorization)

    query_params: Dict[str, Any] = dict(account_id=account_id)
    try:
        filters = []
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
        if not include_archived:
            filters.append(
                """
            archived = 0
            """
            )
        if only_mine:
            filters.append("creator_account_id = %(account_id)s")

        ids_s = ooni_run_link_id
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
        raise HTTPException(status_code=400, detail="Incorrect parameter used")

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
    descriptors = list(query_click(db, query, query_params))
    for d in descriptors:
        d["mine"] = bool(d["mine"])
        d["archived"] = bool(d["archived"])
    log.debug(f"Returning {len(descriptors)} descriptor[s]")
    return OONIRunDescriptorList(v=1, descriptors=descriptors)
