import hashlib
import json
from pathlib import Path

import httpx
import pytest

from ooniprobe import tor_targets
from ooniprobe.routers.v1.probe_services import TorTarget

DATA = Path("tests/fixtures/data")


@pytest.fixture
def pt_config():
    return json.loads((DATA / "pt_config.json").read_text())


@pytest.fixture
def auth_dirs():
    return (DATA / "auth_dirs.inc").read_text()


def make_client(pt_config, auth_dirs, status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == tor_targets.PT_CONFIG_URL:
            return httpx.Response(status, json=pt_config)
        if str(request.url) == tor_targets.AUTH_DIRS_URL:
            return httpx.Response(status, text=auth_dirs)
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


class FakeS3:
    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body, ContentType):
        self.objects[(Bucket, Key)] = Body


def test_parse_bridge_line():
    line = "obfs4 1.2.3.4:443 D9A82D2F9C2F65A18407B1D2B764F130847F8B5D cert=abc= iat-mode=0"
    assert tor_targets.parse_bridge_line(line) == {
        "address": "1.2.3.4:443",
        "fingerprint": "D9A82D2F9C2F65A18407B1D2B764F130847F8B5D",
        "name": "",
        "protocol": "obfs4",
        "params": {"cert": ["abc="], "iat-mode": ["0"]},
    }


def test_parse_bridge_line_no_fingerprint():
    line = "meek_lite 192.0.2.20:80 url=https://example.org front=example.net"
    assert tor_targets.parse_bridge_line(line) is None
    assert tor_targets.parse_bridge_line("obfs4 1.2.3.4:443") is None


def test_parse_bridges(pt_config):
    targets = tor_targets.parse_bridges(pt_config)
    assert len(targets) == 3
    for line in pt_config["bridges"]["obfs4"]:
        key = hashlib.sha256(line.encode()).hexdigest()
        assert targets[key]["protocol"] == "obfs4"
        assert targets[key]["address"] == line.split()[1]
    for t in targets.values():
        TorTarget(**t)


def test_parse_auth_dirs(auth_dirs):
    targets = tor_targets.parse_auth_dirs(auth_dirs)
    assert len(targets) == 20
    assert targets["128.31.0.39:9201"] == {
        "address": "128.31.0.39:9201",
        "fingerprint": "1A25C6358DB91342AA51720A5038B72742732498",
        "name": "moria1",
        "protocol": "or_port_dirauth",
    }
    assert targets["128.31.0.39:9231"]["protocol"] == "dir_port"
    # maatuska has its orport on 80 and dirport on 443
    assert targets["171.25.193.9:80"]["protocol"] == "or_port_dirauth"
    assert targets["171.25.193.9:443"]["protocol"] == "dir_port"
    # bridge authority with no v3ident
    assert targets["66.111.2.131:9001"]["name"] == "Serge"
    assert (
        targets["217.196.147.77:443"]["fingerprint"]
        == "FAA4BCA4A6AC0FB4CA2F8AD5A11D9E122BA894F6"
    )


def test_parse_auth_dirs_skips_bad_entries():
    text = """
    /* comment with "quotes", */
    "noaddr orport=443 v3ident=AAAA",
    "badfpr orport=443 1.2.3.4:80 ABCD",
    "ok orport=443 "
      "1.2.3.4:80 1A25 C635 8DB9 1342 AA51 720A 5038 B727 4273 2498",
    """
    targets = tor_targets.parse_auth_dirs(text)
    assert set(targets) == {"1.2.3.4:443", "1.2.3.4:80"}


def test_fetch_tor_targets(pt_config, auth_dirs):
    targets = tor_targets.fetch_tor_targets(make_client(pt_config, auth_dirs))
    assert len(targets) == 3 + 20
    for t in targets.values():
        TorTarget(**t)


def test_fetch_tor_targets_http_error(pt_config, auth_dirs):
    with pytest.raises(httpx.HTTPStatusError):
        tor_targets.fetch_tor_targets(make_client(pt_config, auth_dirs, 500))


def test_fetch_tor_targets_rejects_empty(auth_dirs):
    with pytest.raises(ValueError):
        tor_targets.fetch_tor_targets(make_client({"bridges": {}}, auth_dirs))


def test_upload(pt_config, auth_dirs):
    s3 = FakeS3()
    targets = tor_targets.fetch_tor_targets(make_client(pt_config, auth_dirs))
    tor_targets.upload(targets, s3, "bucket", "tor_targets.json")
    assert json.loads(s3.objects[("bucket", "tor_targets.json")]) == targets
