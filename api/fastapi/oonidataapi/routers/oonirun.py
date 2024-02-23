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
from pydantic import constr, Field, validator
from pydantic import BaseModel as PydandicBaseModel
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
from ..dependencies import get_postgresql_session


ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


class BaseModel(PydandicBaseModel):
    class Config:
        json_encoders = {datetime: lambda v: v.strftime(ISO_FORMAT)}


log = logging.getLogger(__name__)

router = APIRouter()


class OONIRunLinkBase(BaseModel):
    name: str = Field(default="", title="name of the ooni run link", min_length=2)
    short_description: str = Field(
        default="",
        title="short description of the ooni run link",
        min_length=2,
        max_length=200,
    )

    description: str = Field(
        default="", title="full description of the ooni run link", min_length=2
    )
    author: str = Field(
        default="",
        title="public author name of ooni run link",
        min_length=2,
        max_length=100,
    )

    nettests: List[Dict]

    name_intl: Optional[Dict[str, str]] = Field(
        default=None,
        description="name of the ooni run link in different languages",
    )
    short_description_intl: Optional[Dict[str, str]] = Field(
        default=None,
        description="short description of the ooni run link in different languages",
    )
    description_intl: Optional[Dict[str, str]] = Field(
        default=None,
        description="full description of the ooni run link in different languages",
    )

    @validator("name_intl", "short_description_intl", "description_intl")
    def validate_intl(cls, v):
        for value in v.values():
            if len(value) < 2:
                raise ValueError("must be at least 2 characters")
        return v

    icon: Optional[str] = ""


class OONIRunLink(OONIRunLinkBase):
    is_archived: Optional[bool] = False
    oonirun_link_id: int
    date_created: datetime
    date_updated: datetime
    creator_account_id: str
    revision: int
    is_mine: Optional[bool] = False

    v: int = 1

    class Config:
        orm_mode = True


class OONIRunLinkCreate(OONIRunLinkBase):
    pass


class OONIRunLinkEdit(OONIRunLinkBase):
    is_archived: Optional[bool] = False


def generate_random_intuid() -> int:
    collector_id = 0
    randint = int.from_bytes(urandom(4), byteorder)
    return randint * 100 + collector_id


@router.post(
    "/v2/oonirun",
    tags=["oonirunv2"],
    dependencies=[Depends(role_required(["admin", "user"]))],
    response_model=OONIRunLink,
)
def create_oonirun_link(
    create_request: OONIRunLinkCreate,
    authorization: str = Header("authorization"),
    db=Depends(get_postgresql_session),
):
    """Create a new oonirun link or a new version for an existing one."""
    log.debug("creating oonirun")
    account_id = get_account_id_or_raise(authorization)
    assert create_request

    now = datetime.utcnow().replace(microsecond=0)

    oonirun_link = models.OONIRunLink(
        oonirun_link_id=generate_random_intuid(),
        creator_account_id=account_id,
        name=create_request.name,
        name_intl=create_request.name_intl,
        short_description=create_request.short_description,
        short_description_intl=create_request.short_description_intl,
        description=create_request.description,
        description_intl=create_request.description_intl,
        author=create_request.author,
        nettests=create_request.nettests,
        icon=create_request.icon,
        is_archived=False,
        date_created=now,
        date_updated=now,
    )

    db.add(oonirun_link)
    db.commit()
    db.refresh(oonirun_link)

    return oonirun_link


@router.put(
    "/v2/oonirun/{oonirun_link_id}",
    dependencies=[Depends(role_required(["admin", "user"]))],
    tags=["oonirun"],
    response_model=OONIRunLink,
)
def edit_oonirun_link(
    oonirun_link_id: int,
    edit_request: OONIRunLinkEdit,
    authorization: str = Header("authorization"),
    db=Depends(get_postgresql_session),
):
    """Edit an existing OONI Run link"""
    log.debug(f"edit oonirun {oonirun_link_id}")
    account_id = get_account_id_or_raise(authorization)

    now = datetime.utcnow().replace(microsecond=0)

    q = db.query(models.OONIRunLink).filter(
        models.OONIRunLink.oonirun_link_id == oonirun_link_id
    )
    if get_client_role(authorization) != "admin":
        q = q.filter(models.OONIRunLink.creator_account_id == account_id)
    oonirun_link = q.order_by(models.OONIRunLink.revision.desc()).first()
    if not oonirun_link:
        raise HTTPException(status_code=404, detail="OONI Run link not found")

    current_nettests = oonirun_link.nettests
    if current_nettests != edit_request.nettests:
        new_oonirun_link = models.OONIRunLink(
            oonirun_link_id=oonirun_link.oonirun_link_id,
            creator_account_id=account_id,
            name=edit_request.name,
            name_intl=edit_request.name_intl,
            short_description=edit_request.short_description,
            short_description_intl=edit_request.short_description_intl,
            description=edit_request.description,
            description_intl=edit_request.description_intl,
            author=edit_request.author,
            nettests=edit_request.nettests,
            icon=edit_request.icon,
            is_archived=edit_request.is_archived,
            revision=int(oonirun_link.revision + 1),
            date_created=now,
            date_updated=now,
        )
        db.add(new_oonirun_link)
        db.commit()
        return new_oonirun_link

    oonirun_link.name = edit_request.name
    oonirun_link.name_intl = edit_request.name_intl
    oonirun_link.short_description = edit_request.short_description
    oonirun_link.short_description_intl = edit_request.short_description_intl
    oonirun_link.description = edit_request.description
    oonirun_link.description_intl = edit_request.description_intl
    oonirun_link.author = edit_request.author
    oonirun_link.nettests = edit_request.nettests
    oonirun_link.icon = edit_request.icon
    oonirun_link.is_archived = edit_request.is_archived
    oonirun_link.date_updated = now
    db.commit()
    return oonirun_link


@metrics.timer("fetch_oonirun_descriptor")
@router.get(
    "/v2/oonirun/{oonirun_link_id}", tags=["oonirun"], response_model=OONIRunLink
)
def fetch_oonirun_descriptor(
    oonirun_link_id: int,
    revision: Annotated[
        Optional[int],
        Query(
            description="specificy which revision of the run link descriptor you wish to fetch"
        ),
    ] = None,
    authorization: str = Header("authorization"),
    db=Depends(get_postgresql_session),
):
    """Fetch OONIRun descriptor by creation time or the newest one"""
    # Return the latest version of the translations
    log.debug("fetching oonirun")
    account_id = get_account_id_or_none(authorization)

    q = db.query(models.OONIRunLink).filter(
        models.OONIRunLink.oonirun_link_id == oonirun_link_id
    )
    if revision is not None:
        q = q.filter(models.OONIRunLink.revision == revision)
    oonirun_link = q.order_by(models.OONIRunLink.revision.desc()).first()

    if oonirun_link is None:
        raise HTTPException(status_code=404, detail=f"OONI Run link not found")

    oonirun_link.is_mine = account_id == oonirun_link.creator_account_id
    return oonirun_link


class OONIRunDescriptorList(BaseModel):
    descriptors: List[OONIRunLink]
    v: int = 1

    class Config:
        orm_mode = True


@router.get("/v2/oonirun/", tags=["oonirun"])
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
    try:
        if only_latest:
            subquery = (
                db.query(
                    models.OONIRunLink.oonirun_link_id,
                    sqlalchemy.func.max(models.OONIRunLink.revision).label("revision"),
                )
                .group_by(models.OONIRunLink.oonirun_link_id)
                .subquery("latest_link")
            )
            q = q.filter(
                sqlalchemy.tuple_(
                    models.OONIRunLink.oonirun_link_id,
                    models.OONIRunLink.revision,
                ).in_(subquery)
            )
        if not include_archived:
            q = q.filter(models.OONIRunLink.is_archived == False)
        if only_mine:
            q = q.filter(models.OONIRunLink.creator_account_id == account_id)

        if ooni_run_link_id:
            q = q.filter(
                models.OONIRunLink.oonirun_link_id.in_(commasplit(ooni_run_link_id))
            )

    except Exception as e:
        log.debug(f"list_oonirun_descriptors: invalid parameter. {e}")
        raise HTTPException(status_code=400, detail="Incorrect parameter used")

    descriptors = []
    for row in q.all():
        oonirun_link = OONIRunLink(
            oonirun_link_id=row.oonirun_link_id,
            creator_account_id=row.creator_account_id,
            name=row.name,
            name_intl=row.name_intl,
            short_description=row.short_description,
            short_description_intl=row.short_description_intl,
            description=row.description,
            description_intl=row.description_intl,
            author=row.author,
            nettests=row.nettests,
            icon=row.icon,
            is_archived=row.is_archived,
            revision=row.revision,
            date_created=row.date_created,
            date_updated=row.date_updated,
            is_mine=account_id == row.creator_account_id,
        )
        descriptors.append(oonirun_link)
    log.debug(f"Returning {len(descriptors)} descriptor[s]")
    return OONIRunDescriptorList(v=1, descriptors=descriptors)
