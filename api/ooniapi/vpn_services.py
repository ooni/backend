"""
VPN Services

Insert credentials into database.
"""
import base64
import datetime
import json
import logging
from argparse import ArgumentParser
from dataclasses import dataclass

from ooniapi.database import query_click, insert_click

import pem
import requests

RISEUP_CA_URL = "https://api.black.riseup.net/ca.crt"
RISEUP_CERT_URL = "https://api.black.riseup.net/3/cert"

# Do not bother using credentials older than these, in days
# This also means that we need to ensure we're inserting new credentials at a shorter period.
CREDENTIAL_FRESHNESS_INTERVAL_DAYS=7

log = logging.getLogger()

@dataclass
class CertificateCredentials:
    key: str
    cert: str

@dataclass
class OpenVPNCredentials:
    provider: str
    ts: datetime.datetime
    config: dict

def as_base64(s):
    encoded = base64.b64encode(s)
    return f"base64:{encoded}"

def fetch_riseup_ca():
   r = requests.get(RISEUP_CA_URL)
   if r.status_code == 200:
       return r.text.strip().encode('utf-8')

def fetch_riseup_cert():
    r = requests.get(RISEUP_CERT_URL)
    if r.status_code == 200:
        return r.text.strip().encode('utf-8')

def parse_certificate(s):
    parts = pem.parse(s)
    key, cert = parts
    return CertificateCredentials(key.as_text().encode('utf-8'), cert.as_text().encode('utf-8'))

def create_options_with_credentials():
    ca = fetch_riseup_ca()
    creds = parse_certificate(fetch_riseup_cert())
    return json.dumps({
        'ca': as_base64(ca),
        'cert': as_base64(creds.cert),
        'key': as_base64(creds.key)
    })


def insert_vpn_credentials(clickfn=None):
    if clickfn is None:
        clickfn = insert_click

    try:
        config_json = create_options_with_credentials()
    except Exception as e:
        log.warning(f"error fetching credentials: {e}")
        return

    row = dict(
        provider="riseup",
        config=config_json,
        fetched_date=datetime.datetime.now(),
    )
    sql_ins = """INSERT INTO vpn_services (provider, config, fetched_date) VALUES"""
    clickfn(sql_ins, [row])

def query_vpn_credentials(clickfn=None, active=True):
    if clickfn is None:
        clickfn = query_click

    sql_query = """SELECT provider,fetched_date,config FROM vpn_services
    WHERE (provider = 'riseup')"""

    interval_days = CREDENTIAL_FRESHNESS_INTERVAL_DAYS
    if active:
        sql_query += f" AND (fetched_date >= now() - toIntervalDay({interval_days}))"

    rows = clickfn(sql_query, {})

    return (
        OpenVPNCredentials(
            provider=entry["provider"],
            ts=entry["fetched_date"],
            config=entry["config"],
        ) for entry in rows)


if __name__ == "__main__":
    import sys
    import os

    def get_click_client():
        from clickhouse_driver import Client as Clickhouse
        click = Clickhouse.from_url(CLICKHOUSE_URL)
        return click

    CLICKHOUSE_URL = os.environ.get("CLICKHOUSE_URL", None)
    if CLICKHOUSE_URL is None:
        print("Please set CLICKHOUSE_URL")
        sys.exit(1)

    click = get_click_client()

    ap = ArgumentParser()
    ap.add_argument("--insert", action="store_true")
    ap.add_argument("--query", action="store_true")
    conf = ap.parse_args()

    if conf.insert:
        insert_vpn_credentials(click.execute)
        print("ok")
        sys.exit(0)

    if conf.query:
        def _run_query(query, query_params, query_prio=3):
            rows, coldata = click.execute(query, query_params, with_column_types=True)
            colnames, _ = tuple(zip(*coldata))
            return [dict(zip(colnames, row)) for row in rows]

        creds = query_vpn_credentials(clickfn=_run_query, active=True)
        for c in creds:
            print(c.provider, c.ts)
        sys.exit(0)
