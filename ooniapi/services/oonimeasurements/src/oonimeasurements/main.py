import logging
from functools import lru_cache

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel
from sqlalchemy import Engine, create_engine, text
from starlette.concurrency import run_in_threadpool

from .common.clickhouse_utils import async_query_click
from .common.config import Settings
from .common.dependencies import get_clickhouse_session, get_settings
from .common.metrics import mount_metrics
from .common.rate_limit_quotas import RateLimiterMiddleware
from .common.version import get_build_label, get_pkg_version
from .routers.data import (
    aggregate_analysis,
    aggregate_observations,
    list_analysis,
    list_observations,
)
from .routers.v1 import aggregation, measurements
from .routers import private

pkg_name = "oonimeasurements"

pkg_version = get_pkg_version(pkg_name)
build_label = get_build_label(pkg_name)

log = logging.getLogger(__name__)


@lru_cache
def get_health_postgresql_engine(postgresql_url: str) -> Engine:
    # PG engine used for the health check specifically.
    # Created once, and with a timeout so an unreachable database doesn't make
    # the health check hang.
    #
    # pool_pre_ping replaces dead connections
    return create_engine(
        postgresql_url, pool_pre_ping=True, connect_args={"connect_timeout": 2}
    )


def check_postgresql(postgresql_url: str) -> None:
    with get_health_postgresql_engine(postgresql_url).connect() as conn:
        conn.execute(text("SELECT 1"))


def create_app() -> FastAPI:
    settings = get_settings()

    logging.basicConfig(level=getattr(logging, settings.log_level.upper()))

    app = FastAPI()

    app.add_middleware(
        CORSMiddleware,
        # allow from observable notebooks
        allow_origin_regex=r"^https://[-A-Za-z0-9]+(\.(test|dev))?\.ooni\.(org|io)$|^https://.*\.observableusercontent\.com$",
        # allow_origin_regex="^https://[-A-Za-z0-9]+(\.test)?\.ooni\.(org|io)$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app


def setup_router(app: FastAPI):
    class HealthStatus(BaseModel):
        status: str
        errors: list[str] = []
        version: str
        build_label: str

    app.include_router(measurements.router, prefix="/api")
    app.include_router(aggregation.router, prefix="/api")
    app.include_router(list_analysis.router, prefix="/api")
    app.include_router(list_observations.router, prefix="/api")
    app.include_router(aggregate_observations.router, prefix="/api")
    app.include_router(aggregate_analysis.router, prefix="/api")
    app.include_router(private.router, prefix="/api")

    instrumentor = Instrumentator().instrument(
        app, metric_namespace="ooniapi", metric_subsystem="oonimeasurements"
    )
    mount_metrics(app, instrumentor.registry)

    @app.get("/version")
    async def version():
        return {"version": pkg_version, "build_label": build_label}

    # TODO(decfox): Add minimal health check functionality
    @app.get("/health")
    async def health(
        settings=Depends(get_settings),
        db=Depends(get_clickhouse_session),
    ):
        errors = []

        try:
            # Only checks that ClickHouse answers: the load balancer calls this
            # hundreds of thousands of times a week
            query = "SELECT 1"
            await async_query_click(db=db, query=query, query_params={})
        except Exception as exc:
            log.error(exc)
            errors.append("db_error")

        # Postgres is only needed to authenticate API token users. It's reported
        # as a warning instead of an error, because failing the health check
        # would make the load balancer take down the API for everyone
        warnings = []
        try:
            await run_in_threadpool(check_postgresql, settings.postgresql_url)
        except Exception as exc:
            log.error(exc)
            warnings.append("postgresql_error")

        if settings.jwt_encryption_key == "CHANGEME":
            err = "bad_jwt_secret"
            log.error(err)
            errors.append(err)

        if settings.prometheus_metrics_password == "CHANGEME":
            err = "bad_prometheus_password"
            log.error(err)
            errors.append(err)

        status, code = ("ok", 200) if len(errors) == 0 else ("fail", 503)
        result = {
            "status": status,
            "errors": errors,
            "warnings": warnings,
            "version": pkg_version,
            "build_label": build_label,
        }

        if len(errors):
            log.error(f"Health check errors detected: {errors}")

        return JSONResponse(content=result, status_code=code)

    @app.get("/")
    async def root():
        return {"message": "Hello OONItarian"}


def setup_rate_limiter(app: FastAPI, settings: Settings):
    # This function makes this setup mockable on tests
    app.add_middleware(
        RateLimiterMiddleware,
        valkey_url=settings.valkey_url,
        hashing_key=settings.account_id_hashing_key,
        rate_limits=settings.rate_limits,
        whitelisted_ipaddrs=settings.rate_limits_whitelisted_ipaddrs,
        unmetered_pages=settings.rate_limits_unmetered_pages,
        postgresql_url=settings.postgresql_url,
        # Token usage isn't recorded without a clickhouse url
        clickhouse_url=settings.clickhouse_url if settings.api_token_usage_enabled else None,
        api_token_cache_ttl=settings.api_token_cache_ttl,
    )


settings = get_settings()

app = create_app()
setup_router(app)
setup_rate_limiter(app, settings)
