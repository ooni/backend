from functools import lru_cache
from fastapi import FastAPI

from .routers import oonirun

from .dependencies import get_settings
from .common.version import get_build_label, get_pkg_version
from fastapi.middleware.cors import CORSMiddleware

from contextlib import asynccontextmanager

import logging

pkg_name = "oonirun"

pkg_version = get_pkg_version(pkg_name)
build_label = get_build_label(pkg_name)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper()))
    yield


app = FastAPI(lifespan=lifespan)

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


@app.get("/version")
async def version():
    return {"version": pkg_version, "build_label": build_label}


@app.get("/health")
async def health():
    return {"status": "ok", "version": pkg_version, "build_label": build_label}


@app.get("/")
async def root():
    return {"message": "Hello OONItarian!"}
