from fastapi import FastAPI

from .routers import oonirun

from .common.config import settings
from .common.version import get_build_label, get_pkg_version
from fastapi.middleware.cors import CORSMiddleware

import logging

logging.basicConfig(level=getattr(logging, settings.log_level.upper()))

app = FastAPI()
# TODO: temporarily enable all
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(oonirun.router, prefix="/api")

from importlib.metadata import version as importlib_version
from importlib.resources import files as importlib_files

pkg_name = "ooniapi.oonirun"

pkg_version = get_pkg_version(pkg_name)
build_label = get_build_label(pkg_name)


@app.get("/version")
async def version():
    return {"version": pkg_version, "build_label": build_label}


@app.get("/")
async def root():
    return {"message": "Hello OONItarian!"}
