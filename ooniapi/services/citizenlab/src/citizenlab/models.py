from pydantic import Field
from typing import Any, Dict, List, Optional

from citizenlab.common.routers import BaseModel


class PullRequestResponse(BaseModel):
    pr_id: str


class Entry(BaseModel):
    category_code: str = Field(description="Category code of the URL entry.")
    url: str = Field(description="The URL to be submitted.")
    date_added: str = Field(description="Date when the entry was added.")
    notes: str = Field(description="Any additional notes regarding the entry.")
    source: str = Field(description="Any additional notes regarding the entry.")


class UrlPriority(BaseModel):
    # XXX: it is unclear which fields are required to do an update
    # XXX: it looks like only domain and URL and cc and category_code are part of the
    # WHERE clause but the INTEG-TEST fields do not specifiy all of these fields
    # so the validator fails
    category_code: str = Field(..., description="The category code associated with the URL.")
    cc: str = Field(..., description="Country code that the URL is relevant to.")
    domain: str = Field(..., description="The domain of the URL.")
    url: str = Field(..., description="The actual URL to be prioritized.")
    priority: int = Field(..., description="The priority number for the URL. Higher numbers indicate higher priority.")


class ListUrlPriorityResponse(BaseModel):
    rules: List[UrlPriority] = Field(..., description="The list of UrlPriority items")


class UrlSubmissionUpdateRequest(BaseModel):
    country_code: str = Field(..., description="The country code for the submission.")
    comment: str = Field(..., description="Comment regarding the submission.")
    old_entry: Optional[Entry] = Field(None, description="The old entry to validate against.")
    new_entry: Optional[Entry] = Field(None, description="New entry to create or update.")


class UrlSubmissionResponse(BaseModel):
    updated_entry: Optional[Entry] = Field(None, description="The updated URL entry after processing.")


class UpdateUrlPriorityRequest(BaseModel):
    old_entry: Optional[UrlPriority] = Field(None, description="Existing URL priority rule to update.")
    new_entry: Optional[UrlPriority] = Field(None, description="New URL priority rule to create or replace existing rule.")


class TestListResponse(BaseModel):
    test_list: Optional[List[Dict[str, Any]]] = Field(None, description="The fetched test list.")
    changes: Dict[str, Any] = Field(description="The changes related to the test list.")
    state: str = Field(description="The current sync state.")
    pr_url: Optional[str] = Field(None, description="The pull request URL, if applicable.")
