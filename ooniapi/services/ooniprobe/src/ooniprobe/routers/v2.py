from datetime import datetime, timedelta, timezone, date
import random
from typing import Dict, List
import logging

import sqlalchemy as sa
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException

from .. import models

from ..utils import (
    fetch_openvpn_config,
    fetch_openvpn_endpoints,
    format_endpoint,
    upsert_endpoints,
)
from ..common.routers import BaseModel
from ..common.dependencies import get_settings
from ..dependencies import get_postgresql_session


log = logging.getLogger(__name__)

router = APIRouter()


class VPNConfig(BaseModel):
    provider: str
    protocol: str
    config: Dict[str, str]
    # date_updated is when the credentials or other config has been updated;
    # inputs will follow a different lifecycle.
    date_updated: str
    endpoints: List[str]


def update_vpn_provider(db: Session, provider_name: str) -> models.OONIProbeVPNProvider:
    """Fetch a fresh config for a given provider and update the database entry"""
    # we are only handling a single provider for the time being (riseup).
    # TODO: manage an inventory of known providers.
    vpn_cert = fetch_openvpn_config()

    try:
        provider = (
            db.query(models.OONIProbeVPNProvider)
            .filter(
                models.OONIProbeVPNProvider.provider_name == provider_name,
            )
            .one()
        )
        vpn_endpoints = fetch_openvpn_endpoints()

        provider.openvpn_ca = vpn_cert["ca"]
        provider.openvpn_cert = vpn_cert["cert"]
        provider.openvpn_key = vpn_cert["key"]
        provider.date_updated = datetime.now(timezone.utc)
        upsert_endpoints(db, vpn_endpoints, provider)
        db.commit()

    except sa.orm.exc.NoResultFound:
        provider = models.OONIProbeVPNProvider(
            provider_name=provider_name,
            date_updated=datetime.now(timezone.utc),
            date_created=datetime.now(timezone.utc),
            openvpn_ca=vpn_cert["ca"],
            openvpn_cert=vpn_cert["cert"],
            openvpn_key=vpn_cert["key"],
        )
        db.add(provider)
        vpn_endpoints = fetch_openvpn_endpoints()
        upsert_endpoints(db, vpn_endpoints, provider)
        db.commit()

    return provider


def get_or_update_riseupvpn(
    db: Session, provider_name: str, vpn_credential_refresh_hours: int
) -> models.OONIProbeVPNProvider:
    """Get a configuration entry for the given provider, or fetch a fresh one if None found"""
    provider = (
        db.query(models.OONIProbeVPNProvider)
        .filter(
            models.OONIProbeVPNProvider.provider_name == provider_name,
            models.OONIProbeVPNProvider.date_updated
            > datetime.now(timezone.utc)
            - timedelta(hours=vpn_credential_refresh_hours),
        )
        .first()
    )
    if provider:
        return provider

    try:
        provider = update_vpn_provider(db, provider_name)
        return provider
    except:
        log.error(f"failed to update vpn provider {provider_name}")

    try:
        # In this case we at least serve a stale version of the provider instead
        # of just failing.
        provider = (
            db.query(models.OONIProbeVPNProvider)
            .filter(
                models.OONIProbeVPNProvider.provider_name == provider_name,
            )
            .one()
        )
        return provider
    except sa.orm.exc.NoResultFound:
        raise HTTPException(status_code=500, detail="error updating provider")


@router.get("/v2/ooniprobe/vpn-config/{provider_name}", tags=["ooniprobe"])
def get_vpn_config(
    provider_name: str,
    db=Depends(get_postgresql_session),
    settings=Depends(get_settings),
) -> VPNConfig:
    """GET VPN config parameters for a given provider, including authentication"""
    log.debug(f"GET vpn config for {provider_name}")

    if provider_name != "riseupvpn":
        raise HTTPException(status_code=404, detail="provider not found")

    try:
        provider = get_or_update_riseupvpn(
            db=db,
            provider_name=provider_name,
            vpn_credential_refresh_hours=settings.vpn_credential_refresh_hours,
        )
    except Exception as exc:
        log.error("Error while fetching credentials for riseup: %s", exc)
        raise HTTPException(status_code=500, detail="could not fetch credentials")

    endpoints = [
        format_endpoint(provider.provider_name, ep) for ep in provider.endpoints
    ]
    return VPNConfig(
        provider=provider.provider_name,
        protocol="openvpn",
        config={
            "ca": provider.openvpn_ca,
            "cert": provider.openvpn_cert,
            "key": provider.openvpn_key,
        },
        # Pick 4 random endpoints to serve to the client
        endpoints=random.sample(endpoints, min(len(endpoints), 4)),
        date_updated=provider.date_updated.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    )
