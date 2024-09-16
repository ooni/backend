import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from pydantic import BaseModel

from prometheus_fastapi_instrumentator import Instrumentator

from . import models
from .routers import v2

from .dependencies import get_postgresql_session
from .common.dependencies import get_settings
from .common.version import get_build_label
from .common.metrics import mount_metrics
from .__about__ import VERSION

pkg_name = "ooniprobe"

build_label = get_build_label(pkg_name)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper()))
    mount_metrics(app, instrumentor.registry)
    yield


app = FastAPI(lifespan=lifespan)

instrumentor = Instrumentator().instrument(
    app, metric_namespace="ooniapi", metric_subsystem="ooniprobe"
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex="^https://[-A-Za-z0-9]+(\.test)?\.ooni\.(org|io)$",
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v2.router, prefix="/api")


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
):
    errors = []
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
    #return RedirectResponse("/docs")
    return {
        "msg": "hello from ooniprobe"
    }
