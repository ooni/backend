"""
Integration test for OONIProbe API
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from httpx import HTTPError
from freezegun import freeze_time
import pytest

from ooniprobe.utils import OpenVPNConfig
from ooniprobe import models
from ooniprobe.routers.v2 import vpn

DUMMY_VPN_CERT = OpenVPNConfig(
    ca="-----BEGIN CERTIFICATE-----\nSAMPLE CERTIFICATE\n-----END CERTIFICATE-----\n",
    cert="-----BEGIN CERTIFICATE-----\nSAMPLE CERTIFICATE\n-----END CERTIFICATE-----\n",
    key="-----BEGIN RSA PRIVATE KEY-----\nSAMPLE KEY\n-----END RSA PRIVATE KEY-----\n",
)


def test_get_version(client):
    r = client.get("/version")
    j = r.json()
    assert "version" in j
    assert "build_label" in j


def test_get_root(client):
    r = client.get("/")
    assert r.status_code == 200


def test_get_config(client):
    r = client.get("/api/v2/ooniprobe/vpn-config/riseupvpn")
    assert r.status_code == 200
    j = r.json()
    assert j["provider"] == "riseupvpn"
    assert j["protocol"] == "openvpn"
    assert j["config"]["cert"].startswith("-----BEGIN CERTIFICATE")
    assert j["config"]["ca"].startswith("-----BEGIN CERTIFICATE")
    assert j["config"]["key"].startswith("-----BEGIN RSA PRIVATE KEY")
    date_updated = j["date_updated"]

    r = client.get("/api/v2/ooniprobe/vpn-config/riseupvpn")
    assert r.status_code == 200
    j = r.json()
    assert j["date_updated"] == date_updated


def test_invalid_provider_name(client, db):
    # we probably aren't going to add NSA VPN to our provider list anytime soon :D
    r = client.get("/api/v2/ooniprobe/vpn-config/nsavpn")
    assert r.status_code != 200


def test_config_updated(client, db):
    with freeze_time("1984-01-01"):
        provider = models.OONIProbeVPNProvider(
            provider_name="riseupvpn",
            date_updated=datetime.now(timezone.utc),
            date_created=datetime.now(timezone.utc),
            openvpn_ca=DUMMY_VPN_CERT["ca"],
            openvpn_cert=DUMMY_VPN_CERT["cert"],
            openvpn_key=DUMMY_VPN_CERT["key"],
        )
        db.add(provider)
        db.commit()

        r = client.get("/api/v2/ooniprobe/vpn-config/riseupvpn")
        assert r.status_code == 200
        j = r.json()
        assert j["provider"] == "riseupvpn"
        assert j["protocol"] == "openvpn"
        assert j["config"]["cert"] == DUMMY_VPN_CERT["cert"]
        assert j["config"]["ca"] == DUMMY_VPN_CERT["ca"]
        assert j["config"]["key"] == DUMMY_VPN_CERT["key"]

    # Check to see if the cert got updated
    with freeze_time("1984-04-01"):
        r = client.get("/api/v2/ooniprobe/vpn-config/riseupvpn")
        assert r.status_code == 200
        j = r.json()
        assert j["provider"] == "riseupvpn"
        assert j["protocol"] == "openvpn"
        assert j["config"]["cert"] != DUMMY_VPN_CERT["cert"]
        assert j["config"]["ca"] != DUMMY_VPN_CERT["ca"]
        assert j["config"]["key"] != DUMMY_VPN_CERT["key"]
        assert j["date_updated"].startswith("1984-04-01")


@pytest.mark.parametrize("error", [HTTPError, Exception])
def test_get_config_fails_if_exception_while_fetching_credentials(client, db, error):
    # no previous credential; when forcing any exception on the fetch code the http client should get a 500
    with patch.object(vpn, "get_or_update_riseupvpn", side_effect=error("err")):
        r = client.get("/api/v2/ooniprobe/vpn-config/riseupvpn")
        assert r.status_code == 500

    with patch.object(vpn, "update_vpn_provider", side_effect=error("err")):
        r = client.get("/api/v2/ooniprobe/vpn-config/riseupvpn")
        assert r.status_code == 500

    # Check that we get stale data if we have it and it's failing to fetch the data
    provider = models.OONIProbeVPNProvider(
        provider_name="riseupvpn",
        date_updated=datetime.now(timezone.utc) - timedelta(days=20),
        date_created=datetime.now(timezone.utc) - timedelta(days=20),
        openvpn_ca=DUMMY_VPN_CERT["ca"],
        openvpn_cert=DUMMY_VPN_CERT["cert"],
        openvpn_key=DUMMY_VPN_CERT["key"],
    )
    db.add(provider)
    db.commit()

    with patch.object(vpn, "update_vpn_provider", side_effect=error("err")):
        r = client.get("/api/v2/ooniprobe/vpn-config/riseupvpn")
        assert r.status_code == 200
