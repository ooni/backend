import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel

from prometheus_fastapi_instrumentator import Instrumentator

from .routers.v1 import aggregation
from .routers.v1 import measurements
from .routers.data import (
    list_analysis,
    list_observations,
    aggregate_observations,
    aggregate_analysis,
)

from .dependencies import get_clickhouse_session
from .common.dependencies import get_settings
from .common.version import get_build_label, get_pkg_version
from .common.clickhouse_utils import query_click
from .common.metrics import mount_metrics


pkg_name = "oonimeasurements"

pkg_version = get_pkg_version(pkg_name)
build_label = get_build_label(pkg_name)

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper()))
    mount_metrics(app, instrumentor.registry)
    yield


app = FastAPI(lifespan=lifespan)

instrumentor = Instrumentator().instrument(
    app, metric_namespace="ooniapi", metric_subsystem="oonimeasurements"
)

app.add_middleware(
    CORSMiddleware,
    # allow from observable notebooks
    allow_origin_regex="^https://[-A-Za-z0-9]+(\.test)?\.ooni\.(org|io)$|^https://.*\.observableusercontent\.com$",
    #allow_origin_regex="^https://[-A-Za-z0-9]+(\.test)?\.ooni\.(org|io)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(measurements.router, prefix="/api")
app.include_router(aggregation.router, prefix="/api")
app.include_router(list_analysis.router, prefix="/api")
app.include_router(list_observations.router, prefix="/api")
app.include_router(aggregate_observations.router, prefix="/api")
app.include_router(aggregate_analysis.router, prefix="/api")


@app.get("/version")
async def version():
    return {"version": pkg_version, "build_label": build_label}


class HealthStatus(BaseModel):
    status: str
    errors: list[str] = []
    version: str
    build_label: str


# TODO(decfox): Add minimal health check functionality
@app.get("/health")
async def health(
    settings=Depends(get_settings),
    db=Depends(get_clickhouse_session),
):
    errors = []

    try:
        query = """
        SELECT COUNT()
        FROM fastpath
        WHERE measurement_start_time < NOW() AND measurement_start_time > NOW() - INTERVAL 3 HOUR
        """
        query_click(db=db, query=query, query_params={})
    except Exception as exc:
        log.error(exc)
        errors.append("db_error")

    if settings.jwt_encryption_key == "CHANGEME":
        err = "bad_jwt_secret"
        log.error(err)
        errors.append(err)

    if settings.prometheus_metrics_password == "CHANGEME":
        err = "bad_prometheus_password"
        log.error(err)
        errors.append(err)

    status = "ok"
    if len(errors) > 0:
        status = "fail"

    return {
        "status": status,
        "errors": errors,
        "version": pkg_version,
        "build_label": build_label,
    }


@app.get("/")
async def root():
    return {"message": "Hello OONItarian"}
