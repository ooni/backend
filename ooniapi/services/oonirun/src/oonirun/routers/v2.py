"""
OONIRun link management

https://github.com/ooni/spec/blob/master/backends/bk-005-ooni-run-v2.md
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Any
import logging

import sqlalchemy as sa
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, Query, HTTPException, Header, Path
from pydantic import computed_field, Field
from pydantic.functional_validators import field_validator, model_validator
from typing_extensions import Annotated, Self

from .. import models

from ..common.routers import BaseModel
from ..common.dependencies import get_settings, role_required
from ..common.auth import (
    get_account_id_or_none,
)
from ..dependencies import PostgresSession, get_postgresql_session


log = logging.getLogger(__name__)

router = APIRouter()


def utcnow_seconds():
    return datetime.now(timezone.utc).replace(microsecond=0)


class OONIRunLinkNettest(BaseModel):
    test_name: str = Field(
        default="", title="name of the ooni nettest", min_length=2, max_length=100
    )
    inputs: List[str] = Field(
        default=[], title="list of input dictionaries for the nettest"
    )
    options: Dict = Field(default={}, title="options for the nettest")
    # TODO(luis): Not in the new spec. Should be removed?
    backend_options: Dict = Field(default={}, title="options to send to the backend")
    is_background_run_enabled_default: bool = Field(
        default=False,
        title="if this test should be enabled by default for background runs",
    )
    is_manual_run_enabled_default: bool = Field(
        default=False, title="if this test should be enabled by default for manual runs"
    )

    targets_name : Optional[str] = Field (
        default=None, 
        description="string used to specify during creation that the input list should be dynamically generated."
    )

    inputs_extra : Optional[List[Dict[str, Any]]] = Field (
        default = None,
        description = "provides a richer JSON array containing extra parameters for each input. If provided, the length of inputs_extra should match the length of inputs."
    )

    @model_validator(mode="after")
    def validate_inputs_extra(self) -> Self:
        if self.inputs_extra is not None and len(self.inputs) != len(self.inputs_extra):
            raise ValueError("When provided, inputs_extra should be the same length as inputs")
        return self

class OONIRunLinkEngineDescriptor(BaseModel):
    revision: str = Field(title="revision of the nettest descriptor")
    nettests: List[OONIRunLinkNettest] = Field(default=[], title="list of nettests")
    date_created: datetime = Field(title="date when the nettest list was created")


class OONIRunLinkBase(BaseModel):
    name: str = Field(title="name of the ooni run link", min_length=2, max_length=50)
    short_description: str = Field(
        title="short description of the ooni run link",
        min_length=2,
        max_length=200,
    )

    description: str = Field(
        title="full description of the ooni run link", min_length=2
    )
    author: str = Field(
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

    @field_validator("name_intl", "short_description_intl", "description_intl")
    @classmethod
    def validate_intl(cls, v: Dict[str, str]):
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
        default_factory=lambda: utcnow_seconds() + timedelta(days=30 * 6),
        description="future time after which the ooni run link will be considered expired and no longer editable or usable (defaults to 6 months from now)",
    )

class OONIRunLink(OONIRunLinkBase):


    oonirun_link_id: str
    date_created: datetime = Field(
        description="time when the ooni run link was created"
    )
    date_updated: datetime = Field(
        description="time when the ooni run nettest was last updated"
    )
    revision: str = Field(
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
        return self.expiration_date < utcnow_seconds()


class OONIRunLinkCreateEdit(OONIRunLinkBase):
    pass


@router.post(
    "/v2/oonirun/links",
    tags=["oonirun"],
    response_model=OONIRunLink,
)
def create_oonirun_link(
    create_request: OONIRunLinkCreateEdit,
    db : PostgresSession,
    token=Depends(role_required(["admin", "user"])),
) -> OONIRunLink:
    """Create a new oonirun link or a new version for an existing one."""
    log.debug("creating oonirun")
    account_id = token["account_id"]
    assert create_request

    if create_request.author != token["email_address"]:
        raise HTTPException(
            status_code=400,
            detail="email_address must match the email address of the user who created the oonirun link",
        )

    now = utcnow_seconds()

    revision = 1
    db_oonirun_link = models.OONIRunLink(
        creator_account_id=account_id,
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
    )
    nettest_list = []
    for nettest_index, nt in enumerate(create_request.nettests):
        nettest = OONIRunLinkNettest(
            test_name=nt.test_name,
            inputs=nt.inputs,
            options=nt.options,
            backend_options=nt.backend_options,
            is_background_run_enabled_default=nt.is_background_run_enabled_default,
            is_manual_run_enabled_default=nt.is_manual_run_enabled_default,
        )
        db_oonirun_link.nettests.append(
            models.OONIRunLinkNettest(
                **nettest.model_dump(),
                date_created=now,
                nettest_index=nettest_index,
                revision=revision,
            )
        )
        nettest_list.append(nettest)

    db.add(db_oonirun_link)
    db.commit()

    return OONIRunLink(
        oonirun_link_id=db_oonirun_link.oonirun_link_id,
        name=db_oonirun_link.name,
        name_intl=db_oonirun_link.name_intl,
        short_description=db_oonirun_link.short_description,
        short_description_intl=db_oonirun_link.short_description_intl,
        description=db_oonirun_link.description,
        description_intl=db_oonirun_link.description_intl,
        author=db_oonirun_link.author,
        icon=db_oonirun_link.icon,
        color=db_oonirun_link.color,
        expiration_date=db_oonirun_link.expiration_date,
        date_created=db_oonirun_link.date_created,
        date_updated=db_oonirun_link.date_updated,
        nettests=nettest_list,
        revision=str(revision),
    )


@router.put(
    "/v2/oonirun/links/{oonirun_link_id}",
    tags=["oonirun"],
    response_model=OONIRunLink,
)
def edit_oonirun_link(
    oonirun_link_id: str,
    edit_request: OONIRunLinkCreateEdit,
    db : PostgresSession,
    token=Depends(role_required(["admin", "user"])),
):
    """Edit an existing OONI Run link"""
    log.debug(f"edit oonirun {oonirun_link_id}")
    account_id = token["account_id"]

    now = utcnow_seconds()

    q = db.query(models.OONIRunLink).filter(
        models.OONIRunLink.oonirun_link_id == oonirun_link_id
    )
    if token["role"] == "user":
        q = q.filter(models.OONIRunLink.creator_account_id == account_id)
        if token["email_address"] != edit_request.author:
            raise HTTPException(
                status_code=403,
                detail="You are not allowed to set the email_address to something other than your email address",
            )
    else:
        # When you are an admin we can do everything and there are no other roles
        assert token["role"] == "admin"

    try:
        oonirun_link = q.one()
    except sa.exc.NoResultFound:
        raise HTTPException(status_code=404, detail="OONI Run link not found")

    if oonirun_link.expiration_date < now:
        raise HTTPException(
            status_code=403,
            detail="OONI Run link has expired and cannot be edited",
        )

    latest_revision: int = oonirun_link.nettests[0].revision
    latest_nettests = []
    for nettest_index, nt in enumerate(
        filter(lambda nt: nt.revision == latest_revision, oonirun_link.nettests)
    ):
        assert nt.nettest_index == nettest_index, "inconsistent nettest index"
        latest_nettests.append(
            OONIRunLinkNettest(
                test_name=nt.test_name,
                inputs=nt.inputs,
                options=nt.options,
                backend_options=nt.backend_options,
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
                inputs=nt.inputs,
                options=nt.options,
                backend_options=nt.backend_options,
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
        revision=str(latest_revision),
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
                inputs=nt.inputs,
                options=nt.options,
                backend_options=nt.backend_options,
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
        expiration_date=res.expiration_date,
        nettests=nettests,
        date_created=date_created,
        date_updated=res.date_updated,
        is_mine=account_id == res.creator_account_id,
        author=res.author,
        revision=str(revision),
    )


class OONIRunLinkRevisions(BaseModel):
    revisions: List[str]


@router.get(
    "/v2/oonirun/links/{oonirun_link_id}/revisions",
    tags=["oonirun"],
    response_model=OONIRunLinkRevisions,
)
def get_oonirun_link_revisions(
    oonirun_link_id: str,
    db : PostgresSession,
):
    """
    Obtain the list of revisions for a certain OONI Run link
    """
    q = db.query(models.OONIRunLink).filter(
        models.OONIRunLink.oonirun_link_id == oonirun_link_id
    )

    try:
        res = q.one()
    except sa.exc.NoResultFound:
        raise HTTPException(status_code=404, detail=f"OONI Run link not found")

    revision = set()
    for nt in res.nettests:
        revision.add(nt.revision)

    revisions = []
    for r in sorted(revision, reverse=True):
        revisions.append(str(r))
    return OONIRunLinkRevisions(revisions=revisions)


@router.get(
    "/v2/oonirun/links/{oonirun_link_id}/engine-descriptor/{revision_number}",
    tags=["oonirun"],
    response_model=OONIRunLinkEngineDescriptor,
)
def get_oonirun_link_engine_descriptor(
    oonirun_link_id: str,
    revision_number: Annotated[
        str,
        Path(
            pattern="^(latest|\\d+)$",
            error_messages={
                "regex": "invalid revision number specified, must be 'latest' or a number"
            },
        ),
    ],
    db : PostgresSession,
):
    """Fetch an OONI Run link by specifying the revision number"""
    try:
        revision = int(revision_number)
    except:
        # We can assert it, since we are doing validation
        assert revision_number == "latest"
        revision = None

    q = db.query(models.OONIRunLink).filter(
        models.OONIRunLink.oonirun_link_id == oonirun_link_id
    )

    try:
        res = q.one()
    except sa.exc.NoResultFound:
        raise HTTPException(status_code=404, detail=f"OONI Run link not found")

    latest_revision = res.nettests[0].revision
    if revision is None:
        revision = latest_revision

    assert isinstance(revision, int)
    nettests, date_created = get_nettests(res, revision)
    return OONIRunLinkEngineDescriptor(
        nettests=nettests,
        date_created=date_created,
        revision=str(revision),
    )


@router.get(
    "/v2/oonirun/links/{oonirun_link_id}/full-descriptor/{revision_number}",
    tags=["oonirun"],
    response_model=OONIRunLink,
)
def get_oonirun_link_revision(
    oonirun_link_id: str,
    revision_number: Annotated[
        str,
        Path(
            pattern="^(latest|\\d+)$",
            error_messages={
                "regex": "invalid revision number specified, must be 'latest' or a number"
            },
        ),
    ],
    db : PostgresSession,
    authorization: str = Header("authorization"),
    settings=Depends(get_settings),
):
    """Fetch an OONI Run link by specifying the revision number"""
    # Return the latest version of the translations
    log.debug("fetching oonirun")
    account_id = get_account_id_or_none(
        authorization, jwt_encryption_key=settings.jwt_encryption_key
    )

    try:
        revision = int(revision_number)
    except:
        # We can assert it, since we are doing validation
        assert revision_number == "latest"
        revision = None

    oonirun_link = make_oonirun_link(
        db=db, oonirun_link_id=oonirun_link_id, account_id=account_id, revision=revision
    )
    return oonirun_link


@router.get(
    "/v2/oonirun/links/{oonirun_link_id}", tags=["oonirun"], response_model=OONIRunLink
)
def get_latest_oonirun_link(
    oonirun_link_id: str,
    db : PostgresSession,
    authorization: str = Header("authorization"),
    settings=Depends(get_settings),
):
    """Fetch OONIRun descriptor by creation time or the newest one"""
    # Return the latest version of the translations
    log.debug("fetching oonirun")
    account_id = get_account_id_or_none(
        authorization, jwt_encryption_key=settings.jwt_encryption_key
    )

    oonirun_link = make_oonirun_link(
        db=db, oonirun_link_id=oonirun_link_id, account_id=account_id
    )
    return oonirun_link


class OONIRunLinkList(BaseModel):
    oonirun_links: List[OONIRunLink]


@router.get("/v2/oonirun/links", tags=["oonirun"])
def list_oonirun_links(
    db : PostgresSession,
    is_mine: Annotated[
        Optional[bool],
        Query(description="List only the my descriptors"),
    ] = None,
    is_expired: Annotated[
        Optional[bool],
        Query(description="List also expired descriptors"),
    ] = None,
    authorization: str = Header("authorization"),
    settings=Depends(get_settings),
) -> OONIRunLinkList:
    """List OONIRun descriptors"""
    log.debug("list oonirun")
    account_id = get_account_id_or_none(authorization, settings.jwt_encryption_key)

    q = db.query(models.OONIRunLink)
    if not is_expired:
        q = q.filter(models.OONIRunLink.expiration_date > utcnow_seconds())
    if is_mine == True:
        q = q.filter(models.OONIRunLink.creator_account_id == account_id)

    links = []
    for row in q.all():
        revision = row.nettests[0].revision
        assert (
            row.nettests[-1].revision <= revision
        ), "nettests must be sorted by revision"
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
            revision=str(revision),
            date_created=row.date_created,
            date_updated=row.date_updated,
            is_mine=account_id == row.creator_account_id,
        )
        links.append(oonirun_link)
    log.debug(f"Returning {len(links)} ooni run links")
    return OONIRunLinkList(oonirun_links=links)
