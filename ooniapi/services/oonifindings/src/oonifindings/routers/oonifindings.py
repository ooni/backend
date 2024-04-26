"""
OONIFindings incidents management
"""

from datetime import datetime, date, timezone
from typing import List, Dict
import logging

from clickhouse_driver import Client as Clickhouse
from fastapi import APIRouter, Depends, Header, Response, HTTPException

from pydantic import Field

from ..common.routers import BaseModel
from ..common.dependencies import get_settings, role_required
from ..common.auth import (
    hash_email_address,
    get_account_id_or_raise,
    get_account_id_or_none, 
    get_client_role
)
from ..common.exceptions import InvalidRequest, OwnershipPermissionError, BaseOONIException
from ..common.utils import setnocacheresponse, generate_random_intuid
from ..common.clickhouse_utils import query_click, raw_query, insert_click, optimize_table
from ..dependencies import get_clickhouse_session

log = logging.getLogger(__name__)

router = APIRouter()


def utcnow_seconds():
    return datetime.now(timezone.utc).replace(microsecond=0)


class OONIFindingBase(BaseModel):
    incident_id: str 
    title: str = Field(
        default="", title="title of the ooni finding"
    )
    short_description: str = Field(
        default="", title="short description of the ooni finding"
    )
    start_time: datetime = Field(
        description="time when the ooni finding started"
    )
    create_time: datetime = Field(
        description="time when the ooni finding report was created"
    )
    reported_by: str = Field(
        default="", title="name of the ooni finding reporter"
    )
    email_address: str = Field(
        default="", title="email address of ooni finding reporter"
    )
    text: str = Field(
        default="", title="content of the ooni finding report"
    )
    published: bool = Field(
        default=False, title="binary check if event is published" 
    )
    event_type: str = Field(
        default="", title="type of ooni finding event"
    )
    ASNs: List[int] = Field(
        default=[], description="list of ASNs associate with the ooni finding"
    )
    CCs: List[str] = Field(
        default=[], description="list of country codes associated with the ooni finding"
    )
    tags: List[str] = Field(
        default=[], description="tags associated with the ooni finding"
    )
    test_names: List[str] = Field(
        default=[], description="ooni tests associated with the ooni finding"
    )
    domains: List[str] = Field(
        default=[], description="list of domains associated with the ooni finding"
    )
    links: List[str] = Field(
        default=[], description="links associated with the ooni finding"
    )


class OONIFinding(OONIFindingBase):
    update_time: datetime = Field(
        description="time when the ooni findings incident was last updated"
    )
    end_time: datetime = Field(
        description="time when the ooni findings incident ended"
    )
    mine: bool = Field(
        default=False, title="check to see if the client account ID matches the creator account ID"
    )


class OONIFindingIncident(BaseModel):
    incident: OONIFinding


class OONIFindings(BaseModel):
    incidents: List[OONIFinding]


class OONIFindingUpdate(OONIFindingBase):
    pass


@router.get(
    "/v2/incidents/search",
    tags=["oonifindings"],
    response_model = OONIFindings
)
def search_list_incidents(
    only_mine: bool,
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
            return OONIFindings(incidents=[])
        where += "\nAND creator_account_id = %(account_id)s"

    if account_id is None:
        # non-published incidents are not exposed to anon users
        where += "\nAND published = 1"
        query_params["account_id"] = "never-match"
    else:
        query_params["account_id"] = account_id

    query = f"""SELECT id, update_time, start_time, end_time, reported_by,
    title, event_type, published, CCs, ASNs, domains, tags, test_names,
    links, short_description, email_address, create_time, creator_account_id 
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
    # TODO(decfox): try using OONIFindings.validate_model to populate model
    for incident in incidents:
        incident_model = OONIFinding(
            incident_id=incident.id,
            update_time=incident.update_time,
            start_time=incident.start_time,
            end_time=incident.end_time,
            reported_by=incident.reported_by,
            title=incident.title,
            text=incident.text,
            event_type=incident.event_type,
            published=incident.published,
            CCs=incident.CCs,
            ASNs=incident.ASNs,
            domains=incident.domains,
            tags=incident.tags,
            test_names=incident.test_names,
            links=incident.links,
            short_description=incident.short_description,
            email_address=incident.email_address,
            create_time=incident.create_time,
            mine=account_id == incident.creator_account_id,
        )
        incident_models.append(incident_model)
    return OONIFindings(incidents=incident_models)


@router.get(
    "/v2/incidents/show/{incident_id}",
    tags=["oonifindings"],
    response_model=OONIFinding
)
def show_incident(
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
    links, short_description, email_address, create_time, creator_account_id
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
    # TODO(decfox): try using OONIFinding.validate_model to populate model
    incident_model = OONIFinding(
        incident_id=incident.id,
        update_time=incident.update_time,
        start_time=incident.start_time,
        end_time=incident.end_time,
        reported_by=incident.reported_by,
        title=incident.title,
        text=incident.text,
        event_type=incident.event_type,
        published=incident.published,
        CCs=incident.CCs,
        ASNs=incident.ASNs,
        domains=incident.domains,
        tags=incident.tags,
        test_names=incident.test_names,
        links=incident.links,
        short_description=incident.short_description,
        email_address=incident.email_address,
        create_time=incident.create_time,
        mine=account_id == incident.creator_account_id,
    )
    return OONIFindingIncident(incident=incident_model)


def prepare_incident_dict(
    authorization: str,
    jwt_encryption_key: str,
    update_incident: OONIFindingUpdate
) -> Dict:
    d = update_incident.dict()
    d["creator_account_id"] = get_account_id_or_raise(authorization, jwt_encryption_key=jwt_encryption_key)
    exp = [
        "ASNs",
        "CCs",
        "create_time",
        "creator_account_id",
        "domains",
        "email_address",
        "end_time",
        "event_type",
        "id",
        "links",
        "published",
        "reported_by",
        "short_description",
        "start_time",
        "tags",
        "test_names",
        "text",
        "title",
    ]
    if sorted(d) != exp:
        log.debug(f"Invalid incident update request. Keys: {sorted(d)}")
        raise InvalidRequest()

    ts_fmt = "%Y-%m-%dT%H:%M:%SZ"
    d["start_time"] = datetime.strptime(d["start_time"], ts_fmt)
    d["create_time"] = datetime.strptime(d["create_time"], ts_fmt)
    if d["end_time"] is not None:
        d["end_time"] = datetime.strptime(d["end_time"], ts_fmt)
        delta = d["end_time"] - d["start_time"]
        if delta.total_seconds() < 0:
            raise InvalidRequest()

    if not d["title"] or not d["text"]:
        log.debug("Invalid incident update request: empty title or desc")
        raise InvalidRequest()

    return d


def mismatched_email_addr(
    authorization: str,
    jwt_encryption_key: str,
    email_address: str,
    hashing_key: str
) -> bool:
    account_id = get_account_id_or_raise(authorization, jwt_encryption_key=jwt_encryption_key)
    hashed = hash_email_address(email_address, hashing_key=hashing_key)
    if account_id == hashed:
        return False

    log.info(f"Email mismatch {hashed} {account_id}")
    return True


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


class OONIFindingsUpdate(BaseModel):
    r: int = Field(
        default=0, title="result of the update operation"
    )
    incident_id: str = Field(
        default="", title="incident id of the updated ooni finding"
    )


@router.post(
    "/v2/incidents/{action}",
    dependencies=[Depends(role_required(["admin", "user"]))],
    tags=["oonifindings"],
    response_model=OONIFindingsUpdate
)
def post_update_incident(
    action: str,
    update_incident: OONIFindingUpdate,
    response: Response,
    authorization: str = Header("authorization"),
    db=Depends(get_clickhouse_session),
    settings=Depends(get_settings)
):
    """
    Create/update/publish/unpublish/delete an incident.
    The `action` value can be "create", "update", "delete", "publish", "unpublish".
    The `id` value is returned by the API when an incident is created.
    It should be set by the caller for incident update or deletion.
    """
    if action not in ("create", "update", "delete", "publish", "unpublish"):
        raise HTTPException(status_code=400, details="Invalid action encountered") 
    assert update_incident

    client_role = get_client_role(authorization, jwt_encryption_key=settings.jwt_encryption_key)

    incident_dict = dict()
    if action == "create":
        incident_id = str(generate_random_intuid(collector_id=settings.collector_id))
        if client_role != "admin" and mismatched_email_addr(
            authorization,
            jwt_encryption_key=settings.jwt_encryption_key,
            email_address=update_incident.email_address,
            hashing_key=settings.account_id_hashing_key
        ):
            raise InvalidRequest()
        
        if client_role != "admin" and update_incident.published:
            raise InvalidRequest()

        update_incident.incident_id = incident_id 
        update_incident.create_time = utcnow_seconds() 
        incident_dict = prepare_incident_dict(
            authorization, jwt_encryption_key=settings.jwt_encryption_key, update_incident=update_incident
        )
        log.info(f"Creating incident {incident_id}")

    else: 
        incident_id = update_incident.incident_id
        # When incident already exists:
        assert incident_id

        # Only admin or incident owner can make changes
        if client_role != "admin":
            if user_cannot_update(
                db, authorization, jwt_encryption_key=settings.jwt_encryption_key, incident_id=incident_id
            ):
                raise OwnershipPermissionError()

            # ...while using the right email addr
            if mismatched_email_addr(
                authorization, 
                jwt_encryption_key=settings.jwt_encyption_key, 
                email_address=update_incident.email_address,
                hashing_key=settings.account_id_hashing_key
            ):
                raise InvalidRequest()
    
        if action == "delete":
            # TODO: switch to faster deletion with new db version
            query = "ALTER TABLE incidents DELETE WHERE id = %(incident_id)s"
            r = raw_query(db, query, {"incident_id": incident_id})
            optimize_table("incidents")
            setnocacheresponse(response)
            # TODO: replace with response_model
            return OONIFindingsUpdate(r=r, incident_id=incident_id)

        if action == "update":
            # Only admin can publish
            if client_role != "admin" and update_incident.published:
                raise InvalidRequest()

            incident_dict = prepare_incident_dict(
                authorization, jwt_encryption_key=settings.jwt_encryption_key, update_incident=update_incident
            )
            log.info(f"Updating incident {incident_id}")

        elif action in ("publish", "unpublish"):
            if client_role != "admin":
                raise InvalidRequest()
            
            query = "SELECT * FROM incidents FINAL WHERE id = %(incident_id)s"
            q = query_click(db, query, {"incident_id": incident_id})
            if len(q) < 1:
                return HTTPException(status_code=404, detail="Incident not found")
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
    return OONIFindingsUpdate(r=r, incident_id=incident_id)
        