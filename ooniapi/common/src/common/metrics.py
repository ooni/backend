import secrets

from typing import Annotated

from fastapi import FastAPI, Response, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .dependencies import get_settings
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    generate_latest,
)

security = HTTPBasic()


def mount_metrics(app: FastAPI, registry: CollectorRegistry):
    def metrics(
        credentials: Annotated[HTTPBasicCredentials, Depends(security)],
        settings=Depends(get_settings),
    ):
        is_correct_username = secrets.compare_digest(
            credentials.username.encode("utf8"), b"prom"
        )
        is_correct_password = secrets.compare_digest(
            credentials.password.encode("utf8"),
            settings.prometheus_metrics_password.encode("utf-8"),
        )
        if not (is_correct_username and is_correct_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Basic"},
            )

        resp = Response(content=generate_latest(registry))
        resp.headers["Content-Type"] = CONTENT_TYPE_LATEST
        return resp

    endpoint = "/metrics"
    app.get(endpoint, include_in_schema=True, tags=None)(metrics)
