"""
Integration test for OONIProbe API
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from httpx import HTTPError
from freezegun import freeze_time
import pytest

from ooniprobe.utils import OpenVPNConfig
from ooniprobe import models
from ooniprobe.routers import v2


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
    vpn_cert = OpenVPNConfig(
        ca="-----BEGIN CERTIFICATE-----\nSAMPLE CERTIFICATE\n-----END CERTIFICATE-----\n",
        cert="-----BEGIN CERTIFICATE-----\nSAMPLE CERTIFICATE\n-----END CERTIFICATE-----\n",
        key="-----BEGIN RSA PRIVATE KEY-----\nSAMPLE KEY\n-----END RSA PRIVATE KEY-----\n",
    )

    with freeze_time("1984-01-01"):
        vpn_config = models.OONIProbeVPNConfig(
            provider="riseupvpn",
            date_updated=datetime.now(timezone.utc),
            date_created=datetime.now(timezone.utc),
            protocol="openvpn",
            openvpn_ca=vpn_cert["ca"],
            openvpn_cert=vpn_cert["cert"],
            openvpn_key=vpn_cert["key"],
        )
        db.add(vpn_config)
        db.commit()

        r = client.get("/api/v2/ooniprobe/vpn-config/riseupvpn")
        assert r.status_code == 200
        j = r.json()
        assert j["provider"] == "riseupvpn"
        assert j["protocol"] == "openvpn"
        assert j["config"]["cert"] == vpn_cert["cert"]
        assert j["config"]["ca"] == vpn_cert["ca"]
        assert j["config"]["key"] == vpn_cert["key"]

    # Check to see if the cert got updated
    with freeze_time("1984-04-01"):
        r = client.get("/api/v2/ooniprobe/vpn-config/riseupvpn")
        assert r.status_code == 200
        j = r.json()
        assert j["provider"] == "riseupvpn"
        assert j["protocol"] == "openvpn"
        assert j["config"]["cert"] != vpn_cert["cert"]
        assert j["config"]["ca"] != vpn_cert["ca"]
        assert j["config"]["key"] != vpn_cert["key"]
        assert j["date_updated"].startswith("1984-04-01")


@pytest.mark.parametrize('error', [HTTPError, Exception])
def test_get_config_fails_if_exception_while_fetching_credentials(client, db, error):
    # no previous credential; when forcing any exception on the fetch code the http client should get a 500
    with patch.object(v2, 'get_or_update_riseup_vpn_config', side_effect=error('err')):
        r = client.get("/api/v2/ooniprobe/vpn-config/riseupvpn")
        assert r.status_code == 500
