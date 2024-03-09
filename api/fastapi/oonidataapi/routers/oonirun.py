"""
OONIRun link management

https://github.com/ooni/spec/blob/master/backends/bk-005-ooni-run-v2.md
"""

from datetime import datetime, timedelta, timezone, date
from os import urandom
from sys import byteorder
from typing import Dict, Any, List, Optional, Tuple
import json
import logging

import sqlalchemy as sa
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, Query, HTTPException, Header
from pydantic import computed_field, Field, validator
from pydantic import BaseModel as PydandicBaseModel
from typing_extensions import Annotated

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


ISO_FORMAT_DATETIME = "%Y-%m-%dT%H:%M:%S.%fZ"
ISO_FORMAT_DATE = "%Y-%m-%d"


class BaseModel(PydandicBaseModel):
    class Config:
        json_encoders = {
            datetime: lambda v: v.strftime(ISO_FORMAT_DATETIME),
            date: lambda v: v.strftime(ISO_FORMAT_DATE),
        }


log = logging.getLogger(__name__)

router = APIRouter()


class OONIRunLinkNettest(BaseModel):
    test_name: str = Field(
        default="", title="name of the ooni nettest", min_length=2, max_length=100
    )
    test_inputs: List[str] = Field(
        default=[], title="list of input dictionaries for the nettest"
    )
    test_options: Dict = Field(default={}, title="options for the nettest")
    backend_config: Dict = Field(default={}, title="options for the nettest")
    is_background_run_enabled_default: bool = Field(
        default=False,
        title="if this test should be enabled by default for background runs",
    )
    is_manual_run_enabled_default: bool = Field(
        default=False, title="if this test should be enabled by default for manual runs"
    )


class OONIRunLinkNettestDescriptor(BaseModel):
    revision: int = Field(default=1, title="revision of the nettest")
    nettests: List[OONIRunLinkNettest] = Field(default=[], title="list of nettests")


class OONIRunLinkBase(BaseModel):
    name: str = Field(
        default="", title="name of the ooni run link", min_length=2, max_length=50
    )
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
        title="public email address of the author name of the ooni run link",
        min_length=2,
        max_length=100,
    )

    nettests: List[OONIRunLinkNettest]

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
        # None is also a valid type
        if v is None:
            return v
        for value in v.values():
            if len(value) < 2:
                raise ValueError("must be at least 2 characters")
        return v

    icon: Optional[str] = Field(
        default=None,
        description="icon to use for the ooni run link",
    )
    color: Optional[str] = Field(
        default=None,
        description="color to use for the ooni run link as a hex value prefixed with #",
        pattern="^#(?:[0-9a-fA-F]{6})$",
    )
    expiration_date: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(days=30 * 6),
        description="future time after which the ooni run link will be considered expired and no longer editable or usable (defaults to 6 months from now)",
    )


class OONIRunLink(OONIRunLinkBase):
    oonirun_link_id: str
    date_created: datetime = Field(
        description="time when the ooni run link was created"
    )
    date_updated: datetime = Field(
        description="time when the ooni run link was created"
    )
    revision: int = Field(
        description="incremental number indicating the revision number of the ooni run link (the first revision is 1)"
    )
    is_mine: Optional[bool] = Field(
        description="flag indiciating indicating if the ooni run link was created by the current user",
        default=False,
    )

    @computed_field(
        description="flag indicating if the ooni run link is expired (see the expiration_date field for more information)"
    )
    @property
    def is_expired(self) -> bool:
        # See docstring of models.OONIRunLink.expiration_date_dt_native
        return self.expiration_date.replace(tzinfo=timezone.utc) < datetime.now(
            timezone.utc
        )


class OONIRunLinkCreateEdit(OONIRunLinkBase):
    pass


def generate_link_id() -> str:
    collector_id = 0
    randint = int.from_bytes(urandom(4), byteorder)
    return str(randint * 100 + collector_id)


@router.post(
    "/v2/oonirun-links",
    tags=["oonirun"],
    dependencies=[Depends(role_required(["admin", "user"]))],
    response_model=OONIRunLink,
)
def create_oonirun_link(
    create_request: OONIRunLinkCreateEdit,
    authorization: str = Header("authorization"),
    db=Depends(get_postgresql_session),
):
    """Create a new oonirun link or a new version for an existing one."""
    log.debug("creating oonirun")
    account_id = get_account_id_or_raise(authorization)
    assert create_request

    now = datetime.now(timezone.utc).replace(microsecond=0)

    oonirun_link = OONIRunLink(
        oonirun_link_id=generate_link_id(),
        name=create_request.name,
        name_intl=create_request.name_intl,
        short_description=create_request.short_description,
        short_description_intl=create_request.short_description_intl,
        description=create_request.description,
        description_intl=create_request.description_intl,
        author=create_request.author,
        icon=create_request.icon,
        color=create_request.color,
        expiration_date=create_request.expiration_date,
        date_created=now,
        date_updated=now,
        nettests=[],
        revision=1,
    )
    # TODO(art): There is a fair amount of duplication moving around pydantic and SQLAlchmey objects.
    # Maybe https://sqlmodel.tiangolo.com/ could help.
    db_oonirun_link = models.OONIRunLink(
        creator_account_id=account_id,
        oonirun_link_id=oonirun_link.oonirun_link_id,
        name=oonirun_link.name,
        name_intl=oonirun_link.name_intl,
        short_description=oonirun_link.short_description,
        short_description_intl=oonirun_link.short_description_intl,
        description=oonirun_link.description,
        description_intl=oonirun_link.description_intl,
        author=oonirun_link.author,
        icon=oonirun_link.icon,
        color=oonirun_link.color,
        expiration_date=oonirun_link.expiration_date,
        date_created=oonirun_link.date_created,
        date_updated=oonirun_link.date_updated,
    )
    for nettest_index, nt in enumerate(create_request.nettests):
        nettest = OONIRunLinkNettest(
            test_name=nt.test_name,
            test_inputs=nt.test_inputs,
            test_options=nt.test_options,
            backend_config=nt.backend_config,
            is_background_run_enabled_default=nt.is_background_run_enabled_default,
            is_manual_run_enabled_default=nt.is_manual_run_enabled_default,
        )
        db_oonirun_link.nettests.append(
            models.OONIRunLinkNettest(
                **nettest.dict(),
                date_created=now,
                nettest_index=nettest_index,
                revision=1,
            )
        )
        oonirun_link.nettests.append(nettest)

    db.add(db_oonirun_link)
    db.commit()

    return oonirun_link


@router.put(
    "/v2/oonirun-links/{oonirun_link_id}",
    dependencies=[Depends(role_required(["admin", "user"]))],
    tags=["oonirun"],
    response_model=OONIRunLink,
)
def edit_oonirun_link(
    oonirun_link_id: str,
    edit_request: OONIRunLinkCreateEdit,
    authorization: str = Header("authorization"),
    db=Depends(get_postgresql_session),
):
    """Edit an existing OONI Run link"""
    log.debug(f"edit oonirun {oonirun_link_id}")
    account_id = get_account_id_or_raise(authorization)

    now = datetime.now(timezone.utc).replace(microsecond=0)

    q = db.query(models.OONIRunLink).filter(
        models.OONIRunLink.oonirun_link_id == oonirun_link_id
    )
    if get_client_role(authorization) != "admin":
        q = q.filter(models.OONIRunLink.creator_account_id == account_id)

    try:
        oonirun_link = q.one()
    except sa.exc.NoResultFound:
        raise HTTPException(status_code=404, detail="OONI Run link not found")

    if oonirun_link.expiration_date_dt_native < now:
        raise HTTPException(
            status_code=403,
            detail="OONI Run link has expired and cannot be edited",
        )

    if edit_request.expiration_date is not None:
        q = db.query(models.OONIRunLink).filter(
            models.OONIRunLink.oonirun_link_id == oonirun_link_id,
            # Timezones in python are a mess...
            models.OONIRunLink.expiration_date > now.replace(tzinfo=None),
        )
        if get_client_role(authorization) != "admin":
            q = q.filter(models.OONIRunLink.creator_account_id == account_id)

        q.update({"expiration_date": edit_request.expiration_date})
        db.commit()

    latest_revision = oonirun_link.nettests[0].revision
    latest_nettests = []
    for nettest_index, nt in enumerate(
        filter(lambda nt: nt.revision == latest_revision, oonirun_link.nettests)
    ):
        assert nt.nettest_index == nettest_index, "inconsistent nettest index"
        latest_nettests.append(
            OONIRunLinkNettest(
                test_name=nt.test_name,
                test_inputs=nt.test_inputs,
                test_options=nt.test_options,
                backend_config=nt.backend_config,
                is_background_run_enabled_default=nt.is_background_run_enabled_default,
                is_manual_run_enabled_default=nt.is_manual_run_enabled_default,
            )
        )

    if latest_nettests != edit_request.nettests:
        latest_revision += 1
        for nettest_index, nt in enumerate(edit_request.nettests):
            new_nettest = models.OONIRunLinkNettest(
                revision=latest_revision,
                nettest_index=nettest_index,
                date_created=now,
                test_name=nt.test_name,
                test_inputs=nt.test_inputs,
                test_options=nt.test_options,
                backend_config=nt.backend_config,
                is_background_run_enabled_default=nt.is_background_run_enabled_default,
                is_manual_run_enabled_default=nt.is_manual_run_enabled_default,
                oonirun_link=oonirun_link,
            )
            db.add(new_nettest)
        latest_nettests = edit_request.nettests

    oonirun_link.name = edit_request.name
    oonirun_link.name_intl = edit_request.name_intl
    oonirun_link.short_description = edit_request.short_description
    oonirun_link.short_description_intl = edit_request.short_description_intl
    oonirun_link.description = edit_request.description
    oonirun_link.description_intl = edit_request.description_intl
    oonirun_link.author = edit_request.author
    oonirun_link.icon = edit_request.icon
    oonirun_link.color = edit_request.color
    oonirun_link.expiration_date = edit_request.expiration_date
    oonirun_link.date_updated = now
    db.commit()

    return OONIRunLink(
        nettests=latest_nettests,
        name=oonirun_link.name,
        short_description=oonirun_link.short_description,
        description=oonirun_link.description,
        author=oonirun_link.author,
        name_intl=oonirun_link.name_intl,
        short_description_intl=oonirun_link.short_description_intl,
        description_intl=oonirun_link.description_intl,
        icon=oonirun_link.icon,
        color=oonirun_link.color,
        expiration_date=oonirun_link.expiration_date,
        oonirun_link_id=oonirun_link.oonirun_link_id,
        date_created=oonirun_link.date_created,
        date_updated=oonirun_link.date_updated,
        revision=latest_revision,
        is_mine=oonirun_link.creator_account_id == account_id,
    )


def get_nettests(
    oonirun_link: models.OONIRunLink, revision: Optional[int]
) -> Tuple[List[OONIRunLinkNettest], datetime]:
    date_created = oonirun_link.nettests[0].date_created
    nettests = []
    for nt in oonirun_link.nettests:
        if revision and nt.revision != revision:
            continue
        date_created = nt.date_created
        nettests.append(
            OONIRunLinkNettest(
                test_name=nt.test_name,
                test_inputs=nt.test_inputs,
                test_options=nt.test_options,
                backend_config=nt.backend_config,
                is_background_run_enabled_default=nt.is_background_run_enabled_default,
                is_manual_run_enabled_default=nt.is_manual_run_enabled_default,
            )
        )
    return nettests, date_created


def make_oonirun_link(
    db: Session,
    oonirun_link_id: str,
    account_id: Optional[str],
    revision: Optional[int] = None,
):
    q = db.query(models.OONIRunLink).filter(
        models.OONIRunLink.oonirun_link_id == oonirun_link_id
    )

    try:
        res = q.one()
    except sa.exc.NoResultFound:
        raise HTTPException(status_code=404, detail=f"OONI Run link not found")

    # nettests are sorted by revision
    latest_revision = res.nettests[0].revision
    if revision is None:
        revision = latest_revision

    assert isinstance(revision, int)

    nettests, date_created = get_nettests(res, revision)
    return OONIRunLink(
        oonirun_link_id=res.oonirun_link_id,
        name=res.name,
        name_intl=res.name_intl,
        short_description=res.short_description,
        short_description_intl=res.short_description_intl,
        description=res.description,
        description_intl=res.description_intl,
        icon=res.icon,
        color=res.color,
        expiration_date=res.expiration_date_dt_native,
        nettests=nettests,
        date_created=date_created,
        date_updated=res.date_updated,
        is_mine=account_id == res.creator_account_id,
        author=res.author,
        revision=revision,
    )


@metrics.timer("get_latest_oonirun_link")
@router.get(
    "/v2/oonirun-links/{oonirun_link_id}", tags=["oonirun"], response_model=OONIRunLink
)
def get_latest_oonirun_link(
    oonirun_link_id: str,
    authorization: str = Header("authorization"),
    db=Depends(get_postgresql_session),
):
    """Fetch OONIRun descriptor by creation time or the newest one"""
    # Return the latest version of the translations
    log.debug("fetching oonirun")
    account_id = get_account_id_or_none(authorization)

    oonirun_link = make_oonirun_link(
        db=db, oonirun_link_id=oonirun_link_id, account_id=account_id
    )
    return oonirun_link


@metrics.timer("get_latest_oonirun_link")
@router.get(
    "/v2/oonirun-links/{oonirun_link_id}/revision/{revision_number}",
    tags=["oonirun"],
    response_model=OONIRunLink,
)
def get_oonirun_link_revision(
    oonirun_link_id: str,
    revision_number: str,
    authorization: str = Header("authorization"),
    db=Depends(get_postgresql_session),
):
    """Fetch OONIRun descriptor by creation time or the newest one"""
    # Return the latest version of the translations
    log.debug("fetching oonirun")
    account_id = get_account_id_or_none(authorization)

    if revision_number == "latest":
        revision = None
    else:
        try:
            revision = int(revision_number)
        except:
            raise HTTPException(
                status_code=401, detail="invalid revision number specified"
            )

    oonirun_link = make_oonirun_link(
        db=db, oonirun_link_id=oonirun_link_id, account_id=account_id, revision=revision
    )
    return oonirun_link


class OONIRunLinkList(BaseModel):
    oonirun_links: List[OONIRunLink]

    class Config:
        orm_mode = True


@router.get("/v2/oonirun-links", tags=["oonirun"])
def list_oonirun_links(
    is_mine: Annotated[
        Optional[bool],
        Query(description="List only the my descriptors"),
    ] = None,
    is_expired: Annotated[
        Optional[bool],
        Query(description="List also expired descriptors"),
    ] = None,
    authorization: str = Header("authorization"),
    db=Depends(get_postgresql_session),
) -> OONIRunLinkList:
    """List OONIRun descriptors"""
    log.debug("list oonirun")
    account_id = get_account_id_or_none(authorization)

    q = db.query(models.OONIRunLink)
    if not is_expired:
        q = q.filter(models.OONIRunLink.expiration_date > datetime.now(timezone.utc))
    if is_mine == True:
        q = q.filter(models.OONIRunLink.creator_account_id == account_id)

    links = []
    for row in q.all():
        revision = 1
        if row.nettests:
            revision = row.nettests[0].revision
        nettests, _ = get_nettests(row, revision)
        oonirun_link = OONIRunLink(
            oonirun_link_id=row.oonirun_link_id,
            name=row.name,
            name_intl=row.name_intl,
            short_description=row.short_description,
            short_description_intl=row.short_description_intl,
            description=row.description,
            description_intl=row.description_intl,
            author=row.author,
            nettests=nettests,
            icon=row.icon,
            expiration_date=row.expiration_date,
            revision=revision,
            date_created=row.date_created,
            date_updated=row.date_updated,
            is_mine=account_id == row.creator_account_id,
        )
        links.append(oonirun_link)
    log.debug(f"Returning {len(links)} ooni run links")
    return OONIRunLinkList(oonirun_links=links)
