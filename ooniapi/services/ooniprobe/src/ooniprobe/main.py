import logging
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fastapi_utils.tasks import repeat_every

from pydantic import BaseModel

from prometheus_fastapi_instrumentator import Instrumentator


from . import models
from .routers.v2 import vpn
from .routers.v1 import probe_services

from .download_geoip import try_update
from .dependencies import get_postgresql_session, get_clickhouse_session
from .common.dependencies import get_settings
from .common.config import Settings
from .common.version import get_build_label
from .common.metrics import mount_metrics
from .common.clickhouse_utils import query_click
from .__about__ import VERSION

log = logging.getLogger(__name__)

pkg_name = "ooniprobe"

build_label = get_build_label(pkg_name)


@asynccontextmanager
async def lifespan(app: FastAPI, test_settings: Optional[Settings] = None):
    # Use the test settings in tests to mock parameters
    settings = test_settings or get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper()))
    mount_metrics(app, instrumentor.registry)

    await setup_repeating_tasks(settings)

    print("Server initialization finished")
    yield

async def setup_repeating_tasks(settings : Settings):
    # Call all repeating tasks here to make them start
    # See: https://fastapi-utils.davidmontague.xyz/user-guide/repeated-tasks/
    await update_geoip_task()

@repeat_every(seconds = 5, logger=log)
def update_geoip_task():
    settings = get_settings()
    try_update(settings.geoip_db_dir)

app = FastAPI(lifespan=lifespan)

instrumentor = Instrumentator().instrument(
    app, metric_namespace="ooniapi", metric_subsystem="ooniprobe"
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex="^https://[-A-Za-z0-9]+(\.test)?\.ooni\.(org|io)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(vpn.router, prefix="/api")
app.include_router(probe_services.router, prefix="/api")




@app.get("/version")
async def version():
    return {"version": VERSION, "build_label": build_label}


class HealthStatus(BaseModel):
    status: str
    errors: list[str] = []
    version: str
    build_label: str


@app.get("/health")
async def health(
    settings=Depends(get_settings),
    db=Depends(get_postgresql_session),
    clickhouse=Depends(get_clickhouse_session),
):
    errors = []
    try:
        query = """SELECT *
        FROM fastpath FINAL
        """
        query_click(db=clickhouse, query=query, query_params={})
    except Exception as e:
        errors.append("clickhouse_error")
        log.error(e)

    try:
        db.query(models.OONIProbeVPNProvider).limit(1).all()
    except Exception as exc:
        print(exc)
        errors.append("db_error")

    if settings.jwt_encryption_key == "CHANGEME":
        errors.append("bad_jwt_secret")

    if settings.prometheus_metrics_password == "CHANGEME":
        errors.append("bad_prometheus_password")

    status = "ok"
    if len(errors) > 0:
        status = "fail"

    return {
        "status": status,
        "errors": errors,
        "version": VERSION,
        "build_label": build_label,
    }


@app.get("/")
async def root():
    # TODO(art): fix this redirect by pointing health monitoring to /health
    # return RedirectResponse("/docs")
    return {"msg": "hello from ooniprobe"}
