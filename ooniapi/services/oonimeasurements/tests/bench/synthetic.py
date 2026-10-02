"""
Deterministic synthetic data for benchmarks.

Rows are generated server side from numbers() so that large sizes are cheap to
build. Every value derives from cityHash64(number, salt), so the same size and
anchor date always produce the same dataset: responses from a baseline run and
a tuned run can be compared byte for byte.
"""

import hashlib
import os
import re
from pathlib import Path

from oonimeasurements.routers.private import TEST_GROUPS

TESTS_DIR = Path(__file__).parent.parent
INITDB_DIR = TESTS_DIR / "fixtures" / "initdb"
MIGRATIONS_DIR = TESTS_DIR / "migrations"

DAYS = int(os.environ.get("OONI_BENCH_DAYS", 180))
if DAYS < 2:
    # some benchmarked endpoints default to windows ending before yesterday
    raise ValueError(f"OONI_BENCH_DAYS must be at least 2, got {DAYS}")
URL_COUNT = 3000
COUNTRIES = [
    "US", "IT", "DE", "RU", "IR", "CN", "IN", "BR", "GB", "FR",
    "MY", "TH", "VE", "UA", "TR", "EG", "MX", "ID", "PK", "NG",
    "KZ", "BY", "MM", "CU", "SA", "AE", "ET", "UG", "CA", "AU",
    "JP", "KR", "ES", "NL", "SE", "PL", "AR", "CO", "PH", "VN",
]
ASNS_PER_COUNTRY = 30
CATEGORY_CODES = ["NEWS", "HUMR", "POLR", "GRP", "LGBT", "REL", "COMT", "MMED", "CULTR", "ANON"]


def _schema_files():
    yield INITDB_DIR / "01-scheme.sql"
    yield INITDB_DIR / "03-faulty-msm-detection.sql"
    yield from sorted(MIGRATIONS_DIR.iterdir())


def _ddl_statements():
    for path in _schema_files():
        lines = [l for l in path.read_text().split("\n") if not l.startswith("--")]
        for stmt in "\n".join(lines).split(";"):
            stmt = stmt.strip()
            # data fixtures are not part of the schema
            if not stmt or stmt.upper().startswith("INSERT"):
                continue
            yield re.sub(r"\bdefault\.", "", stmt)


def schema_fingerprint() -> str:
    """Changes whenever the schema or this generator does."""
    source = "\n".join(_ddl_statements()) + Path(__file__).read_text()
    return hashlib.sha256(source.encode()).hexdigest()[:16]


def create_schema(click):
    for stmt in _ddl_statements():
        click.execute(stmt)


def _h(salt: int, key: str = "number") -> str:
    return f"cityHash64({key}, {salt})"


def _skewed_index(salt: int, size: int, key: str) -> str:
    # 1-based index with a heavy head: a few countries/urls dominate, like prod
    return f"1 + toUInt32(pow(({_h(salt, key)} % 10000) / 10000, 2) * {size})"


def _array(values) -> str:
    return "[" + ",".join(f"'{v}'" for v in values) + "]"


def _cc(key="number"):
    return f"arrayElement({_array(COUNTRIES)}, least({_skewed_index(1, len(COUNTRIES), key)}, {len(COUNTRIES)}))"


def _asn(key="number"):
    return f"toUInt32(1000 + indexOf({_array(COUNTRIES)}, probe_cc) * 100 + {_h(2, key)} % {ASNS_PER_COUNTRY})"


def _url_idx(key="number"):
    return f"least({_skewed_index(4, URL_COUNT, key)}, {URL_COUNT}) - 1"


def _mst(n, key="number"):
    return f"toDateTime(today() - {DAYS}) + intDiv({key} * {DAYS * 86400}, {n}) + {_h(3, key)} % 60"


def _uid(test_name_expr, key="number", delay=None):
    # collection delay: usually seconds, sometimes days (late uploads)
    delay = delay or f"if({_h(10, key)} % 100 < 2, {_h(10, key)} % 259200, {_h(10, key)} % 120)"
    return (
        f"concat(formatDateTime(measurement_start_time + {delay}, '%Y%m%d%H%i%S'), '.',"
        f" leftPad(toString({_h(8, key)} % 1000000), 6, '0'), '_', probe_cc, '_',"
        f" replaceAll({test_name_expr}, '_', ''), '_', lower(substring(hex({_h(9, key)}), 1, 16)))"
    )


def _report_id(test_name_expr, key="number"):
    return (
        f"concat(formatDateTime(measurement_start_time, '%Y%m%dT%H%i%SZ'), '_',"
        f" replaceAll({test_name_expr}, '_', ''), '_', probe_cc, '_', toString(probe_asn),"
        f" '_n1_', substring(hex({_h(7, key)}), 1, 16))"
    )


# fastpath measurements belong to reports, like in production: a report's
# measurements share its probe, test and report_id and are spread over its run,
# so thousands of reports overlap in time; measurements are collected (uid)
# after a lag and the report_id timestamp is when the collector opened the
# report. Distributions follow production data2 (2026-10).
MEASUREMENTS_PER_REPORT = 4
REPORT = f"intDiv(number, {MEASUREMENTS_PER_REPORT})"


def _report_start(n):
    reports = -(-n // MEASUREMENTS_PER_REPORT)
    # every report starts at least a minute before the end of the window
    return f"(toDateTime(today() - {DAYS}) + intDiv({REPORT} * {DAYS * 86400 - 120}, {reports}) + {_h(3, REPORT)} % 60)"


def _report_duration(n):
    # 60% 2-20 s, 25% up to 10 min, 10% up to 2 h, 4.9% up to 14 h, 0.1% 1-3 days
    h = f"{_h(20, REPORT)} % 1000"
    r = f"{_h(21, REPORT)}"
    d = f"multiIf({h} < 600, 2 + {r} % 18, {h} < 850, 20 + {r} % 580, {h} < 950, 600 + {r} % 6600, {h} < 999, 7200 + {r} % 43200, 86400 + {r} % 172800)"
    # reports still running at the end of the window are cut short
    return f"least({d}, dateDiff('second', {_report_start(n)}, toDateTime(today())) - {2 * MEASUREMENTS_PER_REPORT})"


def _report_mst(n):
    # spread over the run, at least a second apart so the sort key stays unique
    i = f"(number % {MEASUREMENTS_PER_REPORT})"
    return f"{_report_start(n)} + {i} + intDiv({i} * {_report_duration(n)}, {MEASUREMENTS_PER_REPORT})"


def _report_opened(n):
    # report_id time after the report's first measurement: 85% 3-20 s, 10% up to 2 min, 4.9% up to 1 h, 0.1% 11-25 h
    h = f"{_h(22, REPORT)} % 1000"
    r = f"{_h(23, REPORT)}"
    return f"({_report_start(n)} + multiIf({h} < 850, 3 + {r} % 17, {h} < 950, 20 + {r} % 100, {h} < 999, 120 + {r} % 3480, 39600 + {r} % 50400))"


def _collection_lag():
    # 3% -1..-30 s (fast clocks), 50% 1-5 s, 40% 5-30 s, 6% 30-200 s, 0.9% 200 s-4 h, 0.1% 4 h-3 days
    h = f"{_h(10)} % 10000"
    r = f"toInt64({_h(24)} % 244800)"
    return f"multiIf({h} < 300, -1 - {r} % 30, {h} < 5300, 1 + {r} % 5, {h} < 9300, 5 + {r} % 25, {h} < 9900, 30 + {r} % 170, {h} < 9990, 200 + {r} % 14200, 14400 + {r})"


def _report_id_opened(n, test_name_expr):
    return (
        f"concat(formatDateTime({_report_opened(n)}, '%Y%m%dT%H%i%SZ'), '_',"
        f" replaceAll({test_name_expr}, '_', ''), '_', probe_cc, '_', toString(probe_asn),"
        f" '_n1_', substring(hex({_h(7, REPORT)}), 1, 16))"
    )


def _test_name_expr(key="number") -> str:
    buckets = [
        (70, "web_connectivity"), (76, "signal"), (80, "whatsapp"), (83, "telegram"),
        (85, "facebook_messenger"), (88, "tor"), (90, "torsf"), (92, "psiphon"),
        (94, "riseupvpn"), (96, "dnscheck"), (98, "ndt"),
    ]
    args = ", ".join(f"r < {b}, '{t}'" for b, t in buckets)
    return f"multiIf({args}, 'http_invalid_request_line')".replace("r <", f"{_h(18, key)} % 100 <")


def insert_citizenlab(click):
    click.execute(
        f"""
        INSERT INTO citizenlab (domain, url, cc, category_code)
        SELECT
            concat('site', toString(number), '.example.org') AS domain,
            concat('https://', domain, '/') AS url,
            if(number < {URL_COUNT - 500}, 'ZZ', lower(arrayElement({_array(COUNTRIES)}, 1 + number % {len(COUNTRIES)}))) AS cc,
            arrayElement({_array(CATEGORY_CODES)}, 1 + {_h(30)} % {len(CATEGORY_CODES)}) AS category_code
        FROM numbers({URL_COUNT})
        """
    )


def insert_lookup_tables(click):
    click.execute(
        "INSERT INTO test_groups (test_name, test_group) VALUES",
        [(tn, tg) for tg, names in TEST_GROUPS.items() for tn in names],
    )
    click.execute(
        f"""
        INSERT INTO asnmeta (asn, org_name, cc, changed, aut_name, source)
        SELECT
            toUInt32(1000 + intDiv(number, {ASNS_PER_COUNTRY}) * 100 + number % {ASNS_PER_COUNTRY}) AS asn,
            concat('Synthetic Network ', toString(asn)),
            arrayElement({_array(COUNTRIES)}, least(intDiv(number, {ASNS_PER_COUNTRY}), {len(COUNTRIES)})),
            today() - 30, concat('AS', toString(asn)), 'synthetic'
        FROM numbers({(len(COUNTRIES) + 1) * ASNS_PER_COUNTRY})
        """
    )


def insert_fastpath(click, n: int):
    click.execute(
        f"""
        INSERT INTO fastpath (
            measurement_uid, report_id, input, probe_cc, probe_asn, test_name,
            test_start_time, measurement_start_time, filename, scores, platform,
            anomaly, confirmed, msm_failure, domain, software_name, software_version,
            control_failure, blocking_general, is_ssl_expected, page_len, page_len_ratio,
            server_cc, server_asn, server_as_name, test_version, architecture,
            engine_name, engine_version, test_runtime, blocking_type,
            test_helper_address, test_helper_type, ooni_run_link_id, is_verified
        )
        SELECT
            {_uid('test_name', delay=_collection_lag())},
            {_report_id_opened(n, 'test_name')},
            multiIf(test_name = 'web_connectivity', concat('https://site', toString({_url_idx()}), '.example.org/'),
                    test_name = 'dnscheck', 'https://dns.google/dns-query', '') AS input,
            {_cc(REPORT)} AS probe_cc,
            {_asn(REPORT)} AS probe_asn,
            {_test_name_expr(REPORT)} AS test_name,
            {_report_start(n)},
            {_report_mst(n)} AS measurement_start_time,
            '',
            multiIf(
                test_name IN ('tor', 'torsf', 'psiphon', 'riseupvpn'),
                concat('{{"extra":{{"test_runtime":', toString(({_h(12)} % 3000) / 100), '}}}}'),
                concat('{{"blocking_general":0.0,"analysis":{{"blocking_type":"', blocking_type, '"}}}}')
            ),
            arrayElement(['android', 'ios', 'linux', 'macos', 'windows'], 1 + {_h(13)} % 5),
            if({_h(5)} % 100 < 8, 't', 'f') AS anomaly,
            if({_h(5)} % 1000 < 5, 't', 'f'),
            if({_h(6)} % 100 < 3, 't', 'f'),
            if(input = '', '', domain(input)) AS domain,
            arrayElement(['ooniprobe-android', 'ooniprobe-cli', 'ooniprobe-desktop-unattended'], 1 + {_h(14)} % 3),
            arrayElement(['3.20.0', '3.24.0', '5.3.0'], 1 + {_h(15)} % 3),
            '', 0, 0, 0, 0, '', 0, '',
            '0.4.3', 'arm64', 'ooniprobe-engine',
            arrayElement(['3.20.0', '3.24.0', '3.28.0'], 1 + {_h(15)} % 3),
            ({_h(12)} % 3000) / 100,
            if(anomaly = 't' AND test_name = 'web_connectivity', arrayElement(['dns', 'tcp_ip', 'http-failure', 'http-diff'], 1 + {_h(16)} % 4), '') AS blocking_type,
            'https://1.th.ooni.org', 'https',
            if({_h(17)} % 100 < 5, toNullable(toUInt64(10000 + {_h(17)} % 50)), NULL),
            'u'
        FROM numbers({n})
        """,
    )


def insert_obs_web(click, n: int):
    # four observations per measurement (dns, tcp, tls, http); `m` keys the
    # measurement. Measurements close in time differ in m % 250, so every
    # observation gets a distinct start time and ordering by it is total.
    m = "intDiv(number, 4)"
    idx = "number % 4"
    blocked = f"({_h(20, m)} % 100 < 10)"
    click.execute(
        f"""
        INSERT INTO obs_web (
            measurement_uid, observation_idx, input, report_id, measurement_start_time,
            software_name, software_version, test_name, test_version, bucket_date,
            probe_asn, probe_cc, probe_as_org_name, probe_as_cc, probe_as_name,
            network_type, platform, origin, engine_name, engine_version, architecture,
            resolver_ip, resolver_asn, resolver_cc, resolver_as_org_name, resolver_as_cc,
            hostname, ip, port, ip_asn, dns_query_type, dns_failure, dns_answer,
            tcp_failure, tcp_success, tls_failure, tls_server_name,
            http_request_url, http_failure, http_response_status_code, created_at
        )
        SELECT
            {_uid("'web_connectivity'", m)},
            {idx},
            concat('https://', hostname, '/'),
            {_report_id("'web_connectivity'", m)},
            addMilliseconds(toDateTime64({_mst(n // 4, m)}, 3), {m} % 250 * 4 + {idx}) AS measurement_start_time,
            'ooniprobe-cli', '3.20.0', 'web_connectivity', '0.4.3', toString(toDate(measurement_start_time)),
            {_asn(m)} AS probe_asn,
            {_cc(m)} AS probe_cc,
            concat('Synthetic Network ', toString(probe_asn)), probe_cc, '',
            'wifi', 'linux', 'pipeline', 'ooniprobe-engine', '3.20.0', 'amd64',
            '8.8.8.8',
            if({_h(21, m)} % 100 < 60, probe_asn, arrayElement([15169, 13335], 1 + {_h(21, m)} % 2)) AS resolver_asn,
            probe_cc, '', probe_cc,
            concat('site', toString({_url_idx(m)}), '.example.org') AS hostname,
            if({idx} = 0, NULL, IPv4NumToString(toUInt32(167772160 + {_h(22, m)} % 16777216))) AS ip,
            if({idx} IN (1, 2), toNullable(toUInt16(443)), NULL),
            if(ip IS NULL, NULL, toNullable(toUInt32(13335))),
            if({idx} = 0, 'A', NULL),
            if({idx} = 0 AND {blocked} AND {_h(23, m)} % 4 = 0, 'dns_nxdomain_error', NULL),
            if({idx} = 0, IPv4NumToString(toUInt32(167772160 + {_h(22, m)} % 16777216)), NULL),
            if({idx} = 1 AND {blocked} AND {_h(23, m)} % 4 = 1, 'generic_timeout_error', NULL),
            if({idx} = 1, toNullable(toUInt8(NOT ({blocked} AND {_h(23, m)} % 4 = 1))), NULL),
            if({idx} = 2 AND {blocked} AND {_h(23, m)} % 4 = 2, 'connection_reset', NULL),
            if({idx} = 2, hostname, NULL),
            if({idx} = 3, concat('https://', hostname, '/'), NULL),
            if({idx} = 3 AND {blocked} AND {_h(23, m)} % 4 = 3, 'eof_error', NULL),
            if({idx} = 3, toNullable(toUInt16(200)), NULL),
            toDateTime(measurement_start_time) + 3600
        FROM numbers({n})
        """,
    )


def insert_analysis_web_measurement(click, n: int):
    blocked = f"({_h(20)} % 100 < 10)"
    click.execute(
        f"""
        INSERT INTO analysis_web_measurement (
            domain, input, test_name, probe_asn, probe_as_org_name, probe_cc,
            resolver_asn, resolver_as_cc, network_type, measurement_start_time,
            measurement_uid, ooni_run_link_id, top_probe_analysis, top_dns_failure,
            top_tcp_failure, top_tls_failure, dns_blocked, dns_down, dns_ok,
            tcp_blocked, tcp_down, tcp_ok, tls_blocked, tls_down, tls_ok
        )
        SELECT
            concat('site', toString({_url_idx()}), '.example.org') AS domain,
            concat('https://', domain, '/'),
            'web_connectivity',
            {_asn()} AS probe_asn,
            concat('Synthetic Network ', toString(probe_asn)),
            {_cc()} AS probe_cc,
            probe_asn, probe_cc, 'wifi',
            {_mst(n)} AS measurement_start_time,
            {_uid("'web_connectivity'")},
            if({_h(17)} % 100 < 5, toString(10000 + {_h(17)} % 50), ''),
            if({blocked}, 'tcp.generic_timeout_error', 'ok'),
            if({blocked} AND {_h(23)} % 3 = 0, 'dns_nxdomain_error', NULL),
            if({blocked} AND {_h(23)} % 3 = 1, 'generic_timeout_error', NULL),
            if({blocked} AND {_h(23)} % 3 = 2, 'connection_reset', NULL),
            if({blocked} AND {_h(23)} % 3 = 0, 0.9, 0.0) AS dns_blocked, 0.05, 1 - dns_blocked,
            if({blocked} AND {_h(23)} % 3 = 1, 0.8, 0.0) AS tcp_blocked, 0.05, 1 - tcp_blocked,
            if({blocked} AND {_h(23)} % 3 = 2, 0.8, 0.0) AS tls_blocked, 0.05, 1 - tls_blocked
        FROM numbers({n})
        """,
    )


def insert_changepoints(click, n: int):
    click.execute(
        f"""
        INSERT INTO event_detector_changepoints (
            probe_asn, probe_cc, domain, ts, count_isp_resolver, count_other_resolver,
            count, dns_isp_blocked, change_dir, s_pos, s_neg, h, block_type
        )
        SELECT
            {_asn()} AS probe_asn, {_cc()} AS probe_cc,
            concat('site', toString({_url_idx()}), '.example.org'),
            toDateTime(today() - {DAYS}) + intDiv(number * {DAYS * 86400}, {n}),
            1, 1, 2, 0.8, if({_h(24)} % 2 = 0, 1, -1), 0.1, 0.1, 3.5,
            arrayElement(['dns_isp_block', 'tcp_block', 'tls_block'], 1 + {_h(24)} % 3)
        FROM numbers({n})
        """
    )


def populate(click, rows: int):
    insert_citizenlab(click)
    insert_lookup_tables(click)
    insert_fastpath(click, rows)
    insert_obs_web(click, rows * 3)
    insert_analysis_web_measurement(click, rows * 7 // 10)
    insert_changepoints(click, max(rows // 1000, 10))
    # merged like production, and the same part layout, so the same bytes
    # read, whenever background merges would otherwise have run
    for table in ("fastpath", "obs_web", "analysis_web_measurement"):
        click.execute(f"OPTIMIZE TABLE {table} FINAL")
