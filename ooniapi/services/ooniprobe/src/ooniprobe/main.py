import logging
from contextlib import asynccontextmanager
from typing import Optional

import boto3
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import requests
from fastapi.middleware.cors import CORSMiddleware
from fastapi_utils.tasks import repeat_every
from ooniauth_py import ServerState
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool

from . import models
from .__about__ import VERSION
from .common.clickhouse_utils import query_click
from .common.config import Settings
from .common.dependencies import ClickhouseDep, SettingsDep, get_settings
from .common.metrics import mount_metrics
from .common.version import get_build_label
from .dependencies import PostgresSessionDep, S3ClientDep, get_manifest
from .download_geoip import try_update
from .routers import bouncer, prio_crud, reports
from .routers.v1 import probe_services
from .routers.v2 import vpn

log = logging.getLogger(__name__)

pkg_name = "ooniprobe"

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

    init_ooniauth()

    if repeating_tasks_active:
        await setup_repeating_tasks(settings)
    app.state.s3_client = boto3.client("s3")

    yield


def init_ooniauth():
    # Creating a server state from scratch initializes the underlying crypto library
    ServerState()


async def setup_repeating_tasks(settings: Settings):
    # Call all repeating tasks here to make them start
    # See: https://fastapi-utils.davidmontague.xyz/user-guide/repeated-tasks/
    await update_geoip_task()


@repeat_every(seconds=3600, logger=log)  # Every hour
def update_geoip_task():
    settings = get_settings()
    try_update(settings.geoip_db_dir)


app = FastAPI(lifespan=lifespan)

instrumentor = Instrumentator().instrument(
    app, metric_namespace="ooniapi", metric_subsystem="ooniprobe"
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https://[-A-Za-z0-9]+(\.(test|dev))?\.ooni\.(org|io)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(vpn.router, prefix="/api")
app.include_router(probe_services.router, prefix="/api")
app.include_router(reports.router)
app.include_router(bouncer.router)
app.include_router(prio_crud.router, prefix="/api")


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
    request: Request,
    settings: SettingsDep,
    s3: S3ClientDep,
    db: PostgresSessionDep,
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
        resp = await run_in_threadpool(requests.get, settings.fastpath_url)
        resp.raise_for_status()
    except Exception as exc:
        log.error(str(exc))
        errors.append("fastpath_connection_error")

    try:
        db.query(models.OONIProbeVPNProvider).limit(1).all()
    except Exception as exc:
        print(exc)
        errors.append("db_error")

    try:
        check_ooniauth_health()
    except BaseException as exc:
        log.error(f"Usertauth health error: {exc}")
        errors.append("bad_ooniauth_heatlh")

    if settings.jwt_encryption_key == "CHANGEME":
        errors.append("bad_jwt_secret")

    if settings.prometheus_metrics_password == "CHANGEME":
        errors.append("bad_prometheus_password")

    if settings.anonc_manifest_bucket == "CHANGEME":
        errors.append("bad_manifest_bucket")

    if settings.anonc_manifest_file == "CHANGEME":
        errors.append("bad_manifest_file")

    if settings.anonc_secret_key == "CHANGEME":
        errors.append("bad_anonc_secret_key")

    # Check that you can retrieve the manifest
    try:
        get_manifest(s3, settings.anonc_manifest_bucket, settings.anonc_manifest_file)
    except ValidationError as e: # Bad manifest
        errors.append("bad_anonc_manifest")
        log.error(f"Error parsing manifest file: {e}")
    except Exception as e:
        errors.append("anonc_manifest_unreachable")
        log.error(f"Error retrieving manifest: {e}")

    status, code = ("ok", 200) if len(errors) == 0 else ("fail", 503)
    result = {
        "status": status,
        "errors": errors,
        "version": VERSION,
        "build_label": build_label,
    }


    return JSONResponse(content=result, status_code=code)


@app.get("/")
async def root():
    # TODO(art): fix this redirect by pointing health monitoring to /health
    # return RedirectResponse("/docs")
    return {"msg": "hello from ooniprobe"}


def check_ooniauth_health():
    """
    Raise an error if there's an error with the ooniauth library
    """
    # should be able to handle a credential sign request when restoring from hard-coded credentials

    # These keys are innocuous, just created to test this
    secret_key = "AUGQSPO28+QLlf8fKhQjqAD2Ehjn0Q471Yavs7n0qsYJ0nnZ1G/Y2LqvjC3Stq0o9Ka6lB2Xq9EDIEOFhQsjbQQDAAAAAAAAAGk422WHZ5MEPCTMbaj4sDvW27Yvl+pRzDuuTasyEpIDRCEzgL3tIOErnbYtca/68gHUxIfXRCDtcSMEvxVhSAynRFLeT0pXf5fRFwX4gbzNVgvzh0MthADyh7UUPmj6BQ=="
    public_parameters = "AaJpxHsB+x4axWCrFxohF+ML5inYWbPbVQro9YGxb9NVAcgzlHrnd7PLfwWQe69W3ZLcGe4R/CnbFBwhCfdfvvpCAwAAAAAAAAAkAklNBr7fMUrdkeNT360ZsLTGN8A7kKMX6b60tJ5YCBLJ9QJdwnkp12VHPgND2/chraDFw8snqfq0JDZI2tJ04sqKzWi+y57qzh0HG+pkZ3xe7RceyE4isTs7ZRzriwA="
    sign_request = "6iOCB9U1J7UowHfVGq0zoWiP2zSi7589rqS7bdNBC2NlAAAAAAAAAAPW0h/qB7voDedoLiDttZwawVv7xdlZY7GkbijU+o+RAAIAAAAKx1aegNytJO5oarCsIx0t5FQpqP5Wm54k+ECb9nVh7wqQpREN1uu20ZqgU4iW8XDwzOnw8IfWJBSv7FTaF0ne"

    server = ServerState.from_creds(public_parameters, secret_key)
    server.handle_registration_request(sign_request)
