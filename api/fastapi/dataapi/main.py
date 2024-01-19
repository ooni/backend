from fastapi import FastAPI

from .routers import measurements
from .routers import aggregation

from .config import settings

import logging

logging.basicConfig(level=getattr(logging, settings.log_level.upper()))

app = FastAPI()
app.include_router(measurements.router, prefix="/api")
app.include_router(aggregation.router, prefix="/api")

from importlib.metadata import version as importlib_version
from importlib.resources import files as importlib_files

pkg_name = "dataapi"

pkg_version = importlib_version(pkg_name)
try:
    with importlib_files("dataapi").joinpath("TAG_VERSION").open('r') as in_file:
        tag_version = in_file.read().strip()
except:
    tag_version = None

@app.get("/version")
async def version():
    return {"version": pkg_version, "tag_version": tag_version}

@app.get("/")
async def root():
    return {"message": "Hello OONItarian!"}
