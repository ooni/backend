#!/usr/bin/env python2.7

import argparse
import bz2
import re
import sys

import psycopg2

from centrifugation import PostgresSource


class OriginasStream(PostgresSource):
    columns = ("origin", "asn")

    def _iter(self, fileobj):
        # ASN, IP-NET, bits
        reasset = re.compile(r'^[0-9\.*]+\s+IN TXT\s+"{[0-9,]+}" "[0-9\.]+" "\d+"')
        regex = re.compile(r'^[0-9\.*]+\s+IN TXT\s+"(\d+)" "([0-9\.]+)" "(\d+)"')
        last = None
        for line in fileobj:
            m = regex.match(line)
            if not m:
                if reasset.match(line):
                    continue  # XXX: AS-SET are skipped for the moment
                else:
                    raise RuntimeError("Unparsable line", line)
            row = m.groups()
            if last != row:  # skip consequent duplicates
                asn, ipnet, bits = last = row
                asn = int(asn)
                if (
                    asn < 64512 or 65535 < asn < 4200000000
                ):  # drop private ASNs from RFC6996
                    yield "{}/{}\t{}\n".format(ipnet, bits, asn)


def parse_args():
    p = argparse.ArgumentParser(
        description="ooni-pipeline: originas.bz2 -> postgres/table"
    )
    p.add_argument(
        "--originas", metavar="FILE", help="path to originas.bz2", required=True
    )
    p.add_argument(
        "--postgres", metavar="DSN", help="libpq data source name", required=True
    )
    p.add_argument("--table", help="postgres table name", default="originas")
    opt = p.parse_args()
    return opt


def main():
    opt = parse_args()
    with psycopg2.connect(opt.postgres) as conn, conn.cursor() as c:
        # probably that's not the most simple way to filter out uniq records
        c.execute(
            "CREATE TEMPORARY TABLE tmp (LIKE {} INCLUDING DEFAULTS)".format(opt.table)
        )
        source = OriginasStream(bz2.BZ2File(opt.originas, "r"))
        c.copy_from(source, "tmp", columns=source.columns)
        c.execute("TRUNCATE TABLE {}".format(opt.table))
        c.execute("INSERT INTO {} SELECT DISTINCT * FROM tmp".format(opt.table))


if __name__ == "__main__":
    main()
