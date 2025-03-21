import secrets

from typing import Annotated, Optional
import timeit

from fastapi import FastAPI, Response, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .dependencies import get_settings
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    generate_latest,
    Histogram,
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


FUNCTION_TIME = Histogram(
    "fn_execution_time_seconds",
    "Function execution time in seconds",
    labelnames=["name", "status"],
)


def timer(func, timer_name: Optional[str] = None):
    """Measure function execution time in seconds.

    Metric will include execution status (error or success) and function name, you
    can also specify another name with `timer_name`. Example:

    ```
    @timer
    def add(x,y):
        return x + y
    ```

    Args:
        func (Callable): function to time
        timer_name (Optional[str], optional): Alternative name for this timer, uses function name if
        not provided. Defaults to None.
    """

    name = timer_name or func.__name__

    def timed_function(*args, **kwargs):

        start_time = timeit.default_timer()
        result = None
        successs = False

        try:
            result = func(*args, **kwargs)
            successs = True
        finally:
            end_time = timeit.default_timer()
            status = "success" if successs else "error"
            FUNCTION_TIME.labels(name=name, status=status).observe(
                end_time - start_time
            )

        return result

    return timed_function
