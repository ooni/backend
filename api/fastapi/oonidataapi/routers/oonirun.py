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

import sqlalchemy

from ..config import metrics
from .. import models

from ..utils import (
    commasplit,
    role_required,
    get_client_role,
    get_account_id_or_raise,
    get_account_id_or_none,
)
from ..dependencies import get_postgresql_session, Session


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
    descriptor: OONIRunDescriptor,
    ooni_run_link_id: Annotated[
        Optional[int],
        Query(description="ID of the OONI Run link ID being created"),
    ] = None,
    authorization: str = Header("authorization"),
    db=Depends(get_postgresql_session),
) -> OONIRunCreated:
    """Create a new oonirun link or a new version for an existing one."""
    log.debug("creating oonirun")
    account_id = get_account_id_or_raise(authorization)
    assert descriptor

    now = datetime.utcnow()

    if ooni_run_link_id is not None:
        ooni_run_link = (
            db.query(models.OONIRunLink)
            .filter(ooni_run_link_id=ooni_run_link_id, creator_account_id=account_id)
            .order_by(descriptor_creation_time="desc")
            .first()
        )

        # A descriptor is already in the database and belongs to account_id
        # Check if we need to update the descriptor timestamp or only txn
        previous_descriptor = OONIRunDescriptor(**json.loads(ooni_run_link.descriptor))
        increase_descriptor_creation_time = compare_descriptors(
            previous_descriptor, descriptor
        )
        del previous_descriptor

        if increase_descriptor_creation_time:
            ooni_run_link.descriptor_creation_time = now
    else:
        ooni_run_link = models.OONIRunLink()
        ooni_run_link.ooni_run_link_id = generate_random_intuid()
        ooni_run_link.descriptor_creation_time = now

    ooni_run_link.descriptor = json.dumps(descriptor)
    ooni_run_link.author = descriptor.author
    ooni_run_link.name = descriptor.name

    ooni_run_link.icon = descriptor.icon or ""
    ooni_run_link.short_description = descriptor.short_description or ""

    ooni_run_link.creator_account_id = account_id
    ooni_run_link.translation_creation_time = now

    db.add(ooni_run_link)
    db.commit()
    db.refresh(ooni_run_link)

    return OONIRunCreated(v=1, ooni_run_link_id=ooni_run_link.ooni_run_link_id)


@router.post(
    "/api/_/ooni_run/archive/{ooni_run_link_id}",
    dependencies=[Depends(role_required(["admin", "user"]))],
    tags=["oonirun"],
)
def archive_oonirun(
    ooni_run_link_id: int,
    authorization: str = Header("authorization"),
    db=Depends(get_postgresql_session),
) -> OONIRunCreated:
    """Archive an OONIRun descriptor and all its past versions."""
    log.debug(f"archive oonirun {ooni_run_link_id}")
    account_id = get_account_id_or_raise(authorization)

    q = db.query(models.OONIRunLink).filter(ooni_run_link_id=ooni_run_link_id)
    if get_client_role(authorization) != "admin":
        q = q.filter(creator_account_id=account_id)

    q.update({"is_archived": True})
    db.commit()
    return OONIRunCreated(v=1, ooni_run_link_id=ooni_run_link_id)


class OONIRunDescriptorFetch(BaseModel):
    name: str
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
    ooni_run_link_id: int,
    creation_time: Annotated[
        Optional[str],
        Query(
            description="filter by descriptor create time eg. `2023-06-02T12:33:43.123Z`"
        ),
    ] = None,
    authorization: str = Header("authorization"),
    db=Depends(get_postgresql_session),
) -> OONIRunDescriptorFetch:
    """Fetch OONIRun descriptor by creation time or the newest one"""
    # Return the latest version of the translations
    log.debug("fetching oonirun")
    descriptor_creation_time = creation_time
    account_id = get_account_id_or_none(authorization)

    q = db.query(models.OONIRunLink).filter(ooni_run_link_id=ooni_run_link_id)
    if descriptor_creation_time is not None:
        q = q.filter(descriptor_creation_time=from_timestamp(descriptor_creation_time))
    oonirun_link = q.order_by(descriptor_creation_time="desc").first()

    descriptor = json.loads(oonirun_link["descriptor"])

    return OONIRunDescriptorFetch(
        name=oonirun_link.name,
        archived=bool(oonirun_link.is_archived),
        descriptor=descriptor,
        descriptor_creation_time=oonirun_link.descriptor_creation_time,
        mine=oonirun_link.account_id == account_id,
        translation_creation_time=oonirun_link.translation_creation_time,
        v=1,
    )


class OONIRunDescriptorList(BaseModel):
    v: int
    descriptors: List[OONIRunDescriptorFetch]


@router.get("/api/_/ooni_run/list", tags=["oonirun"])
def list_oonirun_descriptors(
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
    db=Depends(get_postgresql_session),
) -> OONIRunDescriptorList:
    """List OONIRun descriptors"""
    log.debug("list oonirun")
    account_id = get_account_id_or_none(authorization)

    q = db.query(models.OONIRunLink)
    query_params: Dict[str, Any] = dict(account_id=account_id)
    try:
        filters = []
        if only_latest:
            subquery = (
                db.query(
                    models.OONIRunLink.ooni_run_link_id,
                    sqlalchemy.func.max(
                        models.OONIRunLink.translation_creation_time
                    ).label("translation_creation_time"),
                )
                .group_by(models.OONIRunLink.ooni_run_link_id)
                .subquery("latest_link")
            )
            q = q.filter(
                sqlalchemy.tuple_(
                    models.OONIRunLink.ooni_run_link_id,
                    models.OONIRunLink.translation_creation_time,
                ).in_(subquery)
            )
        if not include_archived:
            q = q.filter(is_archived=False)
        if only_mine:
            q = q.filter(creator_account_id=account_id)

        if ooni_run_link_id:
            q = q.filter(
                models.OONIRunLink.ooni_run_link_id.in_(commasplit(ooni_run_link_id))
            )

    except Exception as e:
        log.debug(f"list_oonirun_descriptors: invalid parameter. {e}")
        raise HTTPException(status_code=400, detail="Incorrect parameter used")

    descriptors = []
    for row in q.all():
        descriptors.append(
            OONIRunDescriptorFetch(
                name=row.name,
                descriptor=row.descriptor,
                descriptor_creation_time=row.descriptor_creation_time,
                archived=row.is_archived,
                mine=row.creator_account_id == account_id,
                translation_creation_time=row.translation_creation_time,
                v=1,
            )
        )
    log.debug(f"Returning {len(descriptors)} descriptor[s]")
    return OONIRunDescriptorList(v=1, descriptors=descriptors)
