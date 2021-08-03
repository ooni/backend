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
CREATE UNLOGGED TABLE test_helper_instances (
    name text NOT NULL,
    provider text NOT NULL,
    region text,
    ipaddr inet NOT NULL,
    ipv6addr inet,
    draining_at timestamp without time zone
);
ALTER TABLE test_helper_instances OWNER TO shovel;

Example for /etc/ooni/rotation.conf
--
[DEFAULT]
token = CHANGEME
db_uri = postgresql://shovel:CHANGEME@localhost/metadb
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
import logging
import random
import sys
import time

import psycopg2  # debdeps: python3-psycopg2
import statsd  # debdeps: python3-statsd
import digitalocean  # debdeps: python3-digitalocean

metrics = statsd.StatsClient("127.0.0.1", 8125, prefix="rotation")

log = logging.getLogger("rotation")
log.addHandler(logging.StreamHandler())  # Writes to console
log.setLevel(logging.DEBUG)

conffile_path = "/etc/ooni/rotation.conf"
setup_script_path = "/etc/ooni/rotation_setup.sh"
nginx_conf = "/etc/ooni/rotation_nginx_conf"
certbot_creds = "/etc/ooni/certbot-digitalocean"
TAG = "roaming-th"


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


def add_droplet_to_db_table(db_conn, dr):
    vals = [dr.name, dr.region["slug"], dr.ip_address, dr.ip_v6_address]
    q = """INSERT INTO test_helper_instances
        (name, provider, region, ipaddr, ipv6addr)
        VALUES (%s, 'Digital Ocean', %s, %s, %s)
    """
    with db_conn.cursor() as cur:
        cur.execute(q, vals)
        db_conn.commit()


def drain_droplet_in_db_table(db_conn, dr):
    q = """UPDATE test_helper_instances
    SET draining_at = NOW()
    WHERE name = %s AND provider = 'Digital Ocean' AND region = %s
    """
    vals = [dr.name, dr.region["slug"]]
    with db_conn.cursor() as cur:
        cur.execute(q, vals)
        db_conn.commit()


def delete_droplet_from_db_table(db_conn, dr):
    q = """DELETE FROM test_helper_instances
    WHERE name = %s AND provider = 'Digital Ocean' AND region = %s
    """
    vals = [dr.name, dr.region["slug"]]
    with db_conn.cursor() as cur:
        cur.execute(q, vals)
        db_conn.commit()


@metrics.timer("destroy_drained_droplets")
def destroy_drained_droplets(db_conn, api, draining_time_minutes, live_droplets):
    q = """SELECT name FROM test_helper_instances
    WHERE provider = 'Digital Ocean'
    AND draining_at IS NOT NULL
    AND draining_at < NOW() - interval '%s minutes ago'
    ORDER BY draining_at
    """
    v = [draining_time_minutes]
    with db_conn.cursor() as cur:
        cur.execute(q, v)
        oldest = cur.fetchone()

    if oldest:
        oldest = oldest[0]
    else:
        log.info("No droplet to destroy")
        return

    to_delete = [d for d in live_droplets if d.name == oldest]
    for droplet in to_delete:
        log.info(f"Destroying {droplet.name} droplet")
        delete_droplet_from_db_table(db_conn, droplet)
        droplet.destroy()


@metrics.timer("spawn_new_droplet")
def spawn_new_droplet(api, dig_oc_token, live_regions, conf):
    regions = set(r.slug for r in api.get_all_regions() if r.available is True)
    preferred_regions = regions - live_regions

    ssh_keys = api.get_all_sshkeys()
    # log.debug(ssh_keys)
    img = conf["image_name"]
    assert img
    size_slug = conf["size_slug"]
    assert size_slug
    with open(setup_script_path) as f:
        user_data = f.read()
    for attempt in range(20):
        name = datetime.utcnow().strftime("roaming-th-%Y%m%d%H%M%S")
        region = random.choice(list(preferred_regions or regions))
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
    timeout = time.time() + 60 * 10
    while time.time() < timeout:
        time.sleep(5)
        for action in droplet.get_actions():
            action.load()
            if action.status == "completed":
                log.info("Spawning completed, waiting warmup")
                time.sleep(10)
                return api.get_droplet(droplet.id)

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


def drain_droplet_if_needed(db_conn, live_droplets, active_droplets_count):
    q = """SELECT name FROM test_helper_instances
        WHERE provider = 'Digital Ocean'
        AND draining_at IS NULL
    """
    with db_conn.cursor() as cur:
        cur.execute(q)
        active = set(row[0] for row in cur.fetchall())
    active_droplets = [d for d in live_droplets if d.name in active]
    log.info(f"{len(active_droplets)} active droplets")

    if len(active_droplets) > active_droplets_count:
        by_age = sorted(active_droplets, key=lambda d: d.created_at)
        oldest = by_age[0]
        log.info(f"Draining {oldest.name} droplet")
        drain_droplet_in_db_table(db_conn, oldest)


@metrics.timer("create_le_do_ssl_cert")
def create_le_do_ssl_cert():
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
        "*.th.ooni.org",
        "-n"
    ]
    log.info("Creating/refreshing wildcard certificate *.th.ooni.org")
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


@metrics.timer("ssh_reload_nginx")
@retry
def ssh_reload_nginx(host: str) -> None:
    """Reload Nginx over SSH"""
    cmd = [
        "ssh",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "BatchMode=yes",
        "-i",
        "/etc/ooni/testhelper_ssh_key",
        host,
        "systemctl",
        "reload",
        "nginx",
    ]
    log.info("Reloading nginx")
    log.info(" ".join(cmd))
    check_output(cmd)


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
    x = [r for r in records if r.name == name and r.type == rtype]
    if x:
        x = x[0]
        url = f"domains/{zone}/records/{x.id}"
        changes = dict(data=ip_address)
        log.info(f"Updating existing DNS record {x.id} {rtype} {name} {zone} {ip_address}")
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
def update_dns_records(dig_oc_token: str, zone: str, droplets) -> None:
    # Number droplets starting from the newest
    droplets = sorted(droplets, key=lambda d: d.name, reverse=True)
    vals = [(n, d.ip_address, d.ip_v6_address) for n, d in enumerate(droplets)]
    update_or_create_dns_records(dig_oc_token, zone, vals)


@metrics.timer("deploy_ssl_cert")
def deploy_ssl_cert(host: str, zone: str) -> None:
    cert_fname = f"/etc/letsencrypt/live/{zone}/fullchain.pem"
    privkey_fname = f"/etc/letsencrypt/live/{zone}/privkey.pem"
    scp_file(cert_fname, host, "/etc/ssl/private/th_fullchain.pem")
    scp_file(privkey_fname, host, "/etc/ssl/private/th_privkey.pem")
    scp_file(nginx_conf, host, "/etc/nginx/sites-enabled/default")
    ssh_reload_nginx(host)


@metrics.timer("run_time")
def main():
    conf = load_conf()

    dig_oc_token = conf["token"]
    assert dig_oc_token
    assert len(dig_oc_token) == 64
    draining_time_minutes = int(conf["draining_time_minutes"])
    assert draining_time_minutes >= 0

    active_droplets_count = int(conf["active_droplets_count"])
    assert 0 <= active_droplets_count < 100
    assert Path(setup_script_path).is_file()
    assert Path(certbot_creds).is_file()
    assert Path(nginx_conf).is_file()
    dns_zone = conf["dns_zone"]
    assert dns_zone

    api = digitalocean.Manager(token=dig_oc_token)
    # Fetch all test-helper droplets
    droplets = api.get_all_droplets(tag_name=TAG)
    for d in droplets:
        assert TAG in d.tags
    live_droplets = [d for d in droplets if d.status == "active"]
    log.info(f"{len(droplets)} droplets")
    log.info(f"{len(live_droplets)} live droplets")

    # Avoid failure modes where we destroy all VMs or create unlimited amounts
    # or churn too quickly
    db_conn = psycopg2.connect(conf["db_uri"])

    destroy_drained_droplets(db_conn, api, draining_time_minutes, live_droplets)

    # Drain a droplet if needed
    drain_droplet_if_needed(db_conn, live_droplets, active_droplets_count)

    if len(live_droplets) > active_droplets_count:
        log.info(f"No need to spawn a new droplet {len(live_droplets)} > {active_droplets_count}")
        sys.exit(0)

    if len(droplets) > active_droplets_count + 2:
        log.error("Unexpected amount of running droplets")
        sys.exit(1)

    # Spawn a new droplet
    live_regions = set(d.region["slug"] for d in droplets)
    new_droplet = spawn_new_droplet(api, dig_oc_token, live_regions, conf)
    log.info(f"Droplet {new_droplet.name} ready at {new_droplet.ip_address}")
    add_droplet_to_db_table(db_conn, new_droplet)
    live_droplets.append(new_droplet)

    create_le_do_ssl_cert()
    # Deploy SSL certificate to new droplet
    deploy_ssl_cert(f"root@{new_droplet.ip_address}", dns_zone)

    # Update DNS A/AAAA records only when a new droplet is deployed
    update_dns_records(dig_oc_token, dns_zone, live_droplets)


if __name__ == "__main__":
    main()
