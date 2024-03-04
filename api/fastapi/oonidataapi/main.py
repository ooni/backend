from fastapi import FastAPI

from .routers import measurements
from .routers import aggregation
from .routers import oonirun

from .config import settings
from fastapi.middleware.cors import CORSMiddleware

import logging

logging.basicConfig(level=getattr(logging, settings.log_level.upper()))

app = FastAPI()
# TODO: temporarily enable all
origins = [
    "*"
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(measurements.router, prefix="/api")
app.include_router(aggregation.router, prefix="/api")
app.include_router(oonirun.router, prefix="/api")


from importlib.metadata import version as importlib_version
from importlib.resources import files as importlib_files

pkg_name = "oonidataapi"

pkg_version = importlib_version(pkg_name)
try:
    with importlib_files(pkg_name).joinpath("BUILD_LABEL").open("r") as in_file:
        build_label = in_file.read().strip()
except:
    build_label = None


@app.get("/version")
async def version():
    return {"version": pkg_version, "build_label": build_label}


@app.get("/")
async def root():
    return {"message": "Hello OONItarian!"}
