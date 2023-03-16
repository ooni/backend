"""
Test helper rotation - basic functional testing
"""

import datetime
from unittest.mock import Mock, create_autospec, call

import pytest  # debdeps: python3-pytest

import rotation as ro


@pytest.fixture(autouse=True, scope="session")
def mock_everything():
    ro.Clickhouse = create_autospec(ro.Clickhouse)
    ro.digitalocean = create_autospec(ro.digitalocean)
    ro.requests = Mock()
    ro.metrics = Mock()
    ro.datetime = create_autospec(ro.datetime)
    ro.datetime.utcnow = Mock(return_value=datetime.datetime(2000, 1, 1))


class Droplet:
    region = dict(slug="slug")
    ip_address = "1.2.3.4"
    ip_v6_address = "::9"
    name = "foo_name"


@pytest.fixture
def dr():
    return Droplet()


def test_rotation_db_list():
    click = ro.Clickhouse("localhost", user="rotation")
    d = Mock()
    active_droplets, rows = ro.list_active_droplets(click, [d], "foo")
    click.execute.assert_called()
    click.execute.assert_called_with(
        """SELECT name, rdn FROM test_helper_instances
        FINAL
        WHERE provider = 'Digital Ocean'
        AND dns_zone = %(dns_zone)s
        AND draining_at IS NULL
    """,
        {"dns_zone": "foo"},
    ), click.execute.call_args_list


def test_rotation_db_add(dr):
    click = ro.Clickhouse("localhost", user="rotation")
    click.execute.reset_mock()
    ro.add_droplet_to_db_table(click, dr, "0", "foo")
    exp = [
        call(
            "INSERT INTO test_helper_instances (dns_zone, ipaddr, ipv6addr, name, provider, rdn, region, sign) VALUES",
            [
                {
                    "dns_zone": "foo",
                    "rdn": "0",
                    "ipaddr": "1.2.3.4",
                    "ipv6addr": "::9",
                    "name": "foo_name",
                    "provider": "Digital Ocean",
                    "region": "slug",
                    "sign": 1,
                }
            ],
        )
    ]
    assert click.execute.call_args_list == exp, click.execute.call_args_list


def test_rotation_db_drain(dr):
    click = ro.Clickhouse("localhost", user="rotation")
    click.execute.reset_mock()
    now = datetime.datetime(2000, 1, 1, 0, 0)
    ro.drain_droplet_in_db_table(click, now, dr, "0", "foo")
    exp = [
        call(
            "INSERT INTO test_helper_instances (dns_zone, ipaddr, ipv6addr, name, provider, rdn, region, sign) VALUES",
            [
                {
                    "dns_zone": "foo",
                    "rdn": "0",
                    "ipaddr": "1.2.3.4",
                    "ipv6addr": "::9",
                    "name": "foo_name",
                    "provider": "Digital Ocean",
                    "region": "slug",
                    "sign": -1,
                }
            ],
        ),
        call(
            "INSERT INTO test_helper_instances (dns_zone, draining_at, ipaddr, ipv6addr, name, provider, rdn, region, sign) VALUES",
            [
                {
                    "dns_zone": "foo",
                    "rdn": "0",
                    "ipaddr": "1.2.3.4",
                    "ipv6addr": "::9",
                    "name": "foo_name",
                    "provider": "Digital Ocean",
                    "region": "slug",
                    "sign": 1,
                    "draining_at": datetime.datetime(2000, 1, 1, 0, 0),
                }
            ],
        ),
        call("OPTIMIZE TABLE test_helper_instances FINAL"),
    ]
    assert click.execute.call_args_list == exp, click.execute.call_args_list


def test_rotation_db_destroy(dr):
    click = ro.Clickhouse("localhost", user="rotation")
    click.execute.reset_mock()
    drain_t = datetime.datetime(2000, 1, 1, 0, 0)
    destroy_t = datetime.datetime(2000, 2, 2, 0, 0)
    ro.destroy_droplet_in_db_table(click, dr, "0", drain_t, destroy_t, "foo")
    exp = [
        call(
            "INSERT INTO test_helper_instances (dns_zone, draining_at, ipaddr, ipv6addr, name, provider, rdn, region, sign) VALUES",
            [
                {
                    "dns_zone": "foo",
                    "draining_at": drain_t,
                    "ipaddr": "1.2.3.4",
                    "ipv6addr": "::9",
                    "name": "foo_name",
                    "provider": "Digital Ocean",
                    "rdn": "0",
                    "region": "slug",
                    "sign": -1,
                }
            ],
        ),
        call(
            "INSERT INTO test_helper_instances (destroyed_at, dns_zone, draining_at, ipaddr, ipv6addr, name, provider, rdn, region, sign) VALUES",
            [
                {
                    "dns_zone": "foo",
                    "draining_at": drain_t,
                    "ipaddr": "1.2.3.4",
                    "ipv6addr": "::9",
                    "name": "foo_name",
                    "provider": "Digital Ocean",
                    "rdn": "0",
                    "region": "slug",
                    "sign": 1,
                    "destroyed_at": destroy_t,
                }
            ],
        ),
        call("OPTIMIZE TABLE test_helper_instances FINAL"),
    ]
    assert click.execute.call_args_list == exp, click.execute.call_args_list
