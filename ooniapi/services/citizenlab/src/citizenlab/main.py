import logging
from typing import Optional
from contextlib import asynccontextmanager
from urllib.request import urlopen

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from fastapi_utils.tasks import repeat_every

from pydantic import BaseModel

from prometheus_fastapi_instrumentator import Instrumentator


from .routers import admin, v1

from .dependencies import get_postgresql_session, get_clickhouse_session, SettingsDep
from .common.dependencies import get_settings
from .common.config import Settings
from .common.version import get_build_label
from .common.metrics import mount_metrics
from .common.clickhouse_utils import query_click
from .common.errors import BaseOONIException
from .__about__ import VERSION

log = logging.getLogger(__name__)

pkg_name = "citizenlab"

build_label = get_build_label(pkg_name)


@asynccontextmanager
async def lifespan(
    app: FastAPI,
    test_settings: Optional[Settings] = None,
    repeating_tasks_active: bool = True,
):
    # Use the test settings in tests to mock parameters
    settings = test_settings or get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper()))
    mount_metrics(app, instrumentor.registry)

    if repeating_tasks_active:
        await setup_repeating_tasks(settings)

    yield


async def setup_repeating_tasks(settings: Settings):
    # Call all repeating tasks here to make them start
    # See: https://fastapi-utils.davidmontague.xyz/user-guide/repeated-tasks/
    await update_geoip_task()


app = FastAPI(lifespan=lifespan)

# add a custom exception handler that places the err_args and err_str keys in
# the top level object for API compatibility with older versions
@app.exception_handler(BaseOONIException)
async def ooni_exception_handler(request, exc: BaseOONIException):
    # NOTE: content is same as BaseOONIException.detail
    content = {
        "description": exc.description,
        "err_args": exc.err_args,
        "err_str": exc.err_str
    }
    return JSONResponse(status_code=exc.status_code, content=content)

instrumentor = Instrumentator().instrument(
    app, metric_namespace="ooniapi", metric_subsystem="citizenlab"
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https://[-A-Za-z0-9]+(\.test)?\.ooni\.(org|io)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin.router, prefix="/api")
app.include_router(v1.router, prefix="/api")


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
    settings: SettingsDep,
    db=Depends(get_postgresql_session),
    clickhouse=Depends(get_clickhouse_session),
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
        response = urlopen(settings.fastpath_url)
        assert (
            response.status == 200
        ), "Unexpected status trying to connect to fastpath: " + str(response.status)
    except Exception as exc:
        log.error(str(exc))
        errors.append("fastpath_connection_error")

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
    return {"msg": "hello from citizenlab"}
