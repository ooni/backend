from typing import List
import logging

from fastapi import Response, APIRouter

from ..utils import generate_report_id
from ..dependencies import SettingsDep
from ..common.routers import BaseModel
from ..common.utils import setnocacheresponse
from ..common.metrics import timer

router = APIRouter()

log = logging.getLogger(__name__)

class OpenReportRequest(BaseModel):
    """
    Open report
    """
    data_format_version: str
    format: str
    probe_asn: str = "AS0"
    probe_cc: str = "ZZ"
    software_name: str
    software_version: str
    test_name: str = ""
    test_start_time: str
    test_version: str

class OpenReportResponse(BaseModel):
    """
    Open report confirmation
    """
    backend_version: str
    report_id: str
    supported_formats: List[str]


@timer
@router.post("/report", tags=["reports"], response_model=OpenReportResponse)
def open_report(data: OpenReportRequest, response: Response, settings : SettingsDep) -> OpenReportResponse:
    """
    Opens a new report 
    """

    log.info("Open report %r", data.model_dump())
    asn = data.probe_asn.upper()
    if len(asn) > 12 or len(asn) < 3 or not asn.startswith("AS"):
        asn = "AS0"
    try:
        asn_i = int(asn[2:])
    except Exception:
        asn_i = 0

    cc = data.probe_cc.upper().replace("_", "")
    if len(cc) != 2:
        cc = "ZZ"
    test_name = data.test_name.lower()
    rid = generate_report_id(test_name, settings, cc, asn_i)
    resp = OpenReportResponse(backend_version="1.3.5", supported_formats=["yaml", "json"], report_id=rid)
    setnocacheresponse(response)
    return resp