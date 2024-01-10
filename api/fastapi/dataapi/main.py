from fastapi import FastAPI

from .routers import measurements
from .routers import aggregation

from .config import settings

import logging

logging.basicConfig(level=getattr(logging, settings.log_level.upper()))

app = FastAPI()
app.include_router(measurements.router, prefix="/api")
app.include_router(aggregation.router, prefix="/api")


@app.get("/")
async def root():
    return {"message": "Hello OONItarian!"}
