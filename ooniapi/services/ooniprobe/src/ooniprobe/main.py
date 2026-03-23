import logging
from contextlib import asynccontextmanager
from typing import Optional

import boto3
import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi_utils.tasks import repeat_every
from ooniauth_py import ServerState
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel

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
    app.state.fastpath_client = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
    )
    app.state.s3_client = boto3.client("s3")

    yield

    await app.state.fastpath_client.aclose()


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
        resp = await app.state.fastpath_client.get(settings.fastpath_url)
        assert resp.status_code == 200, (
            "Unexpected status trying to connect to fastpath: " + str(resp.status_code)
        )
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
    except Exception as e:
        errors.append("anonc_manifest_unreachable")
        log.error(f"Error retrieving manifest: {e}")

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


def check_ooniauth_health():
    """
    Raise an error if there's an error with the ooniauth library
    """
    # should be able to handle a credential sign request when restoring from hard-coded credentials

    # These keys are innocuous, just created to test this
    secret_key = "ASDFF9zKec3Num0nunVOWSTDtIaePd0i6b9q+csSYp03BSD2MaFqUpjJ1wszMkD6g6wswKiR2pj8/0+VUtpGJfzBAAMgvlT+W0/NPbpKDbwAQdcsU54k51vMGMzNaqAO+fza9g8gAgs3rHVvfZgdy37NRUpuKBtS4C8C+pF4N0RRSn+RXwcgHo/rhjaggjAigpJ4gTfzktpQnWdxo9sBMLzy7Ugp0QQ="
    public_parameters = "ASAQLXA3nuXAE3EqWdGPCOhdnuHUQvzveiNbk0AxuLOnHwEgPDK8zi0QEp5itXAuRHm4EI/niFnDlJecii1xrisjORgDIKYlBK2/NgBDBuPkUq7VscpReP2FXr3xYGzA5DrffE9YIPTUjn1pq0qhMoD/oJfJwovgkv5otvOCBsxLGTZqzIcvICRQeuUNqnxEfI6BSCLUqa3+++AjEqqctoKggsqMwYAZ"
    sign_request = "IGZhzXTHZrN9QwSmiy5P/n2mnEpCMSHpQGO/lhe+fw9xYLJTMavNnWs/qtak2XEySicyGtQS3yuO1N/6AQ3A4xl2DHx0czkl91bbp/ZVgsgF+JdN5s4WHbA/uLd2rAOEvEEB4zf0pCu9JU13BRh1vSnNJIXNXRlpRbsyIW3NclGdPQ=="

    server = ServerState.from_creds(public_parameters, secret_key)
    server.handle_registration_request(sign_request)
