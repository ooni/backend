import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel

from prometheus_fastapi_instrumentator import Instrumentator

from . import models
from .routers import v2

from .common.dependencies import get_settings, SettingsDep, ClickhouseDep, PostgresDep
from .common.version import get_build_label, get_pkg_version
from .common.version import get_build_label, get_pkg_version
from .common.metrics import mount_metrics
from .common.clickhouse_utils import query_click

log = logging.getLogger(__name__)

pkg_name = "oonirun"

pkg_version = get_pkg_version(pkg_name)
build_label = get_build_label(pkg_name)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper()))
    mount_metrics(app, instrumentor.registry)
    yield


app = FastAPI(lifespan=lifespan)

instrumentor = Instrumentator().instrument(
    app, metric_namespace="ooniapi", metric_subsystem="oonirun"
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https://[-A-Za-z0-9]+(\.test)?\.ooni\.(org|io)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v2.router, prefix="/api")


@app.get("/version")
async def version():
    return {"version": pkg_version, "build_label": build_label}


class HealthStatus(BaseModel):
    status: str
    errors: list[str] = []
    version: str
    build_label: str


@app.get("/health")
async def health(
    settings: SettingsDep,
    db: PostgresDep,
    clickhouse: ClickhouseDep,
):
    errors = []

    try:
        query = """
        SELECT COUNT()
        FROM fastpath
        WHERE measurement_start_time < NOW() AND measurement_start_time > NOW() - INTERVAL 3 HOUR
        """
        query_click(db=clickhouse, query=query, query_params={})
    except Exception as e:
        errors.append("clickhouse_error")
        log.error(e)

    try:
        db.query(models.OONIRunLink).limit(1).all()
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
        "status":   status,
        "errors":   errors,
        "version":  pkg_version,
        "build_label": build_label,
    }


@app.get("/")
async def root():
    return {"message": "Hello OONItarian!"}
