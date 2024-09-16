import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel

from prometheus_fastapi_instrumentator import Instrumentator

from . import models
from .routers import v1

from .dependencies import get_settings, get_postgresql_session
from .common.version import get_build_label, get_pkg_version
from .common.metrics import mount_metrics

pkg_name = "oonifindings"

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
    app, metric_namespace="ooniapi", metric_subsystem="oonifindings"
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex="^https://[-A-Za-z0-9]+(\.test)?\.ooni\.(org|io)$",
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1.router, prefix="/api")


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
    db=Depends(get_postgresql_session),
):
    errors = []

    try:
        db.query(models.OONIFinding).limit(1).all()
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
