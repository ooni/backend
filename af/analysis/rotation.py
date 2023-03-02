#!/usr/bin/env python3
"""
Spaws and rotates hosts on Digital Ocean. Runs a setup script on the host
at first boot.
Reads /etc/ooni/rotation.conf
Keeps a list of live hosts in a dedicated db table.
Runs as a SystemD timer.

Interfaces, APIs and stateful contents:
  - Digital Ocean API: DNS A/AAAA records
  - Digital Ocean API: Live droplets
  - test_helper_instances database table
  - certbot certificates stored on local host and pushed to the test hepers

Table setup:

CREATE TABLE test_helper_instances
(
    `rdn` String,
    `dns_zone` String,
    `name` String,
    `provider` String,
    `region` String,
    `ipaddr` IPv4,
    `ipv6addr` IPv6,
    `draining_at` Nullable(DateTime('UTC')),
    `sign` Int8
)
ENGINE = CollapsingMergeTree(sign)
ORDER BY name


Example for /etc/ooni/rotation.conf
--
[DEFAULT]
token = CHANGEME
active_droplets_count = 4
size_slug = s-1vcpu-1gb
image_name = debian-10-x64
draining_time_minutes = 240
dns_zone = th.ooni.org
--

Example for /etc/ooni/rotation_setup.sh
--
#!/bin/bash
# Configure test-helper droplet
# This script is run as root and with CWD=/
set -euo pipefail
exec 1>setup.log 2>&1
echo "deb [trusted=yes] https://ooni-internal-deb.s3.eu-central-1.amazonaws.com unstable main" > /etc/apt/sources.list.d/ooni.list
apt-key adv --verbose --keyserver hkp://keyserver.ubuntu.com --recv-keys 'B5A08F01796E7F521861B449372D1FF271F2DD50'
apt-get update
apt-get upgrade -qy
echo > /etc/motd
apt-get install -qy oohelperd
apt-get install -qy oohelperd nginx-light
--

Example for /etc/ooni/certbot-digitalocean
---
dns_digitalocean_token = CHANGEME
---
"""

from configparser import ConfigParser
from datetime import datetime
from functools import wraps
from subprocess import check_output
from pathlib import Path
from ipaddress import IPv4Address as IP4a
import logging
import random
import sys
import time

# debdeps: python3-clickhouse-driver
from clickhouse_driver import Client as Clickhouse
import statsd  # debdeps: python3-statsd
import digitalocean  # debdeps: python3-digitalocean
import requests  # debdeps: python3-requests

metrics = statsd.StatsClient("127.0.0.1", 8125, prefix="rotation")

log = logging.getLogger("rotation")
log.addHandler(logging.StreamHandler())  # Writes to console
log.setLevel(logging.DEBUG)

conffile_path = "/etc/ooni/rotation.conf"
setup_script_path = "/etc/ooni/rotation_setup.sh"
nginx_conf = "/etc/ooni/rotation_nginx_conf"
certbot_creds = "/etc/ooni/certbot-digitalocean"
TAG = "roaming-th"
ssh_cmd_base = [
    "ssh",
    "-o",
    "StrictHostKeyChecking=no",
    "-o",
    "UserKnownHostsFile=/dev/null",
    "-o",
    "ConnectTimeout=10",
    "-o",
    "BatchMode=yes",
    "-i",
    "/etc/ooni/testhelper_ssh_key",
]


def retry(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        for attempt in range(5):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                log.info(f"Catched {e} - retrying")
            time.sleep((attempt + 1) * 5)
        return func(*args, **kwargs)

    return wrapped


def insert(click, table: str, cols: dict) -> None:
    cs = ", ".join(sorted(cols.keys()))
    q = f"INSERT INTO {table} ({cs}) VALUES"
    log.info(q)
    click.execute(q, [cols])


def optimize_table(click, tblname: str) -> None:
    q = f"OPTIMIZE TABLE {tblname} FINAL"
    log.info(q)
    click.execute(q)


def add_droplet_to_db_table(click, dr, rdn, dns_zone) -> None:
    cols = dict(
        dns_zone=dns_zone,
        rdn=rdn,
        ipaddr=dr.ip_address,
        ipv6addr=dr.ip_v6_address,
        name=dr.name,
        provider="Digital Ocean",
        region=dr.region["slug"],
        sign=1,
    )
    insert(click, "test_helper_instances", cols)
    optimize_table(click, "test_helper_instances")


def drain_droplet_in_db_table(click, dr, rdn: str, dns_zone: str) -> None:
    cols = dict(
        dns_zone=dns_zone,
        rdn=rdn,
        ipaddr=dr.ip_address,
        ipv6addr=dr.ip_v6_address,
        name=dr.name,
        provider="Digital Ocean",
        region=dr.region["slug"],
        sign=-1,
    )
    insert(click, "test_helper_instances", cols)

    now = datetime.utcnow()
    cols["draining_at"] = now
    cols["sign"] = 1
    insert(click, "test_helper_instances", cols)
    optimize_table(click, "test_helper_instances")


def delete_droplet_from_db_table(
    click, dr, rdn: str, draining_at, dns_zone: str
) -> None:
    cols = dict(
        dns_zone=dns_zone,
        draining_at=draining_at,
        rdn=rdn,
        ipaddr=dr.ip_address,
        ipv6addr=dr.ip_v6_address,
        name=dr.name,
        provider="Digital Ocean",
        region=dr.region["slug"],
        sign=-1,
    )
    insert(click, "test_helper_instances", cols)


@metrics.timer("destroy_drained_droplets")
def destroy_drained_droplets(
    click, api, draining_time_minutes: int, live_droplets: list, dns_zone: str
) -> None:
    q = """SELECT name, rdn, draining_at FROM test_helper_instances
        FINAL
        WHERE provider = 'Digital Ocean'
        AND dns_zone = %(dns_zone)s
        AND draining_at IS NOT NULL
        AND draining_at < NOW() - interval %(mins)s minute
        ORDER BY draining_at
        LIMIT 1
    """
    log.info(q)
    rows = click.execute(q, dict(dns_zone=dns_zone, mins=draining_time_minutes))
    if not rows:
        log.info("No droplet to destroy")
        return

    name, rdn, draining_at = rows[0]
    to_delete = [d for d in live_droplets if d.name == name]
    if not to_delete:
        log.error(f"{name} found in database but not found on Digital Ocean")
        return

    for droplet in to_delete:
        log.info(f"Destroying {droplet.name} droplet")
        delete_droplet_from_db_table(click, droplet, rdn, draining_at, dns_zone)
        droplet.destroy()


def pick_regions(api, live_regions: set) -> list:
    """Pick regions that are available and have no droplet yet"""
    available_regions = set(
        r.slug for r in api.get_all_regions() if r.available is True
    )
    # Pick only regions with good, unfiltered network connectivity
    acceptable_regions = set(("ams3", "fra1", "lon1", "nyc3", "sfo3", "tor1"))
    ok_regions = acceptable_regions.intersection(available_regions)
    best_regions = ok_regions - live_regions
    if not len(best_regions):
        log.crit("No regions available!")
        raise Exception("No regions available")
    if len(best_regions):
        return list(best_regions)
    log.info(f"No 'best' region available. Falling back to {ok_regions}")
    return list(ok_regions)


@metrics.timer("spawn_new_droplet")
def spawn_new_droplet(api, dig_oc_token: str, live_regions, conf):
    regions = pick_regions(api, live_regions)

    ssh_keys = api.get_all_sshkeys()
    img = conf["image_name"]
    assert img
    size_slug = conf["size_slug"]
    assert size_slug
    with open(setup_script_path) as f:
        user_data = f.read()
    for attempt in range(20):
        name = datetime.utcnow().strftime("roaming-th-%Y%m%d%H%M%S")
        region = random.choice(regions)
        log.info(f"Trying to spawn {name} in {region}")
        try:
            droplet = digitalocean.Droplet(
                backups=False,
                image=img,
                name=name,
                region=region,
                size_slug=size_slug,
                ssh_keys=ssh_keys,
                token=dig_oc_token,
                user_data=user_data,
                ipv6=True,
                tags=[
                    TAG,
                ],
            )
            droplet.create()
            break
        except digitalocean.baseapi.DataReadError as e:
            log.info(f"Unable to spawn {e}")
            time.sleep(1)

    log.info(f"Spawning {name} in {region}")
    timeout = time.time() + 60 * 20
    while time.time() < timeout:
        time.sleep(5)
        for action in droplet.get_actions():
            action.load()
            if action.status == "completed":
                log.info("Spawning completed, waiting warmup")
                new_droplet = api.get_droplet(droplet.id)
                if new_droplet.ip_address:
                    ssh_wait_droplet_warmup(new_droplet.ip_address)
                    return new_droplet

        log.debug("Waiting for droplet to start")

    log.error("Timed out waiting for droplet start")
    raise Exception


# sz=api.get_all_sizes()
# sorted((s.price_monthly, s.slug, s.memory) for s in sz)
# imgs = api.get_all_images()
# [(i.name, i.slug) for i in imgs if i.distribution == "Debian"]


def load_conf():
    cp = ConfigParser()
    with open(conffile_path) as f:
        cp.read_file(f)
    return cp["DEFAULT"]


def list_active_droplets(click, live_droplets, dns_zone: str):
    q = """SELECT name, rdn FROM test_helper_instances
        FINAL
        WHERE provider = 'Digital Ocean'
        AND dns_zone = %(dns_zone)s
        AND draining_at IS NULL
    """
    log.info(q)
    rows = click.execute(q, dict(dns_zone=dns_zone))
    log.info(rows)
    active = set(row[0] for row in rows)
    active_droplets = [d for d in live_droplets if d.name in active]
    return active_droplets, rows


def drain_droplet(click, dns_zone, active_droplets: list, rows: list) -> str:
    by_age = sorted(active_droplets, key=lambda d: d.created_at)
    oldest = by_age[0]
    rdn = [row[1] for row in rows if row[0] == oldest.name][0]
    log.info(f"Draining {oldest.name} {rdn}.{dns_zone} droplet")
    drain_droplet_in_db_table(click, oldest, rdn, dns_zone)
    return rdn


@metrics.timer("create_le_do_ssl_cert")
def create_le_do_ssl_cert(dns_zone: str) -> None:
    """Create/renew Let's Encrypt SSL Certificate through the Digital Ocean API

    Namecheap DNS entry to delegate to DO:
        th.ooni.org
            NS  ns1.digitalocean.com
            NS  ns2.digitalocean.com
            NS  ns3.digitalocean.com

    On Digital Ocean, creates a wildcard cert for *.th.ooni.org using DNS
    """
    # TODO create_le_do_ssl_cert only if needed
    # debdeps: certbot python3-certbot-dns-digitalocean
    cmd = [
        "certbot",
        "certonly",
        "--dns-digitalocean",
        "--dns-digitalocean-credentials",
        certbot_creds,
        "-d",
        f"*.{dns_zone}",
        "-n",
    ]
    log.info(f"Creating/refreshing wildcard certificate *.{dns_zone}")
    log.info(" ".join(cmd))
    check_output(cmd)


@metrics.timer("scp_file")
@retry
def scp_file(local_fn: str, host: str, remote_fn: str) -> None:
    """SCP file"""
    assert remote_fn.startswith("/")
    dest = f"{host}:{remote_fn}"
    cmd = [
        "scp",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=10",
        "-i",
        "/etc/ooni/testhelper_ssh_key",
        "-Bpr",
        local_fn,
        dest,
    ]
    log.info("Copying file")
    log.info(" ".join(cmd))
    check_output(cmd)


def ssh_restart_service(host: str, service_name: str) -> None:
    cmd = ssh_cmd_base + [
        f"{host}",
        "systemctl",
        "restart",
        service_name,
    ]
    log.info(f"Restarting {service_name}")
    log.info(" ".join(cmd))
    check_output(cmd)


@metrics.timer("ssh_restart_nginx")
@retry
def ssh_restart_nginx(host: str) -> None:
    ssh_restart_service(host, "nginx")


@metrics.timer("ssh_restart_netdata")
@retry
def ssh_restart_netdata(host: str) -> None:
    ssh_restart_service(host, "netdata")


@metrics.timer("ssh_wait_droplet_warmup")
def ssh_wait_droplet_warmup(ipaddr: str) -> None:
    cmd = ssh_cmd_base + [
        f"root@{ipaddr}",
        "cat",
        "/var/run/rotation_setup_completed",
    ]
    timeout = time.time() + 60 * 15
    while time.time() < timeout:
        log.info("Checking flag")
        log.info(" ".join(cmd))
        try:
            check_output(cmd)
            log.info("Flag file found")
            return
        except Exception:
            log.debug("Flag file not found")
            time.sleep(5)

    log.error("Timed out waiting for droplet start")
    raise Exception


def delete_dns_record(api, zone: str, name: str, ip_address, rtype, dig_oc_token=None):
    assert not name.endswith(zone)
    records = api.get_records()
    for r in records:
        if r.domain == zone and r.data == ip_address and r.type == rtype:
            log.info(f"Deleting {r.type} {r.zone} {r.name} {r.data}")
            r.destroy()
            return

    log.error(f"{name} {ip_address} not found")


def update_or_create_dns_record(api, zone, name, rtype, ip_address, records):
    ip_address = str(ip_address)
    x = [r for r in records if r.name == name and r.type == rtype]
    if x:
        x = x[0]
        url = f"domains/{zone}/records/{x.id}"
        changes = dict(data=ip_address)
        m = f"Updating existing DNS record {x.id} {rtype} {name} {zone} {ip_address}"
        log.info(m)
        api.get_data(url, type=digitalocean.baseapi.PUT, params=changes)
        return

    log.info(f"Creating DNS record {rtype} {name} {zone} {ip_address}")
    api.create_new_domain_record(type=rtype, name=name, data=ip_address, ttl=60)


def update_or_create_dns_records(dig_oc_token: str, zone: str, vals: list) -> None:
    """Upsert A/AAAA records in Digital Ocean
    vals: [(n, ip_address, ip_v6_address), ... ]
    """
    api = digitalocean.Domain(name=zone, token=dig_oc_token)
    records = api.get_records()
    # An initial filtering for safety
    records = [r for r in records if r.domain == zone and r.type in ("A", "AAAA")]
    for n, ip_address, ip_v6_address in vals:
        name = str(n)
        # pick the existing record to be updated, if any:
        update_or_create_dns_record(api, zone, name, "A", ip_address, records)
        # Same for IPv6
        update_or_create_dns_record(api, zone, name, "AAAA", ip_v6_address, records)


@metrics.timer("update_dns_records")
def update_dns_records(click, dig_oc_token: str, dns_zone: str, droplets) -> None:
    q = """SELECT rdn, ipaddr, ipv6addr FROM test_helper_instances
        FINAL
        WHERE provider = 'Digital Ocean'
        AND dns_zone = %(dns_zone)s
        AND draining_at IS NULL
        ORDER BY name
    """
    log.info(q)
    rows = click.execute(q, dict(dns_zone=dns_zone))
    log.info(rows)
    update_or_create_dns_records(dig_oc_token, dns_zone, rows)


@metrics.timer("setup_nginx")
def setup_nginx(host: str, zone: str) -> None:
    """Deploy TLS certificates, configure Nginx and [re]start it.
    Then restart Netdata to enable Nginx monitoring.
    """
    cert_fname = f"/etc/letsencrypt/live/{zone}/fullchain.pem"
    privkey_fname = f"/etc/letsencrypt/live/{zone}/privkey.pem"
    scp_file(cert_fname, host, "/etc/ssl/private/th_fullchain.pem")
    scp_file(privkey_fname, host, "/etc/ssl/private/th_privkey.pem")
    scp_file(nginx_conf, host, "/etc/nginx/sites-enabled/default")
    ssh_restart_nginx(host)
    ssh_restart_netdata(host)


def assign_rdn(click, dns_zone: str, wanted_droplet_num: int) -> str:
    q = """SELECT rdn FROM test_helper_instances
        FINAL
        WHERE provider = 'Digital Ocean'
        AND dns_zone = %(dns_zone)s
        AND draining_at IS NULL
        """
    log.info(q)
    rows = click.execute(q, dict(dns_zone=dns_zone))
    log.info(rows)
    in_use = set(r[0] for r in rows)
    log.info(f"In use RDNs: {in_use}")
    for n in range(wanted_droplet_num):
        rdn = str(n)
        if rdn not in in_use:
            log.info(f"Selected RDN {rdn}")
            return rdn

    raise Exception("Unable to pick an RDN")


@metrics.timer("end_to_end_test")
def end_to_end_test(ipaddr: IP4a, fqdn: str) -> None:
    # Test the new TH with real traffic
    j = {
        "http_request": "https://google.com/",
        "http_request_headers": {},
        "tcp_connect": ["8.8.8.8:443"],
    }
    hdr = {"Host": fqdn, "Pragma": "no-cache"}
    log.info(f"Testing TH on {fqdn} using http_request and tcp_connect")
    r = requests.post(f"https://{ipaddr}", headers=hdr, verify=False, json=j)
    keys = set(r.json().keys())
    expected = {"dns", "http_request", "tcp_connect"}
    if r.ok and expected.issubset(keys):
        # This is true when keys >= expected
        log.info(f"End-to-end test successful")
        return

    log.error(f"Failed end to end test: {r.status_code}\nHeaders: {r.headers}")
    log.error(f"Body: {r.text}")
    raise Exception("End to end test failed")


@metrics.timer("run_time")
def main() -> None:
    conf = load_conf()

    dig_oc_token = conf["token"]
    assert dig_oc_token
    assert len(dig_oc_token) == 64
    draining_time_minutes = int(conf["draining_time_minutes"])
    assert draining_time_minutes >= 1

    wanted_droplet_num = int(conf["active_droplets_count"])
    assert 0 <= wanted_droplet_num < 20
    assert Path(setup_script_path).is_file()
    assert Path(certbot_creds).is_file()
    assert Path(nginx_conf).is_file()
    dns_zone = conf["dns_zone"].strip(".")
    assert dns_zone

    click = Clickhouse("localhost", user="rotation")
    api = digitalocean.Manager(token=dig_oc_token)
    # Fetch all test-helper droplets
    droplets = api.get_all_droplets(tag_name=TAG)
    for d in droplets:
        assert TAG in d.tags
    # Naming: live_droplets - all VMs running on Digital Ocean in active status
    #         active_droplets - live_droplets without the ones being drained
    live_droplets = [d for d in droplets if d.status == "active"]
    active_droplets, rows = list_active_droplets(click, live_droplets, dns_zone)
    log.info(f"{len(droplets)} droplets")
    log.info(f"{len(live_droplets)} live droplets")
    log.info(f"{len(active_droplets)} active droplets")

    # Avoid failure modes where we destroy all VMs or create unlimited amounts
    # or churn too quickly
    destroy_drained_droplets(click, api, draining_time_minutes, live_droplets, dns_zone)

    if len(droplets) > wanted_droplet_num + 5:
        log.error("Unexpected amount of running droplets")
        sys.exit(1)

    if len(active_droplets) >= wanted_droplet_num:
        # Drain one droplet if needed
        rdn = drain_droplet(click, dns_zone, active_droplets, rows)

    else:
        # special case: creating a new rdn not seen before
        rdn = assign_rdn(click, dns_zone, wanted_droplet_num)

    # Spawn a new droplet
    log.info(f"Spawning droplet be become {rdn}.{dns_zone}")
    live_regions = set(d.region["slug"] for d in droplets)
    new_droplet = spawn_new_droplet(api, dig_oc_token, live_regions, conf)
    log.info(f"Droplet {new_droplet.name} ready at {new_droplet.ip_address}")
    add_droplet_to_db_table(click, new_droplet, rdn, dns_zone)
    live_droplets.append(new_droplet)

    create_le_do_ssl_cert(dns_zone)
    setup_nginx(f"root@{new_droplet.ip_address}", dns_zone)
    end_to_end_test(new_droplet.ip_address, f"{rdn}.{dns_zone}")

    # Update DNS A/AAAA records only when a new droplet is deployed
    update_dns_records(click, dig_oc_token, dns_zone, live_droplets)


if __name__ == "__main__":
    main()
