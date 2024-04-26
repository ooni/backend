import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel

from prometheus_fastapi_instrumentator import Instrumentator

from .routers import oonifindings

from .dependencies import get_settings, get_clickhouse_session
from .common.version import get_build_label, get_pkg_version
from .common.clickhouse_utils import query_click
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

# TODO: temporarily enable all
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(oonifindings.router, prefix="/api")


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
        query = f"""SELECT id, update_time, start_time, end_time, reported_by,
        title, event_type, published, CCs, ASNs, domains, tags, test_names,
        links, short_description, email_address, create_time, creator_account_id 
        FROM incidents FINAL
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

    if len(errors) > 0:
        raise HTTPException(status_code=400, detail="health check failed")
    
    status = "ok"
    
    return {
        "status": status,
        "errors": errors,
        "version": pkg_version,
        "build_label": build_label,
    }


@app.get("/")
async def root():
    return {"message": "Hello OONItarian"}