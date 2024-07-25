"""
OONIFindings incidents management
"""

from datetime import datetime, timezone
from typing import List, Optional, Union, Tuple, Any, Annotated
import logging

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Header, Response, HTTPException, Query

from pydantic import Field, ValidationInfo
from pydantic.functional_validators import field_validator

from .. import models

from ..common.routers import BaseModel
from ..common.dependencies import get_settings, role_required
from ..common.auth import (
    get_account_id_or_raise,
    get_account_id_or_none,
    get_client_role
)
from ..common.utils import setnocacheresponse, generate_random_intuid
from ..dependencies import get_postgresql_session

log = logging.getLogger(__name__)

router = APIRouter()


def utcnow_seconds():
    return datetime.now(timezone.utc).replace(microsecond=0)


class OONIFindingId(BaseModel):
    incident_id: str = Field(
        alias="id"
    )


class OONIFindingWithMail(OONIFindingId):
    email_address: str = Field(
        default="", title="email address of user"
    )


class OONIFinding(OONIFindingWithMail):
    title: str = Field(
        title="title of the ooni finding"
    )
    short_description: str = Field(
        default="", title="short description of the oonifinding report"
    )
    start_time: datetime = Field(
        title="date when the oonifinding incident started"
    )
    create_time: Optional[datetime] = Field(
        default=None, title="date when the oonifinding report was created"
    )
    update_time: Optional[datetime] = Field(
        default=None, title="time when the oonifinding report was last updated"
    )
    end_time: Optional[datetime] = Field(
        default=None, title="time when the oonifinding incident ended"
    )
    reported_by: str = Field(
        default="", title="name of the oonifinding reporter"
    )
    creator_account_id: Optional[str] = Field(
        default="", title="account id of the oonifinding report creator"
    )
    published: bool = Field(
        default=False, title="binary check if event is published"
    )
    event_type: str = Field(
        default="", title="type of oonifinding event"
    )
    ASNs: List[int] = Field(
        default=[], description="list of ASNs associate with the oonifinding"
    )
    CCs: List[str] = Field(
        default=[], description="list of country codes associated with the oonifinding"
    )
    tags: List[str] = Field(
        default=[], description="tags associated with the oonifinding"
    )
    test_names: List[str] = Field(
        default=[], description="ooni tests associated with the oonifinding"
    )
    domains: List[str] = Field(
        default=[], description="list of domains associated with the oonifinding"
    )
    links: List[str] = Field(
        default=[], description="links associated with the oonifinding"
    )
    mine: Optional[bool] = Field(
        default=False, title="check if creator account id matches user"
    )

    @field_validator("end_time")
    @classmethod
    def check_time_difference(cls, end_time: datetime, info: ValidationInfo):
        start_time = info.data.get('start_time')
        if end_time and start_time:
            start_time = start_time.replace(microsecond=0)
            end_time = end_time.replace(microsecond=0)
            delta = end_time - start_time
            if delta.total_seconds() < 0:
                raise ValueError("invalid start and end time")


class OONIFindingWithText(OONIFinding):
    text: str = Field(
        title="content of the oonifinding report"
    )

    @field_validator("title", "text")
    @classmethod
    def check_empty(cls, v: str):
        if not v:
            raise ValueError("field cannot be empty")
        return v 


class OONIFindingIncident(BaseModel):
    incident: OONIFindingWithText


class OONIFindingIncidents(BaseModel):
    incidents: List[OONIFinding]


@router.get(
    "/v1/incidents/search",
    tags=["oonifindings"],
    response_model=OONIFindingIncidents
)
def list_oonifindings(
    only_mine: Annotated[
        bool,
        Query(description="show only owned items")
    ],
    response: Response,
    authorization: str = Header("authorization"),
    db=Depends(get_postgresql_session),
    settings=Depends(get_settings),
):
    """
    Search and list incidents
    """
    log.debug("listing incidents")
    q = db.query(models.OONIFinding).filter(
        models.OONIFinding.deleted != 1
    )

    client_role = get_client_role(authorization, jwt_encryption_key=settings.jwt_encryption_key)
    account_id = get_account_id_or_none(
        authorization, jwt_encryption_key=settings.jwt_encryption_key
    )

    if only_mine:
        q = q.filter(models.OONIFinding.creator_account_id == account_id)

    if account_id is None:
        # non-published incidents are not exposed to anon users
        q = q.filter(models.OONIFinding.published == 1)
        account_id = "never-match"

    findings = []
    for row in q.all():
        oonifinding = OONIFinding(
            id=row.incident_id,
            update_time=row.update_time,
            start_time=row.start_time,
            end_time=row.end_time,
            reported_by=row.reported_by,
            title=row.title,
            event_type=row.event_type,
            published=bool(row.published),
            CCs=row.country_codes,
            ASNs=row.asns,
            domains=row.domains,
            tags=row.tags,
            test_names=row.test_names,
            links=row.links,
            short_description=row.short_description,
            email_address=row.email_address,
            create_time=row.create_time,
            mine=(row.creator_account_id == account_id)
        )

        if account_id is None or client_role != "admin":
            oonifinding.email_address = ""

        findings.append(oonifinding)

    setnocacheresponse(response)
    return OONIFindingIncidents(incidents=findings)


@router.get(
    "/v1/incidents/show/{incident_id}",
    tags=["oonifindings"],
    response_model=OONIFindingIncident
)
def get_oonifinding_by_id(
    incident_id: str,
    response: Response,
    authorization: str = Header("authorization"),
    db=Depends(get_postgresql_session),
    settings=Depends(get_settings)
):
    """
    Returns an incident
    """
    log.debug("showing incident")
    q = db.query(models.OONIFinding).filter(
        models.OONIFinding.incident_id == incident_id
    )
    q = q.filter(models.OONIFinding.deleted != 1)

    client_role = get_client_role(authorization, jwt_encryption_key=settings.jwt_encryption_key)
    account_id = get_account_id_or_none(
        authorization, jwt_encryption_key=settings.jwt_encryption_key
    )
    if account_id is None:
        # non-published incidents are not exposed to anon users
        q = q.filter(models.OONIFinding.published == 1)
        account_id = "never-match"

    try:
        finding = q.one()
    except sa.exc.NoResultFound:
        raise HTTPException(status_code=404, detail="OONI Finding not found")

    oonifinding = OONIFindingWithText(
        id=finding.incident_id,
        update_time=finding.update_time,
        start_time=finding.start_time,
        end_time=finding.end_time,
        reported_by=finding.reported_by,
        title=finding.title,
        text=finding.text,
        event_type=finding.event_type,
        published=bool(finding.published),
        CCs=finding.country_codes,
        ASNs=finding.asns,
        domains=finding.domains,
        tags=finding.tags,
        test_names=finding.test_names,
        links=finding.links,
        short_description=finding.short_description,
        email_address=finding.email_address,
        create_time=finding.create_time,
        mine=(finding.creator_account_id == account_id)
    )

    if account_id is None or client_role != "admin":
        oonifinding.email_address = ""  # hide email

    # TODO: cache if possible
    setnocacheresponse(response)
    return OONIFindingIncident(incident=oonifinding)


class OONIFindingCreateUpdate(OONIFindingWithText):
    pass


# TODO(decfox): we maintain this pydantic model to ensure client response
# does not change. Eventually, we should get rid of this and simply
# return the updated sqlalchemy model.
class OONIFindingsUpdateResponse(OONIFindingId):
    r: Union[int, Tuple[List[Any]]] = Field(
        default=0, title="result of the update operation"
    )


def validate_time(incident: OONIFinding) -> bool:
    incident.start_time = incident.start_time.replace(microsecond=0)
    if incident.end_time is not None:
        incident.end_time = incident.end_time.replace(microsecond=0)
        delta = incident.end_time - incident.start_time
        if delta.total_seconds() < 0:
            raise HTTPException(status_code=400, detail="invalid query paramters") 
    return True


@router.post(
    "/v1/incidents/create",
    tags=["oonifindings"],
    response_model=OONIFindingsUpdateResponse
)
def create_oonifinding(
    create_request: OONIFindingCreateUpdate,
    response: Response,
    authorization: str = Header("authorization"),
    token=Depends(role_required(["admin"])),
    db=Depends(get_postgresql_session),
    settings=Depends(get_settings)
):
    """
    Create an incident
    """
    if create_request.email_address != token["email_address"]:
        raise HTTPException(status_code=400, detail="Invalid email address for creator account")

    # assert create_request
    if create_request.published:
        raise HTTPException(status_code=400, detail="Invalid publish parameter on create request")

    # TODO(decfox): evaluate if we can replace this with a simple getter
    account_id = get_account_id_or_raise(
        authorization, jwt_encryption_key=settings.jwt_encryption_key
    )
    now = utcnow_seconds()
    incident_id = str(generate_random_intuid(collector_id=settings.collector_id))

    log.info(f"Creating incident {incident_id}")

    db_oonifinding = models.OONIFinding(
        incident_id=incident_id,
        create_time=now,
        update_time=now,
        start_time=create_request.start_time,
        end_time=create_request.end_time,
        creator_account_id=account_id,
        title=create_request.title,
        short_description=create_request.short_description,
        text=create_request.text,
        reported_by=create_request.reported_by,
        email_address=create_request.email_address,
        event_type=create_request.event_type,
        published=int(create_request.published),
        country_codes=create_request.CCs,
        asns=create_request.ASNs,
        domains=create_request.domains,
        tags=create_request.tags,
        links=create_request.links,
        test_names=create_request.test_names,
    )

    db.add(db_oonifinding)
    db.commit()

    setnocacheresponse(response)
    return OONIFindingsUpdateResponse(r=1, id=incident_id)


@router.post(
    "/v1/incidents/update",
    tags=["oonifindings"],
    response_model=OONIFindingsUpdateResponse
)
def update_oonifinding(
    update_request: OONIFindingCreateUpdate,
    response: Response,
    db=Depends(get_postgresql_session),
    token=Depends(role_required(["admin", "user"])),
):
    """
    Update an incident
    """
    incident_id = update_request.incident_id
    account_id = token["account_id"]

    q = db.query(models.OONIFinding).filter(
        models.OONIFinding.incident_id == incident_id
    )
    if token["role"] == "user":
        q = q.filter(models.OONIFinding.creator_account_id == account_id)
        if update_request.email_address != token["email_address"]:
            raise HTTPException(status_code=403, detail="You are not allowed to set the email address to something other than your email address")
        if update_request.published:
            raise HTTPException(status_code=403, detail="You are not allowed to publish")
    else:
        assert token["role"] == "admin"

    try:
        oonifinding = q.one()
    except sa.exc.NoResultFound:
        raise HTTPException(status_code=404, detail="OONI Finding not found")

    log.info(f"Updating incident {incident_id}")

    now = utcnow_seconds()
    oonifinding.update_time = now
    oonifinding.start_time = update_request.start_time
    oonifinding.end_time = update_request.end_time
    oonifinding.reported_by = update_request.reported_by
    oonifinding.title = update_request.title
    oonifinding.text = update_request.text
    oonifinding.event_type = update_request.event_type
    oonifinding.published = int(update_request.published)
    oonifinding.country_codes = update_request.CCs
    oonifinding.asns = update_request.ASNs
    oonifinding.domains = update_request.domains
    oonifinding.tags = update_request.tags
    oonifinding.links = update_request.links
    oonifinding.test_names = update_request.test_names
    oonifinding.short_description = update_request.short_description
    oonifinding.email_address = update_request.email_address
    db.commit()

    setnocacheresponse(response)
    return OONIFindingsUpdateResponse(r=1, id=incident_id)


@router.post(
      "/v1/incidents/delete",
      tags=["oonifindings"],
)
def delete_oonifinding(
    delete_request: OONIFindingWithMail,
    response: Response,
    token=Depends(role_required(["admin", "user"])),
    db=Depends(get_postgresql_session),
):
    """
    Delete an incident
    """
    assert delete_request
    account_id = token["account_id"]
    incident_id = delete_request.incident_id

    q = db.query(models.OONIFinding).filter(
        models.OONIFinding.incident_id == incident_id
    )
    if token["role"] == "user":
        q = q.filter(models.OONIFinding.creator_account_id == account_id)
        if delete_request.email_address != token["email_address"]:
            raise HTTPException(status_code=403, detail="You are not allowed to delete the incident")
    else:
        assert token["role"] == "admin"

    try:
        q.one()
    except sa.exc.NoResultFound:
        raise HTTPException(status_code=404, detail="OONI Finding not found")
    
    q.delete()
    db.commit()

    setnocacheresponse(response)
    return {}


@router.post(
    "/v1/incidents/{action}",
    tags=["oonifindings"],
    dependencies=[Depends(role_required(["admin"]))],
    response_model=OONIFindingsUpdateResponse
)
def update_oonifinding_publish_status(
    action: str,
    publish_request: OONIFindingCreateUpdate,
    response: Response,
    db=Depends(get_postgresql_session),
):
    """
    Publish/Unpublish an incident.
    """
    if action not in ("publish", "unpublish"):
        raise HTTPException(status_code=400, detail="Invalid query action")

    assert publish_request
    incident_id = publish_request.incident_id

    q = db.query(models.OONIFinding).filter(
        models.OONIFinding.incident_id == publish_request.incident_id
    )

    try:
        oonifinding = q.one()
    except sa.exc.NoResultFound:
        raise HTTPException(status_code=404, detail="OONI Finding not found")

    oonifinding.published = int(action == "publish")
    db.commit()

    setnocacheresponse(response)
    return OONIFindingsUpdateResponse(r=1, id=incident_id)
