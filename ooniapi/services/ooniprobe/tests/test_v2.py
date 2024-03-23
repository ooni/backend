"""
Integration test for OONIRn API
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import time

from ooniprobe import models
import pytest

import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine


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
