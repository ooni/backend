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
from datetime import date
from pathlib import Path

from oonimeasurements.routers.private import TEST_GROUPS

from .production_shape import COUNTRIES as COUNTRY_SHAPE, TESTS as TEST_SHAPE

TESTS_DIR = Path(__file__).parent.parent
INITDB_DIR = TESTS_DIR / "fixtures" / "initdb"
MIGRATIONS_DIR = TESTS_DIR / "migrations"

DAYS = int(os.environ.get("OONI_BENCH_DAYS", 180))
if DAYS < 2:
    # some benchmarked endpoints default to windows ending before yesterday
    raise ValueError(f"OONI_BENCH_DAYS must be at least 2, got {DAYS}")
# the day the dataset ends; pin it so that a dataset built on one day can be
# reused on the next instead of being rebuilt
ANCHOR_DATE = date.fromisoformat(os.environ.get("OONI_BENCH_ANCHOR") or date.today().isoformat())
TODAY = f"toDate('{ANCHOR_DATE.isoformat()}')"
COUNTRIES = [cc for cc, _, _ in COUNTRY_SHAPE]
# a country's networks: those production saw in a day (~1400 ASNs in all)
COUNTRY_ASNS = [asns for _, _, asns in COUNTRY_SHAPE]
ASN_BASE = 300000  # clear of the real ASNs below
# a few networks show up in many countries (VPNs, clouds): 4% of production
# ASNs are seen in more than one country, the most spread in 22
GLOBAL_ASNS = [14593, 212238, 9009, 13335, 16276, 210644, 36924, 208172]
GLOBAL_ASN_PER_10000 = 8
TEST_NAMES = [t for t, _, _, _, _ in TEST_SHAPE]
CATEGORY_CODES = [
    "NEWS", "HUMR", "POLR", "GRP", "LGBT", "REL", "COMT", "MMED", "CULTR", "ANON",
    "ALDR", "PORN", "PROV", "ENV", "MILX", "HATE", "XED", "PUBH", "GMB", "DATE",
    "FILE", "HACK", "HOST", "SRCH", "GAME", "ECON", "GOVT", "COMM", "CTRL", "IGO", "MISC",
]

# web_connectivity inputs, after production (one day of data2, 2026-10): 46K
# distinct inputs a day, 94% of measurements of citizenlab urls. A flat head of
# 100 urls of the global list gets 67% of measurements, the rest of the global
# list (1726 urls) most of the remainder, then each country's own list. CN is
# the long tail: 30K of the 33K unlisted inputs, nearly all seen once, and its
# listed measurements are spread over its lists too. Elsewhere each country
# tests a few unlisted urls over and over: ~2.8K a day in all.
GLOBAL_LIST = 1726
GLOBAL_HEAD = 100
COUNTRY_LIST = 230
COUNTRY_LIST_CN = 8000
UNLISTED_PER_COUNTRY = 80
COUNTRY_LIST_SIZES = [COUNTRY_LIST_CN if cc == "CN" else COUNTRY_LIST for cc in COUNTRIES]
COUNTRY_LIST_OFFSETS = [GLOBAL_LIST + sum(COUNTRY_LIST_SIZES[:i]) for i in range(len(COUNTRIES))]
# per 10000 web_connectivity measurements: cumulative head, global list, country list
WEB_MIX = (7000, 8900, 9600)
# per 10000 CN measurements: cumulative unique, global list (uniform), country list (uniform)
CN_MIX = (7800, 8500)


def _shape_files():
    yield Path(__file__)
    yield Path(__file__).parent / "production_shape.py"


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
    source = "\n".join(_ddl_statements()) + "".join(p.read_text() for p in _shape_files())
    return hashlib.sha256(source.encode()).hexdigest()[:16]


def create_schema(click):
    for stmt in _ddl_statements():
        click.execute(stmt)


def _h(salt: int, key: str = "number") -> str:
    return f"cityHash64({key}, {salt})"


def _skewed(salt: int, size, key: str, power: int = 2) -> str:
    # 0-based index below size, with a heavy head
    return f"toUInt32(pow(({_h(salt, key)} % 10000) / 10000, {power}) * {size})"


def _cumulative(weights) -> str:
    total = 0
    out = []
    for w in weights:
        total += w
        out.append(total)
    return "[" + ",".join(map(str, out)) + "]", total


def _weighted_index(salt: int, weights, key: str) -> str:
    # 1-based index, drawn with the given integer weights
    cum, total = _cumulative(weights)
    return f"arrayFirstIndex(w -> w > {_h(salt, key)} % {total}, {cum})"


def _array(values) -> str:
    return "[" + ",".join(f"'{v}'" for v in values) + "]"


def _array_int(values) -> str:
    return "[" + ",".join(map(str, values)) + "]"


def _cc(key="number"):
    # countries in production proportions
    return f"arrayElement({_array(COUNTRIES)}, {_weighted_index(1, [m for _, m, _ in COUNTRY_SHAPE], key)})"


def country_asn(cc: str, rank: int = 0) -> int:
    """The rank-th network of a country, 0 being its busiest."""
    return ASN_BASE + (COUNTRIES.index(cc) + 1) * 1000 + rank


def _asn(key="number"):
    # within a country, network volume is close to Zipf like in production (US:
    # busiest 17%, top 10 59%); n networks, j = (n + 1)^(x^1.25) - 1
    ci = f"indexOf({_array(COUNTRIES)}, probe_cc)"
    n = f"arrayElement([{','.join(map(str, COUNTRY_ASNS))}], {ci})"
    x = f"(({_h(2, key)} % 10000) / 10000)"
    local = f"{ASN_BASE} + {ci} * 1000 + least(toUInt32(pow({n} + 1, pow({x}, 1.25))) - 1, {n} - 1)"
    shared = f"arrayElement([{','.join(map(str, GLOBAL_ASNS))}], 1 + {_h(44, key)} % {len(GLOBAL_ASNS)})"
    return f"toUInt32(if({_h(43, key)} % 10000 < {GLOBAL_ASN_PER_10000}, {shared}, {local}))"


def _site(idx: str) -> str:
    return f"concat('https://site', toString({idx}), '.example.org/')"


def _web_input(key="number"):
    # see WEB_MIX; country lists follow the global list, in COUNTRIES order
    ci = f"indexOf({_array(COUNTRIES)}, probe_cc)"
    size = f"arrayElement([{','.join(map(str, COUNTRY_LIST_SIZES))}], {ci})"
    offset = f"arrayElement([{','.join(map(str, COUNTRY_LIST_OFFSETS))}], {ci})"
    v = f"{_h(42, key)} % 10000"
    head, glob, country = WEB_MIX
    unique, cn_glob = CN_MIX
    return (
        f"multiIf("
        f"probe_cc = 'CN' AND {v} < {unique}, concat('https://u', toString({_h(41, key)} % 1000000000), '.example.net/'), "
        f"probe_cc = 'CN' AND {v} < {cn_glob}, {_site(f'{_h(4, key)} % {GLOBAL_LIST}')}, "
        f"probe_cc = 'CN', {_site(f'{offset} + {_h(4, key)} % {size}')}, "
        f"{v} < {head}, {_site(f'{_h(4, key)} % {GLOBAL_HEAD}')}, "
        f"{v} < {glob}, {_site(f'{GLOBAL_HEAD} + {_skewed(4, GLOBAL_LIST - GLOBAL_HEAD, key)}')}, "
        f"{v} < {country}, {_site(f'{offset} + {_skewed(4, size, key, power=3)}')}, "
        f"concat('https://x', lower(probe_cc), toString({_skewed(4, UNLISTED_PER_COUNTRY, key, power=3)}), '.example.net/'))"
    )


def _input(key="number"):
    # dnscheck: 122 inputs on 82 domains, stunreachability 22, echcheck 2
    dns = f"{_skewed(45, 122, key)}"
    return (
        f"multiIf(test_name = 'web_connectivity', {_web_input(key)}, "
        f"test_name = 'dnscheck', concat('https://dns', toString({dns} % 82), '.example.com/dns-query', if({dns} >= 82, concat('?v=', toString({dns})), '')), "
        f"test_name = 'stunreachability', concat('stun://stun', toString({_skewed(45, 22, key)}), '.example.com:3478'), "
        f"test_name = 'echcheck', concat('https://ech', toString({_h(45, key)} % 2), '.example.com/'), '')"
    )


def _outcome(column: int, test_expr="test_name") -> str:
    # per test rate, per 10000, of anomaly (2), confirmed (3) or msm_failure (4)
    rates = f"[{','.join(str(t[column]) for t in TEST_SHAPE)}]"
    return f"arrayElement({rates}, indexOf({_array(TEST_NAMES)}, {test_expr}))"


def _mst(n, key="number"):
    return f"toDateTime({TODAY} - {DAYS}) + intDiv({key} * {DAYS * 86400}, {n}) + {_h(3, key)} % 60"


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
    return f"(toDateTime({TODAY} - {DAYS}) + intDiv({REPORT} * {DAYS * 86400 - 120}, {reports}) + {_h(3, REPORT)} % 60)"


def _report_duration(n):
    # 60% 2-20 s, 25% up to 10 min, 10% up to 2 h, 4.9% up to 14 h, 0.1% 1-3 days
    h = f"{_h(20, REPORT)} % 1000"
    r = f"{_h(21, REPORT)}"
    d = f"multiIf({h} < 600, 2 + {r} % 18, {h} < 850, 20 + {r} % 580, {h} < 950, 600 + {r} % 6600, {h} < 999, 7200 + {r} % 43200, 86400 + {r} % 172800)"
    # reports still running at the end of the window are cut short
    return f"least({d}, dateDiff('second', {_report_start(n)}, toDateTime({TODAY})) - {2 * MEASUREMENTS_PER_REPORT})"


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
    # tests in production proportions
    return f"arrayElement({_array(TEST_NAMES)}, {_weighted_index(18, [m for _, m, _, _, _ in TEST_SHAPE], key)})"


def insert_citizenlab(click):
    click.execute(
        f"""
        INSERT INTO citizenlab (domain, url, cc, category_code)
        SELECT
            concat('site', toString(number), '.example.org') AS domain,
            concat('https://', domain, '/') AS url,
            -- the global list, then each country's, in COUNTRIES order
            if(number < {GLOBAL_LIST}, 'ZZ',
               lower(arrayElement({_array(COUNTRIES)}, arrayFirstIndex(o -> o > number, arrayPushBack({_array_int(COUNTRY_LIST_OFFSETS[1:])}, {COUNTRY_LIST_OFFSETS[-1] + COUNTRY_LIST_SIZES[-1]}))))) AS cc,
            arrayElement({_array(CATEGORY_CODES)}, 1 + {_h(30)} % {len(CATEGORY_CODES)}) AS category_code
        FROM numbers({COUNTRY_LIST_OFFSETS[-1] + COUNTRY_LIST_SIZES[-1]})
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
        SELECT asn, concat('Synthetic Network ', toString(asn)), cc, {TODAY} - 30, concat('AS', toString(asn)), 'synthetic'
        FROM (
            SELECT toUInt32({ASN_BASE} + ci * 1000 + arrayJoin(range(n))) AS asn, arrayElement({_array(COUNTRIES)}, ci) AS cc
            FROM (SELECT number + 1 AS ci, arrayElement({_array_int(COUNTRY_ASNS)}, ci) AS n FROM numbers({len(COUNTRIES)}))
            UNION ALL
            SELECT arrayJoin({_array_int(GLOBAL_ASNS)}) AS asn, 'US' AS cc
        )
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
            {_input()} AS input,
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
            -- confirmed measurements are a subset of anomalies
            if({_h(5)} % 10000 < {_outcome(2)}, 't', 'f') AS anomaly,
            if({_h(5)} % 10000 < {_outcome(3)}, 't', 'f'),
            if({_h(6)} % 10000 < {_outcome(4)}, 't', 'f'),
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
            {_web_input(m)} AS input,
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
            domain(input) AS hostname,
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
            if({idx} = 3, input, NULL),
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
            domain(input) AS domain,
            {_web_input()} AS input,
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
            concat('site', toString({_skewed(4, GLOBAL_LIST, 'number')}), '.example.org'),
            toDateTime({TODAY} - {DAYS}) + intDiv(number * {DAYS * 86400}, {n}),
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
