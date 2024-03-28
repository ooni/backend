from datetime import datetime, timedelta, timezone
from ooniprobe.models import OONIProbeVPNProvider, OONIProbeVPNProviderEndpoint
from ooniprobe.utils import OpenVPNEndpoint, upsert_endpoints


defaultRiseupTargets = [
    "openvpn://riseup.corp/?address=51.15.187.53:1194&transport=tcp",
    "openvpn://riseup.corp/?address=51.15.187.53:1194&transport=udp",
]

def test_create_providers(db, alembic_migration):
    provider = OONIProbeVPNProvider(
        provider_name="riseupvpn",
        date_created=datetime.now(timezone.utc),
        date_updated=datetime.now(timezone.utc),
        openvpn_cert="OPENVPN_CERT",
        openvpn_ca="OPENVPN_CA",
        openvpn_key="OPENVPN_KEY"
    )
    db.add(provider)
    db.add(OONIProbeVPNProviderEndpoint(
        date_created=datetime.now(timezone.utc)-timedelta(hours=1),
        date_updated=datetime.now(timezone.utc)-timedelta(hours=1),
        protocol="openvpn",
        address="51.15.187.53:1194",
        transport="tcp",
        provider=provider
    ))
    db.add(OONIProbeVPNProviderEndpoint(
        date_created=datetime.now(timezone.utc)-timedelta(hours=1),
        date_updated=datetime.now(timezone.utc)-timedelta(hours=1),
        protocol="openvpn",
        address="51.15.187.53:1194",
        transport="udp",
        provider=provider
    ))
    db.add(OONIProbeVPNProviderEndpoint(
        date_created=datetime.now(timezone.utc)-timedelta(hours=1),
        date_updated=datetime.now(timezone.utc)-timedelta(hours=1),
        protocol="openvpn",
        address="1.1.1.1:1194",
        transport="udp",
        provider=provider
    ))
    db.commit()

    all_endpoints = db.query(OONIProbeVPNProviderEndpoint).all()
    assert len(all_endpoints) == 3
    addresses = set()
    for endpoint in all_endpoints:
        addresses.add(endpoint.address)
        assert endpoint.protocol
        assert endpoint.address
        assert endpoint.transport
        assert endpoint.provider.provider_name == "riseupvpn"
    assert addresses == set(["51.15.187.53:1194", "1.1.1.1:1194"])

    provider = db.query(OONIProbeVPNProvider).filter(
        OONIProbeVPNProvider.provider_name == "riseupvpn",
        OONIProbeVPNProvider.date_updated
        > datetime.now(timezone.utc)
        - timedelta(days=7),
    ).one()
    assert len(provider.endpoints) == 3

    new_endpoints = [
        OpenVPNEndpoint(
            address="51.15.187.53:1194",
            protocol="openvpn",
            transport="udp"
        ),
        OpenVPNEndpoint(
            address="51.15.187.53:1194",
            protocol="openvpn",
            transport="tcp"
        ),
        OpenVPNEndpoint(
            address="3.2.1.3:1194",
            protocol="openvpn",
            transport="udp"
        ),
    ]

    upsert_endpoints(db, new_endpoints, provider)
    db.commit()

    all_endpoints = db.query(OONIProbeVPNProviderEndpoint).all()
    assert len(all_endpoints) == 3
    addresses = set()
    for endpoint in all_endpoints:
        addresses.add(endpoint.address)
        assert endpoint.protocol
        assert endpoint.address
        assert endpoint.transport
        assert endpoint.provider.provider_name == "riseupvpn"
        assert endpoint.date_updated > datetime.now(timezone.utc) - timedelta(minutes=1)
    assert addresses == set(["51.15.187.53:1194", "3.2.1.3:1194"])
