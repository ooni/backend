from fastapi import APIRouter, Depends
from ...common.dependencies import get_settings
from ...common.routers import BaseModel

router = APIRouter(prefix="/v1")

class Example(BaseModel):
    msg : str


# if not versioned, go in the top level path
@router.get("/ooniprobe/hello/", tags=["ooniprobe"])
def probe_login_post(
    settings=Depends(get_settings),
) -> Example:

    return Example(msg="Hello")