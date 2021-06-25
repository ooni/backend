#!/usr/bin/env python3
"""
Spaws and rotates hosts on Digital Ocean. Runs a setup script on the host
at first boot.
Reads /etc/ooni/rotation.conf
Keeps a list of live hosts in a dedicated db table.
Runs as a SystedD timer.

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
--

"""

from configparser import ConfigParser
from datetime import datetime
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
TAG = "roaming-th"


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
    region = random.choice(list(preferred_regions or regions))

    name = datetime.utcnow().strftime("roaming-th-%Y%m%d%H%M%S")
    log.info(f"Spawning {name} in {region}")
    ssh_keys = api.get_all_sshkeys()
    img = conf["image_name"]
    assert img
    size_slug = conf["size_slug"]
    assert size_slug
    with open(setup_script_path) as f:
        user_data = f.read()
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

    timeout = time.time() + 60 * 10
    while time.time() < timeout:
        time.sleep(5)
        for action in droplet.get_actions():
            action.load()
            if action.status == "completed":
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

    api = digitalocean.Manager(token=dig_oc_token)
    # Fetch all test-helper droplets
    droplets = api.get_all_droplets(tag_name=TAG)
    for d in droplets:
        assert TAG in d.tags
    live_droplets = [d for d in droplets if d.status == "active"]
    log.info(f"{len(droplets)} droplets")
    log.info(f"{len(live_droplets)} powered on droplets")

    # Avoid failure modes where we destroy all VMs or create unlimited amounts
    # or churn too quickly
    db_conn = psycopg2.connect(conf["db_uri"])

    destroy_drained_droplets(db_conn, api, draining_time_minutes, live_droplets)

    # Drain a droplet if needed
    drain_droplet_if_needed(db_conn, live_droplets, active_droplets_count)

    # Spawn a new droplet if needed
    if len(live_droplets) <= active_droplets_count:
        if len(droplets) > active_droplets_count + 2:
            log.error("Unexpected amount of running droplets")
            sys.exit(1)
        live_regions = set(d.region["slug"] for d in droplets)
        droplet = spawn_new_droplet(api, dig_oc_token, live_regions, conf)
        log.info(f"Droplet {droplet.name} ready at {droplet.ip_address}")
        add_droplet_to_db_table(db_conn, droplet)


if __name__ == "__main__":
    main()
