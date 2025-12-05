import logging
from typing import List, Optional, Any, Dict
from json.decoder import JSONDecodeError

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import Field, ValidationError

from ooniprobe.common.utils import setnocacheresponse
from ooniprobe.common.routers import BaseModel

router = APIRouter(prefix="/bouncer")

log = logging.getLogger(__name__)


class TestHelperEntry(BaseModel):
    address: str
    type: str
    front: Optional[str] = None


class CollectorEntry(BaseModel):
    address: str
    type: str
    front: Optional[str] = None


class NetTest(BaseModel):
    name: str
    collector: str
    altcollector: List[CollectorEntry] = Field(alias="collector-alternate")
    hashes: Optional[Any] = Field(None, alias="input-hashes")
    helpers: Dict[str, str] = Field(alias="test-helpers")
    althelpers: Dict[str, List[TestHelperEntry]] = Field(alias="test-helpers-alternate")
    version: str


class NetTestRequest(BaseModel):
    name: str
    version: str


class NetTestsRequest(BaseModel):
    nettests: List[NetTestRequest] = Field(alias="net-tests")


class NetTestResponse(BaseModel):
    nettests: List[NetTest] = Field(alias="net-tests")


@router.post(
    "/net-tests",
    tags=["bouncer"],
    response_model=NetTestResponse,
    response_model_exclude_unset=True,
)
async def bouncer_net_tests(
    response: Response,
    request: Request,
) -> Dict[str, List[NetTest]]:

    try:
        j = await request.json()
        m = NetTestsRequest(**j)
    except ValidationError as e:
        raise HTTPException(400, detail=e.errors())
    except JSONDecodeError as e:
        raise HTTPException(400, detail=str(e))
    except Exception as e:
        log.warning("Unexpected Exception:" + str(e))
        raise HTTPException(400, detail=str(e))

    try:
        name = m.nettests[0].name
        version = m.nettests[0].version
    except IndexError:
        raise HTTPException(status_code=400, detail="invalid net-tests request")

    # TODO: load this json from environment or filepath
    j = {
        "net-tests": [
            {
                "collector": "httpo://guegdifjy7bjpequ.onion",
                "collector-alternate": [
                    {"type": "https", "address": "https://ams-pg.ooni.org"},
                    {
                        "front": "dkyhjv0wpi2dk.cloudfront.net",
                        "type": "cloudfront",
                        "address": "https://dkyhjv0wpi2dk.cloudfront.net",
                    },
                ],
                "input-hashes": None,
                "name": name,
                "test-helpers": {
                    "tcp-echo": "37.218.241.93",
                    "http-return-json-headers": "http://37.218.241.94:80",
                    "web-connectivity": "httpo://y3zq5fwelrzkkv3s.onion",
                },
                "test-helpers-alternate": {
                    "web-connectivity": [
                        {"type": "https", "address": "https://wcth.ooni.io"},
                        {
                            "front": "d33d1gs9kpq1c5.cloudfront.net",
                            "type": "cloudfront",
                            "address": "https://d33d1gs9kpq1c5.cloudfront.net",
                        },
                    ]
                },
                "version": version,
            }
        ]
    }
    resp = NetTestResponse(**j)
    setnocacheresponse(response)
    return resp
