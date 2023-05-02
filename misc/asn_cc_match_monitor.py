#!/usr/bin/env python3

from time import sleep

import systemd.journal
import geoip2.database  # type: ignore

asnfn = "/var/lib/ooniapi/asn.mmdb"
ccfn = "/var/lib/ooniapi/cc.mmdb"
geoip_asn_reader = geoip2.database.Reader(asnfn)
geoip_cc_reader = geoip2.database.Reader(ccfn)


def follow_journal():
    journal = systemd.journal.Reader()
    #journal.seek_tail()
    journal.get_previous()
    journal.add_match(_SYSTEMD_UNIT="nginx.service")
    while True:
        try:
            event = journal.wait(-1)
            if event == systemd.journal.APPEND:
                for entry in journal:
                    yield entry["MESSAGE"]
        except Exception as e:
            print(e)
            sleep(0.1)


def geolookup(ipaddr: str):
    cc = geoip_cc_reader.country(ipaddr).country.iso_code
    asn = geoip_asn_reader.asn(ipaddr).autonomous_system_number
    return cc, asn


def process(rawmsg):
    if ' "POST /report/' not in rawmsg:
        return
    msg = rawmsg.strip().split()
    ipaddr = msg[2]
    ipaddr2 = msg[3]
    path = msg[8][8:]
    tsamp, tn, probe_cc, probe_asn, collector, rand = path.split("_")
    geo_cc, geo_asn = geolookup(ipaddr)
    proxied = 0
    probe_type = rawmsg.rsplit('"', 2)[-2]
    if "," in probe_type:
        return
    if ipaddr2 != "0.0.0.0":
        proxied = 1
        # Probably CloudFront, use second ipaddr
        geo_cc, geo_asn = geolookup(ipaddr2)

    print(f"{probe_cc},{geo_cc},{probe_asn},{geo_asn},{proxied},{probe_type}")


def main():
    for msg in follow_journal():
        if msg is None:
            break
        try:
            process(msg)
        except Exception as e:
            print(e)
            sleep(0.1)


if __name__ == "__main__":
    main()
