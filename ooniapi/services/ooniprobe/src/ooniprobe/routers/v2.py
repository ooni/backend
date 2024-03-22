"""
OONIRun link management

https://github.com/ooni/spec/blob/master/backends/bk-005-ooni-run-v2.md
"""

from datetime import datetime, timedelta, timezone, date
from typing import Dict, List, Optional, Tuple
import logging

import sqlalchemy as sa
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, Query, HTTPException, Header, Path
from pydantic import computed_field, Field, validator
from typing_extensions import Annotated

from .. import models

from ..common.routers import BaseModel
from ..common.dependencies import get_settings
from ..dependencies import get_postgresql_session


log = logging.getLogger(__name__)

router = APIRouter()


class VPNConfig(BaseModel):
    pass


class ListVPNConfig(BaseModel):
    vpn_configs: List[VPNConfig]


@router.get("/v2/ooniprobe/vpn-config", tags=["ooniprobe"])
def list_vpn_configs(
    db=Depends(get_postgresql_session),
    settings=Depends(get_settings),
) -> ListVPNConfig:
    """List OONIRun descriptors"""
    log.debug("list oonirun")

    q = db.query(models.OONIProbeVPNConfig)

    vpn_configs = []
    for row in q.all():
        vpn_config = VPNConfig()
        vpn_configs.append(vpn_config)
    return ListVPNConfig(vpn_configs=vpn_configs)
