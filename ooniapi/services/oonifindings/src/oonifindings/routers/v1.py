"""
OONIFindings incidents management
"""

from datetime import datetime, timezone
from typing import List, Dict, Optional, Union, Tuple, Any, Annotated
import logging

from clickhouse_driver import Client as Clickhouse
from fastapi import APIRouter, Depends, Header, Response, HTTPException, Query

from pydantic import Field
from pydantic.functional_validators import field_validator

from ..common.routers import BaseModel, ISO_FORMAT_DATE
from ..common.dependencies import get_settings, role_required
from ..common.auth import (
    check_email_address,
    get_account_id_or_raise,
    get_account_id_or_none, 
    get_client_role
)
from ..common.utils import setnocacheresponse, generate_random_intuid
from ..common.clickhouse_utils import query_click, raw_query, insert_click, optimize_table
from ..dependencies import get_clickhouse_session

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
    response_model = OONIFindingIncidents
)
def list_oonifindings(
    only_mine: Annotated[
        bool,
        Query(description="show only owned items")
    ],
    response: Response,
    authorization: str = Header("authorization"),
    db=Depends(get_clickhouse_session),
    settings=Depends(get_settings),
):
    """
    Search and list incidents
    """
    log.debug("listing incidents")
    where = "WHERE deleted != 1"
    query_params = {}

    account_id = get_account_id_or_none(
        authorization, jwt_encryption_key=settings.jwt_encryption_key
    )
    if only_mine:
        if account_id is None:
            return OONIFindingIncidents(incidents=[])
        where += "\nAND creator_account_id = %(account_id)s"

    if account_id is None:
        # non-published incidents are not exposed to anon users
        where += "\nAND published = 1"
        query_params["account_id"] = "never-match"
    else:
        query_params["account_id"] = account_id

    query = f"""SELECT id, update_time, start_time, end_time, reported_by,
    title, event_type, published, CCs, ASNs, domains, tags, test_names,
    links, short_description, email_address, create_time, 
    creator_account_id = %(account_id)s as mine
    FROM incidents FINAL
    {where}
    ORDER BY title
    """
    q = query_click(db=db, query=query, query_params=query_params)
    
    incidents = list(q) 
    client_role = get_client_role(authorization, jwt_encryption_key=settings.jwt_encryption_key)
    for incident in incidents:
        incident["published"] = bool(incident["published"])  
        if account_id is None or client_role != "admin":
            incident["email_address"] = ""
    
    setnocacheresponse(response)
    incident_models = []
    for i in range(len(incidents)):
        incident = incidents[i]
        incident_model = OONIFinding.model_validate(incident)
        incident_models.append(incident_model)
    return OONIFindingIncidents(incidents=incident_models)


@router.get(
    "/v1/incidents/show/{incident_id}",
    tags=["oonifindings"],
    response_model=OONIFindingIncident
)
def get_oonifinding_by_id(
    incident_id: str,
    response: Response,
    authorization: str = Header("authorization"),
    db=Depends(get_clickhouse_session),
    settings=Depends(get_settings)
):
    """
    Returns an incident
    """
    log.debug("showing incident")
    where = "WHERE id = %(id)s AND deleted != 1"
    account_id = get_account_id_or_none(
        authorization, jwt_encryption_key=settings.jwt_encryption_key
    )
    if account_id is None:
        # non-published incidents are not exposed to anon users
        where += "\nAND published = 1"
        query_params = {"id": incident_id, "account_id": "never-match"}
    else:
        query_params = {"id": incident_id, "account_id": account_id}

    query = f"""SELECT id, update_time, start_time, end_time, reported_by,
    title, text, event_type, published, CCs, ASNs, domains, tags, test_names,
    links, short_description, email_address, create_time, 
    creator_account_id = %(account_id)s AS mine
    FROM incidents FINAL
    {where}
    LIMIT 1
    """
    q = query_click(db=db, query=query, query_params=query_params)
    if len(q) < 1:
        raise HTTPException(status_code=404, detail="Incident not found")

    incident = q[0]
    incident["published"] = bool(incident["published"]) 
    client_role = get_client_role(authorization, jwt_encryption_key=settings.jwt_encryption_key)
    if account_id is None or client_role != "admin":
        incident["email_address"] = ""  # hide email
    
    # TODO: cache if possible
    setnocacheresponse(response)
    incident_model = OONIFindingWithText.model_validate(incident)
    return OONIFindingIncident(incident=incident_model)


def prepare_incident_dict(incident: OONIFinding) -> Dict:
    incident.start_time = incident.start_time.replace(microsecond=0)
    if incident.end_time is not None:
        incident.end_time = incident.end_time.replace(microsecond=0)
        delta = incident.end_time - incident.start_time
        if delta.total_seconds() < 0:
            raise HTTPException(status_code=400, detail="invalid query paramters") 
    incident_dict = incident.model_dump(by_alias=True)
    return incident_dict


def user_cannot_update(
    db: Clickhouse,
    authorization: str,
    jwt_encryption_key: str,
    incident_id: str,
) -> bool:
    # Check if there is already an incident and belongs to a different user
    query = """SELECT count() AS cnt
    FROM incidents FINAL
    WHERE deleted != 1
    AND id = %(incident_id)s
    AND creator_account_id != %(account_id)s
    """
    account_id = get_account_id_or_raise(authorization, jwt_encryption_key=jwt_encryption_key)
    query_params = dict(incident_id=incident_id, account_id=account_id)
    q = query_click(db, query, query_params)
    return q[0]["cnt"] > 0


def verify_user(
    db: Clickhouse,
    authorization: str,
    jwt_encryption_key: str,
    incident_id: str,
    email_address: str,
    key: str
):
    if user_cannot_update(
        db, authorization, jwt_encryption_key=jwt_encryption_key, incident_id=incident_id
    ):
        raise HTTPException(status_code=400, detail="Attempted to create, update or delete an item belonging to another user")
        
    if not check_email_address(
        authorization=authorization,
        jwt_encryption_key=jwt_encryption_key,
        email_address=email_address,
        key=key
    ):
        raise HTTPException(status_code=400, detail="Invalid email address for owner account")


class OONIFindingCreateUpdate(OONIFindingWithText):
    pass


class OONIFindingsUpdateResponse(OONIFindingId):
    r: Union[int, Tuple[List[Any]]] = Field(
        default=0, title="result of the update operation"
    )


@router.post(
    "/v1/incidents/create",
    dependencies=[Depends(role_required(["admin"]))],
    tags=["oonifindings"],
    response_model=OONIFindingsUpdateResponse
)
def create_oonifinding(
    create_request: OONIFindingCreateUpdate,
    response: Response,
    authorization: str = Header("authorization"),
    db=Depends(get_clickhouse_session),
    settings=Depends(get_settings)
):
    """
    Create an incident
    """
    if not check_email_address(
        authorization=authorization,
        jwt_encryption_key=settings.jwt_encryption_key,
        email_address=create_request.email_address,
        key=settings.account_id_hashing_key
    ):
        raise HTTPException(status_code=400, detail="Invalid email address for creator account")
    
    # assert create_request
    if create_request.published:
        raise HTTPException(status_code=400, detail="Invalid publish parameter on create request")


    incident_id = str(generate_random_intuid(collector_id=settings.collector_id))    
    create_request.incident_id = incident_id 
    create_request.create_time = utcnow_seconds()
    create_request.creator_account_id = get_account_id_or_raise(
        authorization, jwt_encryption_key=settings.jwt_encryption_key
    ) 
    incident_dict = prepare_incident_dict(incident=create_request)

    log.info(f"Creating incident {incident_id}")

    query = """INSERT INTO incidents
    (id, start_time, end_time, creator_account_id, reported_by, title,
    text, event_type, published, CCs, ASNs, domains, tags, links,
    test_names, short_description, email_address, create_time)
    VALUES
    """
    r = insert_click(db, query, [incident_dict])
    optimize_table(db, tblname="incidents")
    
    setnocacheresponse(response)
    return OONIFindingsUpdateResponse(r=r, id=incident_id)


@router.post(
    "/v1/incidents/update",
    dependencies=[Depends(role_required(["admin", "user"]))],
    tags=["oonifindings"],
    response_model=OONIFindingsUpdateResponse    
)
def update_oonifinding(
    update_request: OONIFindingCreateUpdate,
    response: Response,
    authorization: str = Header("authorization"),
    db=Depends(get_clickhouse_session),
    token=Depends(role_required(["admin", "user"])),
    settings=Depends(get_settings)
):
    """
    Update an incident
    """ 
    incident_id = update_request.incident_id 
    if token["role"] != "admin":
        verify_user(
            db,
            authorization=authorization,
            jwt_encryption_key=settings.jwt_encryption_key,
            incident_id=incident_id,
            email_address=update_request.email_address,
            key=settings.account_id_hashing_key,
        )
        
        if update_request.published is True:
            raise HTTPException(status_code=400, detail="Not enough permissions to publish")

    update_request.creator_account_id = get_account_id_or_raise(
        authorization, jwt_encryption_key=settings.jwt_encryption_key
    ) 
    incident_dict = prepare_incident_dict(update_request)

    log.info(f"Updating incident {incident_id}")

    insert_query = """INSERT INTO incidents
    (id, start_time, end_time, creator_account_id, reported_by, title,
    text, event_type, published, CCs, ASNs, domains, tags, links,
    test_names, short_description, email_address, create_time)
    VALUES
    """
    r = insert_click(db, insert_query, [incident_dict])
    log.debug(f"Result: {r}")
    optimize_table(db, tblname="incidents")
    
    setnocacheresponse(response)
    return OONIFindingsUpdateResponse(r=r, id=incident_id)


@router.post(
      "/v1/incidents/delete",
      tags=["oonifindings"],
)
def delete_oonifinding(
    delete_request: OONIFindingWithMail,
    response: Response,
    authorization: str = Header("authorization"),
    token=Depends(role_required(["admin", "user"])),
    db=Depends(get_clickhouse_session),
    settings=Depends(get_settings)
):
    """
    Delete an incident
    """
    assert delete_request
    incident_id = delete_request.incident_id 
    if token["role"] != "admin":
        try:
            verify_user(
                db,
                authorization=authorization,
                jwt_encryption_key=settings.jwt_encryption_key,
                incident_id=incident_id,
                email_address=delete_request.email_address,
                key=settings.account_id_hashing_key,
            )
        except:
            raise 
        
    query = "ALTER TABLE incidents DELETE WHERE id = %(incident_id)s"
    r = raw_query(db, query, {"incident_id": incident_id})
    optimize_table(db, "incidents")
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
    db=Depends(get_clickhouse_session),
):
    """
    Publish/Unpublish an incident.
    """
    if action not in ("publish", "unpublish"):
        raise HTTPException(status_code=400, detail="Invalid query action")

    assert publish_request
    incident_id = publish_request.incident_id
    
    query = "SELECT * FROM incidents FINAL WHERE id = %(incident_id)s"
    q = query_click(db, query, {"incident_id": incident_id})
    if len(q) < 1:
        raise HTTPException(status_code=404, detail="Incident not found")
    incident_dict = q[0]
    incident_dict["published"] = bool(action == "publish")

    insert_query = """INSERT INTO incidents
    (id, start_time, end_time, creator_account_id, reported_by, title,
    text, event_type, published, CCs, ASNs, domains, tags, links,
    test_names, short_description, email_address, create_time)
    VALUES
    """
    r = insert_click(db, insert_query, [incident_dict])
    log.debug(f"Result: {r}")
    optimize_table(db, tblname="incidents")
    
    setnocacheresponse(response)
    return OONIFindingsUpdateResponse(r=r, id=incident_id)
