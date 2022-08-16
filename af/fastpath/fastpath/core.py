#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OONI Fastpath

See README.adoc

"""

# Compatible with Python3.6 and 3.7 - linted with Black
# debdeps: python3-setuptools

from argparse import ArgumentParser, Namespace
from base64 import b64decode
from configparser import ConfigParser
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
import binascii
import logging
import multiprocessing as mp
import os
import sys
import time
import yaml

import ujson  # debdeps: python3-ujson

try:
    from systemd.journal import JournalHandler  # debdeps: python3-systemd

    no_journal_handler = False
except ImportError:
    # this will be the case on macOS for example
    no_journal_handler = True

# Feeds measurements from S3
import fastpath.s3feeder as s3feeder

# Feeds measurements from a local HTTP API
from fastpath.localhttpfeeder import start_http_api

# Push measurements into Postgres
import fastpath.db as db

from fastpath.metrics import setup_metrics
import fastpath.portable_queue as queue

import fastpath.utils

LOCALITY_VALS = ("general", "global", "country", "isp", "local")

NUM_WORKERS = 3

log = logging.getLogger("fastpath")
metrics = setup_metrics(name="fastpath")

conf = Namespace()
fingerprints: Dict[str, Dict[str, list]]


def parse_date(d: str):
    return datetime.strptime(d, "%Y-%m-%d").date()


def setup_dirs(conf, root) -> None:
    """Setup directories creating them if needed"""
    conf.vardir = root / "var/lib/fastpath"
    conf.cachedir = conf.vardir / "cache"
    conf.s3cachedir = conf.cachedir / "s3"
    # conf.outdir = conf.vardir / "output"
    for p in (
        conf.vardir,
        conf.cachedir,
        conf.s3cachedir,
    ):
        p.mkdir(parents=True, exist_ok=True)


def setup() -> None:
    os.environ["TZ"] = "UTC"
    global conf
    ap = ArgumentParser(__doc__)
    ap.add_argument("--start-day", type=lambda d: parse_date(d))
    ap.add_argument("--end-day", type=lambda d: parse_date(d))
    ap.add_argument("--devel", action="store_true", help="Devel mode")
    h = "Process measurements from S3 and do not start API feeder"
    ap.add_argument("--noapi", action="store_true", help=h)
    ap.add_argument("--stdout", action="store_true", help="Log to stdout")
    ap.add_argument("--debug", action="store_true", help="Log at debug level")
    ap.add_argument("--db-uri", help="PG database DSN or URI")
    ap.add_argument("--clickhouse-url", help="Clickhouse url")
    h = "Update summaries and files instead of logging an error"
    ap.add_argument("--update", action="store_true", help=h)
    h = "Stop after feeding N measurements from S3"
    ap.add_argument("--stop-after", type=int, help=h, default=None)
    h = "Do not insert measurement in database"
    ap.add_argument("--no-write-to-db", action="store_true", help=h)
    h = "Keep files downloaded from S3 in the local cache"
    ap.add_argument("--keep-s3-cache", action="store_true", help=h)
    ap.add_argument("--ccs", help="Filter comma-separated CCs when feeding from S3")
    h = "Filter comma-separated test names when feeding from S3 (without underscores)"
    ap.add_argument("--testnames", help=h)

    conf = ap.parse_args()

    if conf.devel or conf.stdout or no_journal_handler:
        format = "%(relativeCreated)d %(process)d %(levelname)s %(name)s %(message)s"
        logging.basicConfig(stream=sys.stdout, format=format)

    else:
        log.addHandler(JournalHandler(SYSLOG_IDENTIFIER="fastpath"))
    log.setLevel(logging.DEBUG if conf.debug else logging.INFO)
    logging.getLogger("clickhouse_driver.connection").setLevel(logging.WARNING)

    if conf.ccs:
        conf.ccs = set(cc.strip() for cc in conf.ccs.split(","))

    if conf.testnames:
        conf.testnames = set(x.strip() for x in conf.testnames.split(","))

    # Run inside current directory in devel mode
    root = Path(os.getcwd()) if conf.devel else Path("/")
    conf.conffile = root / "etc/ooni/fastpath.conf"
    log.info("Using conf file %s", conf.conffile)
    cp = ConfigParser()
    with open(conf.conffile) as f:
        cp.read_file(f)
        conf.collector_hostnames = cp["DEFAULT"]["collectors"].split()
        log.info("collectors: %s", conf.collector_hostnames)
        conf.s3_access_key = cp["DEFAULT"]["s3_access_key"].strip()
        conf.s3_secret_key = cp["DEFAULT"]["s3_secret_key"].strip()
        if conf.db_uri is None:
            conf.db_uri = cp["DEFAULT"]["db_uri"].strip()
        if conf.clickhouse_url is None:
            conf.clickhouse_url = cp["DEFAULT"]["clickhouse_url"].strip()

    setup_dirs(conf, root)


def per_s(name, item_count, t0) -> None:
    """Generate a gauge metric of items per second"""
    delta = time.time() - t0
    if delta > 0:
        metrics.gauge(f"{name}_per_s", item_count / delta)


@metrics.timer("clean_caches")
def clean_caches() -> None:
    """Cleanup local caches."""
    # Access times are updated on file load.
    # FIXME: use cache locations correctly
    now = time.time()
    threshold = 3600 * 24 * 3
    for f in conf.s3cachedir.iterdir():
        if not f.is_file():
            continue
        age_s = now - f.stat().st_atime
        if age_s > threshold:
            log.debug("Deleting %s", f)
            metrics.gauge("deleted_cache_file_age", age_s)
            # TODO: delete


# Currently unused: we could warn on missing / unexpected cols
expected_colnames = {
    "accessible",
    "advanced",
    "agent",
    "annotations",
    "automated_testing",
    "blocking",
    "body_length_match",
    "body_proportion",
    "blocking_country",
    "blocking_general",
    "blocking_global",
    "blocking_isp",
    "blocking_local",
    "client_resolver",
    "control",
    "control_failure",
    "data_format_version",
    "dns_consistency",
    "dns_experiment_failure",
    "engine_name",
    "engine_version",
    "engine_version_full",
    "failure",
    "failure_asn_lookup",
    "failure_cc_lookup",
    "failure_ip_lookup",
    "failure_network_name_lookup",
    "flavor",
    "headers_match",
    "http_experiment_failure",
    "id",
    "input",
    "input_hashes",
    "measurement_start_time",
    "network_type",
    "options",
    "origin",
    "phase_result",
    "platform",
    "probe_asn",
    "probe_cc",
    "probe_city",
    "probe_ip",
    "queries",
    "receiver_data",
    "registration_server_failure",
    "registration_server_status",
    "report_id",
    "requests",
    "retries",
    "sender_data",
    "server_address",
    "server_port",
    "server_version",
    "simple",
    "socksproxy",
    "software_name",
    "software_version",
    "status_code_match",
    "summary_data",
    "tcp_connect",
    "telegram_http_blocking",
    "telegram_tcp_blocking",
    "telegram_web_failure",
    "telegram_web_status",
    "test_c2s",
    "test_helpers",
    "test_name",
    "test_runtime",
    "test_s2c",
    "test_start_time",
    "test_suite",
    "test_version",
    "test_keys",
    "title_match",
    "web_connectivity",
    "whatsapp_endpoints_blocked",
    "whatsapp_endpoints_dns_inconsistent",
    "whatsapp_endpoints_status",
    "whatsapp_web_failure",
    "whatsapp_web_status",
}


def prepare_for_json_normalize(report) -> None:
    try:
        d = report["test_keys"]["control"]["tcp_connect"]
        d = {n: i for n, i in enumerate(d.items())}
        report["test_keys"]["control"]["tcp_connect"] = tuple(d.items())
    except KeyError:
        pass

    try:
        h = report["test_keys"]["control"]["http_request"]["headers"]
        report["test_keys"]["control"]["http_request"]["headers"] = tuple(h.items())
    except KeyError:
        pass


def process_measurements_from_s3() -> None:
    """Pull measurements from S3 and process them"""
    if conf.no_write_to_db:
        log.info("Skipping DB connection setup")
    else:
        if conf.db_uri:
            db.setup(conf)
        if conf.clickhouse_url:
            db.setup_clickhouse(conf)

    msmt_cnt = 0
    for measurement_tup in s3feeder.stream_cans(conf, conf.start_day, conf.end_day):
        assert measurement_tup is not None
        assert len(measurement_tup) == 3
        msm_jstr, msm, msm_uid = measurement_tup
        assert msm_jstr is None or isinstance(msm_jstr, (str, bytes)), type(msm_jstr)
        assert msm is None or isinstance(msm, dict)
        process_measurement(measurement_tup)
        if conf.stop_after:
            msmt_cnt += 1
            if msmt_cnt >= conf.stop_after:
                return


@metrics.timer("match_fingerprints")
def match_fingerprints(measurement) -> list:
    """Match fingerprints against HTTP headers, bodies and DNS.
    Used only on web_connectivity
    """
    msm_cc = measurement["probe_cc"]

    zzfps = fingerprints["ZZ"]
    ccfps = fingerprints.get(msm_cc, {})

    test_keys = measurement.get("test_keys")
    if test_keys is None:
        return []

    matches = []
    queries = test_keys.get("queries", ()) or ()
    for q in queries:
        for answer in q.get("answers", ()) or ():
            for fp in zzfps["dns_full"] + ccfps.get("dns_full", []):
                addr = ""
                if "ipv4" in answer:
                    addr = answer["ipv4"]
                elif "hostname" in answer:
                    addr = answer["hostname"]
                elif "ipv6" in answer:
                    addr = answer["ipv6"]
                if fp["dns_full"] == addr:
                    matches.append(fp)

    requests = test_keys.get("requests", ()) or ()
    for req in requests:
        r = req.get("response")
        if r is None:
            continue

        # Match HTTP body if found
        body = r.get("body")

        if isinstance(body, dict):
            if "data" in body and body.get("format", "") == "base64":
                log.debug("Decoding base64 body")
                body = b64decode(body["data"])
                # returns bytes. bm.encode() below is faster that decoding it

            else:
                logbug(2, "incorrect body of type dict", measurement)
                body = None

        if body is not None:
            for fp in zzfps["body_match"] + ccfps.get("body_match", []):
                # fp: {"body_match": "...", "locality": "..."}
                tb = time.time()
                bm = fp["body_match"]
                if isinstance(body, bytes):
                    idx = body.find(bm.encode())
                else:
                    idx = body.find(bm)

                if idx != -1:
                    matches.append(fp)
                    log.debug("matched body fp %s %r at pos %d", msm_cc, bm, idx)
                    # Used for statistics
                    metrics.gauge("fingerprint_body_match_location", idx)

                per_s("fingerprints_bytes", len(body), tb)

        del body

        # Match HTTP headers if found
        headers = r.get("headers", {})
        if not headers:
            continue
        headers = {h.lower(): v for h, v in headers.items()}
        for fp in zzfps["header_full"] + ccfps.get("header_full", []):
            name = fp["header_name"]
            if name in headers and headers[name] == fp["header_full"]:
                matches.append(fp)
                log.debug("matched header full fp %s %r", msm_cc, fp["header_full"])

        for fp in zzfps["header_prefix"] + ccfps.get("header_prefix", []):
            name = fp["header_name"]
            prefix = fp["header_prefix"]
            v = headers.get(name)
            if isinstance(v, dict) and v.get("format") == "base64":
                log.debug("Decoding base64 header")
                data = b64decode(v.get("data", ""))
                v = data.decode("latin1")
            if isinstance(v, str) and v.startswith(prefix):
                matches.append(fp)
                log.debug("matched header prefix %s %r", msm_cc, prefix)

    return matches


def g_or(d: dict, key: str, default):
    """Dict getter: return 'default' if the key is missing or value is None"""
    # Note: 'd.get(key) or default' returns 'default' on any falsy value
    v = d.get(key)
    return default if v is None else v


def g(d, *keys, default=None):
    """Item getter that supports nested keys. Returns a default when keys are
    missing or set to None"""
    for k in keys[:-1]:
        d = g_or(d, k, default={})
    return g_or(d, keys[-1], default=default)


def gn(d, *a):
    return g(d, *a, default=None)


def all_keys_true(d: dict, keys) -> bool:
    """Check for values set to True in a dict"""
    if isinstance(keys, str):
        keys = (keys,)
    for k in keys:
        if d.get(k) is not True:
            return False

    return True


def all_keys_false(d, keys):
    """Check for values set to True in a dict"""
    if isinstance(keys, str):
        keys = (keys,)
    for k in keys:
        if d.get(k) is not False:
            return False

    return True


def all_keys_none(d: dict, keys) -> bool:
    """Check for values set to None in a dict"""
    if isinstance(keys, str):
        keys = (keys,)
    for k in keys:
        if d.get(k, True) is not None:
            return False

    return True


def logbug(id: int, desc: str, msm: dict) -> None:
    """Log unexpected measurement contents, possibly due to a bug in the probe
    The id helps locating the call to logbug()
    """
    # Current highest logbug id: 7
    # TODO: use assertions for unknown bugs
    rid = msm.get("report_id", "")
    url = "https://explorer.ooni.org/measurement/{}".format(rid) if rid else "no rid"
    sname = g_or(msm, "software_name", "unknown")
    sversion = g_or(msm, "software_version", "unknown")
    if id > 0:
        # unknown, possibly new bug
        log.warning("probe_bug %d: %s %s %s %s", id, sname, sversion, desc, url)
    else:
        log.info("known_probe_bug: %s %s %s %s", sname, sversion, desc, url)


def _detect_unknown_failure(tk: dict) -> bool:
    """Any field ending with _failure can contain `unknown_failure ...`
    due to failed msmt
    """
    for k in tk:
        if k.endswith("_failure"):
            v = tk[k] or ""
            if v.startswith("unknown_failure"):
                log.debug(f"unknown_failure in field {k}")
                return True

    return False


def init_scores() -> dict:
    return {f"blocking_{lv}": 0.0 for lv in LOCALITY_VALS}


@metrics.timer("score_measurement_facebook_messenger")
def score_measurement_facebook_messenger(msm: dict) -> dict:
    tk = g_or(msm, "test_keys", {})
    del msm

    # TODO: recompute all these keys in the pipeline
    # If the value of these keys is false (inconsistent) there is something
    # fishy
    consistency_keys = [
        "facebook_b_api_dns_consistent",
        "facebook_b_api_reachable",
        "facebook_b_graph_dns_consistent",
        "facebook_b_graph_reachable",
        "facebook_edge_dns_consistent",
        "facebook_edge_reachable",
        "facebook_external_cdn_dns_consistent",
        "facebook_external_cdn_reachable",
        "facebook_scontent_cdn_dns_consistent",
        "facebook_scontent_cdn_reachable",
        "facebook_star_dns_consistent",
        "facebook_star_reachable",
        "facebook_stun_dns_consistent",
    ]
    # These are keys that if they are true it means there is something fishy
    anomaly_keys = ["facebook_tcp_blocking", "facebook_dns_blocking"]

    scores = init_scores()

    # Workaround for 'facebook_dns_blocking': True
    # See tests/test_functional.py:test_facebook_messenger*
    trues = (
        "facebook_b_api_dns_consistent",
        "facebook_b_api_reachable",
        "facebook_b_graph_dns_consistent",
        "facebook_b_graph_reachable",
        "facebook_dns_blocking",
        "facebook_edge_dns_consistent",
        "facebook_edge_reachable",
        "facebook_star_dns_consistent",
        "facebook_star_reachable",
        "facebook_stun_dns_consistent",
    )
    if all_keys_true(tk, trues) and all_keys_false(tk, "facebook_tcp_blocking"):
        score = 0.0

    else:
        score = 0.0
        for key in consistency_keys:
            v = tk.get(key)
            if v is False:
                score += 0.5
                scores[key] = v

        for key in anomaly_keys:
            v = tk.get(key)
            if v is True:
                score += 0.5
                scores[key] = v

    scores["blocking_general"] = score
    return scores


def _extract_tcp_connect(tk: dict) -> tuple:
    # https://github.com/ooni/spec/blob/master/data-formats/df-005-tcpconnect.md
    # NOTE: this is *NOT* ts-008-tcp-connect.md
    # First the probe tests N TCP connections
    tcp_connect = g_or(tk, "tcp_connect", [])
    accessible_endpoints = 0
    unreachable_endpoints = 0
    for entry in tcp_connect:
        success = gn(entry, "status", "success")
        if success is True:
            accessible_endpoints += 1
        elif success is False:
            unreachable_endpoints += 1
        else:
            pass  # unknown

    return accessible_endpoints, unreachable_endpoints


@metrics.timer("score_measurement_telegram")
def score_measurement_telegram(msm: dict) -> dict:
    """Calculate measurement scoring for Telegram.
    Returns a scores dict
    """
    # Ignore tcp_blocking, http_blocking and web_failure from the probe
    tk = g_or(msm, "test_keys", {})
    del msm
    web_status = tk.get("telegram_web_status")
    if web_status == "ok":
        web_blocking = False
    elif web_status == "blocked":
        web_blocking = True
    else:
        # unknown
        web_blocking = None

    accessible_endpoints, unreachable_endpoints = _extract_tcp_connect(tk)

    # Then the probe tests N HTTP connections
    http_success_cnt = 0
    http_failure_cnt = 0
    web_failure = None
    requests = g_or(tk, "requests", ())
    for request in requests:
        try:
            url = request["request"]["url"]
        except KeyError:
            # client bug
            scores = init_scores()
            scores["accuracy"] = 0.0
            return scores

        if url in ("https://web.telegram.org/", "http://web.telegram.org/"):
            if request["failure"] is not None:
                web_failure = request["failure"]

            # TODO extract_html_title(request["response"]["body"] and check if
            # it matches "Telegram Web"
            # see: https://github.com/measurement-kit/measurement-kit/blob/f63ed8b7f186dbb27cf32489216826752d070620/src/libmeasurement_kit/ooni/telegram.cpp#L101

            # We skip the telegram web requests for counting the
            # http_success_cnt
            continue

        if request["failure"] is None:
            http_success_cnt += 1
        else:
            # TODO also consider looking at request["response"]["body"] to
            # match the expected telegram backend response
            http_failure_cnt += 1

    # Scoring

    if (accessible_endpoints + unreachable_endpoints) > 0:
        s = unreachable_endpoints / (accessible_endpoints + unreachable_endpoints)
    else:
        s = 0.5

    if (http_failure_cnt + http_success_cnt) > 0:
        s += http_failure_cnt / (http_failure_cnt + http_success_cnt)
    else:
        s += 0.5

    if web_blocking:
        s += 1

    scores = init_scores()
    scores["blocking_general"] = s
    scores["web_failure"] = web_failure
    scores["accessible_endpoints"] = accessible_endpoints
    scores["unreachable_endpoints"] = unreachable_endpoints
    scores["http_success_cnt"] = http_success_cnt
    scores["http_failure_cnt"] = http_failure_cnt
    if web_failure is not None:
        scores["msg"] = "failure: {}".format(web_failure)
    return scores


@metrics.timer("score_measurement_hhfm")
def score_measurement_hhfm(msm: dict) -> dict:
    """Calculate http_header_field_manipulation"""
    tk = g_or(msm, "test_keys", {})
    rid = msm["report_id"]
    del msm
    scores = init_scores()

    # See test_functional.py:test_score_measurement_hhfm_stats
    #
    # exp_req_failure = tk["requests"][0].get("failure")
    # if exp_req_failure is not None:
    #    # failure state set by probe
    #    scores["blocking_general"] = 0.5
    #    return scores

    # response->body contains a JSON document like:
    # {"headers_dict": {"acCePT-languagE": ["en-US,en;q=0.8"], ...},
    #  "request_line": "geT / HTTP/1.1",
    #  "request_headers": [ ["Connection", "close"], ... ]
    # }
    try:
        resp = tk["requests"][0].get("response", {})
    except (KeyError, IndexError, TypeError):
        # See 20191028T115649Z_AS28573_eIrzDM4njwMjxBi0ODrerI5N03zM7qQoCvl4xpapTccdW0kCRg
        scores["accuracy"] = 0.0
        return scores

    # See 20191027T002012Z_AS45595_p2qNg0FmL4d2kIuLQXEn36MbraErPPA5i64eE1e6nLfGluHpLk
    if resp is None:
        # Broken test?
        scores["accuracy"] = 0.0
        return scores

    resp_body = resp.get("body")
    if resp_body is None:
        scores["total_tampering"] = True
        scores["blocking_general"] = 1.0
        scores["msg"] = "Empty body"
        return scores

    # Compare sent and received HTTP headers
    try:
        ctrl_headers = ujson.loads(resp_body)["headers_dict"]
    except:
        scores["blocking_general"] = 1.0
        scores["msg"] = "Malformed ctrl_headers"
        return scores

    # "unpack" value and turn into a set of tuples to run a comparison
    ctrl = set((k, v[0]) for k, v in ctrl_headers.items())

    exp_req_headers = tk["requests"][0].get("request", {}).get("headers", {})
    expected = set(exp_req_headers.items())

    # The "Connection" header is not always handled correctly
    ctrl.discard(("Connection", "close"))
    expected.discard(("Connection", "close"))

    if expected == ctrl:
        return scores

    # Headers have been manipulated!
    scores["blocking_general"] = 1.1
    diff = expected ^ ctrl
    scores["msg"] = "{} unexpected header change".format(len(diff))
    # TODO: distinguish proxies lowercasing/fixing headers
    # or adding "benign" Via, Connection, X-BlueCoat-Via, X-Forwarded-For
    # headers?
    return scores


@metrics.timer("score_http_invalid_request_line")
def score_http_invalid_request_line(msm: dict) -> dict:
    """Calculate measurement scoring for http_invalid_request_line"""
    # https://github.com/ooni/spec/blob/master/nettests/ts-007-http-invalid-request-line.md
    tk = g_or(msm, "test_keys", {})
    rid = msm["report_id"]
    scores = init_scores()
    sent = tk.get("sent", [])
    received = tk.get("received", [])

    if not len(sent) and not len(received):
        scores["accuracy"] = 0.0
        return scores

    # Compare sent and received HTTP headers
    anomaly = False
    for s, r in zip(sent, received):
        if s != r:
            anomaly = True

    # We ignore the tampering flag due to: https://github.com/ooni/probe/issues/1278
    # tampering = tk.get("tampering", False)
    # if tampering != anomaly:
    #     scores["accuracy"] = 0.0
    #     logbug(6, "Incorrect tampering flag", msm)
    #     return scores

    # Headers have been manipulated!
    if anomaly:
        scores["blocking_general"] = 1.0

    return scores


def get_http_header(resp, header_name, case_sensitive=False):
    """This function returns the HTTP header(s) matching the given
    header_name from the headers. The returned value is a list
    given that we may have multiple keys per header. If the new
    headers_list field is present in the response, we'll use
    that, otherwise we'll fallback to the headers map. We perform
    case insensitive header names search by default. You can yet
    optionally select case sensitive comparison."""
    if case_sensitive == False:
        header_name = header_name.lower()

    header_list = []

    # backward compatibility with older measurements that don't have
    # header_list
    if "header_list" not in resp:
        headers = resp.get("headers", {})
        header_list = [[h, v] for h, v in headers.items()]
    else:
        headers_list = resp.get("headers_list")  # TODO: unused

    values = []
    for h, v in header_list:
        if case_sensitive == False:
            h = h.lower()
        if h == header_name:
            values.append(v)

    return values


@metrics.timer("score_measurement_whatsapp")
def score_measurement_whatsapp(msm: dict) -> dict:
    """Calculate measurement scoring for Whatsapp.
    Returns a scores dict
    """
    # https://github.com/ooni/spec/blob/master/nettests/ts-018-whatsapp.md
    # TODO: check data_format_version?

    score = 0
    tk = g_or(msm, "test_keys", {})

    # msg = ""
    # for req in msm.get("requests", []):
    #    if "X-FB-TRIP-ID" not in req.get("response", {}).get("headers", {}):
    #        score += 0.2
    #        msg += "Missing HTTP header"

    # Disabled due to bug in the probe https://github.com/ooni/probe-engine/issues/341
    # if tk.get("registration_server_status", "ok") != "ok":
    #     score += 0.2
    # if tk.get("whatsapp_web_failure") != None:
    #     score += 0.2
    # if tk.get("whatsapp_endpoints_status", "ok") != "ok":
    #     score += 0.2
    # if tk.get("whatsapp_web_status", "ok") != "ok":
    #     # TODO: recalculate using HTML body title
    #     score += 0.2
    # if tk.get("whatsapp_endpoints_dns_inconsistent", []) != []:
    #     score += 0.2
    # if tk.get("whatsapp_endpoints_blocked", []) != []:
    #     score += 0.2

    # registration_server_failure = tk.get("registration_server_failure")
    # if registration_server_failure is not None:
    #    if registration_server_failure.startswith("unknown_failure"):
    #        # Client error
    #        # TODO: implement confidence = 0
    #        score = 0
    #    else:
    #        score += 0.2

    if (
        msm.get("software_name", "") == "ooniprobe"
        and msm.get("software_version", "") in ("2.1.0", "2.2.0", "2.3.0")
        and tk.get("whatsapp_web_status", "") == "blocked"
    ):
        # The probe is reporting a false positive: due to the empty client headers
        # it hits https://www.whatsapp.com/unsupportedbrowser
        if score == 0.2:
            score = 0

    scores = init_scores()
    # TODO: refactor
    if _detect_unknown_failure(tk):
        scores["accuracy"] = 0.0

    wf = tk.get("whatsapp_web_failure", "")
    if wf and "unknown_failure 'ascii' co" in wf:
        assert msm["report_id"]
        scores["accuracy"] = 0.0
        return scores

    requests = tk.get("requests", ()) or ()
    if not requests:
        assert msm["report_id"]
        scores["accuracy"] = 0.0
        return scores

    # TODO: carve out in a general function
    webapp_accessible = None
    registration_accessible = None
    for b in requests:
        url = b.get("request", {}).get("url", "")
        if url == "https://web.whatsapp.com/":
            webapp_accessible = b.get("failure", True) in (None, "", False)
            # TODO: handle cases where the certificate is invalid or the page
            # has unexpected contents
            # Also note bug https://github.com/ooni/probe-legacy/issues/60

        elif url == "http://web.whatsapp.com/":
            webapp_accessible = True
            if b.get("failure", True) not in (None, "", False):
                webapp_accessible = False
            else:
                resp = b.get("response", {})
                status_code = resp.get("code", 0)
                location_header_list = get_http_header(resp, "Location")
                if status_code != 302:
                    webapp_accessible = False
                elif "https://web.whatsapp.com/" not in location_header_list:
                    webapp_accessible = False

        elif url == "https://v.whatsapp.net/v2/register":
            # In case of connection failure "response" might be empty
            registration_accessible = b.get("failure") is None

    if webapp_accessible is None or registration_accessible is None:
        # bug e.g. 20190101T191128Z_AS34594_ZCyS8OE3SSvRwLeuiAeiklVZ8H91hEfY0Ook7ljgfotgpQklhv
        scores["accuracy"] = 0.0
        return scores

    if webapp_accessible is not True or registration_accessible is not True:
        scores["blocking_general"] = 1.0
        return scores

    accessible_endpoints, unreachable_endpoints = _extract_tcp_connect(tk)
    if not accessible_endpoints and not unreachable_endpoints:
        scores["accuracy"] = 0.0

    elif accessible_endpoints > 0:
        pass  # we call it OK

    else:
        scores["blocking_general"] = 1.0

    scores["analysis"] = dict(
        registration_server_accessible=registration_accessible,
        whatsapp_web_accessible=webapp_accessible,
        whatsapp_endpoints_accessible=accessible_endpoints > 0,
    )

    return scores


@metrics.timer("score_vanilla_tor")
def score_vanilla_tor(msm: dict) -> dict:
    """Calculate measurement scoring for Tor (test_name: vanilla_tor)
    Returns a scores dict
    """
    tk = g_or(msm, "test_keys", {})
    scores = init_scores()

    nks = ("error", "success", "tor_log", "tor_progress_summary", "tor_progress_tag")
    if msm["software_name"] == "ooniprobe" and all_keys_none(tk, nks):
        if tk["tor_progress"] == 0:
            # client bug?
            scores["msg"] = "Client bug"
            return scores

    tor_log = tk.get("tor_log")
    if tor_log is None:
        # unknown bug
        return scores

    if (
        "Bootstrapped 100%: Done" in tor_log
        or "Bootstrapped 100% (done): Done" in tor_log
    ):
        # Success
        return scores

    progress = float(tk.get("tor_progress", 0))
    progress = min(100, max(0, progress))
    # If the Tor bootstrap reaches, for example, 80% maybe it's being heavily
    # throttled or it's just a very slow network: blocking score is set to 0.68
    scores["blocking_general"] = 1.0 - progress * 0.004
    return scores


@metrics.timer("score_web_connectivity")
def score_web_connectivity(msm, matches) -> dict:
    """Calculate measurement scoring for web connectivity
    Returns a scores dict
    """
    scores = init_scores()  # type: Dict[str, Any]
    if len(matches):
        scores["confirmed"] = True
    tk = g_or(msm, "test_keys", {})
    if tk is None:
        logbug(9, "test_keys is None", msm)
        scores["accuracy"] = 0.0
        return scores

    for m in matches:
        l = "blocking_" + m["locality"]
        scores[l] += 1.0

    # "title_match" is often missing from the raw msmt
    # e.g. 20190912T145602Z_AS9908_oXVmdAo2BZ2Z6uXDdatwL9cN5oiCllrzpGWKY49PlM4vEB03X7
    tm = tk.get("title_match")
    if tm not in (True, False, None):
        logbug(1, "incorrect title_match", msm)
        scores["accuracy"] = 0.0
        return scores

    # Do not score title_match=False - see #360
    # if tm is False:
    #     scores["blocking_general"] += 0.5
    #     # TODO: scan HTML body for title instead

    # body_proportion can be missing
    # Commented out to use the same logic as traditional pipeline
    # TODO: enable it after doing statistics on body proportion
    # http://www3.cs.stonybrook.edu/~phillipa/papers/JLFG14.pdf
    # if "body_proportion" in tk:
    #    bp = tk["body_proportion"]
    #    delta = abs((tk["body_proportion"] or 1.0) - 1.0)
    #    scores["blocking_general"] += delta
    # TODO: refactor to apply to all test types

    # anomaly
    blocking_types = ("tcp_ip", "dns", "http-diff", "http-failure")
    probe_blocking = tk.get("blocking")
    if probe_blocking in blocking_types:
        scores["blocking_general"] = 1.0
        scores["analysis"] = {"blocking_type": tk["blocking"]}

    elif probe_blocking == False:
        pass

    elif probe_blocking is None:
        # somewhat-broken msmt https://github.com/ooni/backend/issues/610
        # if confirmed we treat the msmt as good
        if not matches:
            scores["accuracy"] = 0.0

    else:
        logbug(7, "unexpected value for blocking", msm)
        scores["analysis"] = {"msg": "Unsupported blocking type"}
        scores["accuracy"] = 0.0

    # TODO: refactor
    if _detect_unknown_failure(tk):
        scores["accuracy"] = 0.0

    # TODO: add heuristic to split blocking_general into local/ISP/country/global
    scores["blocking_general"] += (
        scores["blocking_country"]
        + scores["blocking_global"]
        + scores["blocking_isp"]
        + scores["blocking_local"]
    )

    if "accessible" in tk and tk["accessible"] is None and not matches:
        # https://github.com/ooni/backend/issues/610
        scores["accuracy"] = 0.0
        return scores

    return scores


def score_web_connectivity_full(msm: dict) -> dict:
    try:
        matches = match_fingerprints(msm)
    except binascii.Error:
        scores = score_web_connectivity(msm, [])
        scores["accuracy"] = 0.0
        return scores

    return score_web_connectivity(msm, matches)


@metrics.timer("score_ndt")
def score_ndt(msm: dict) -> dict:
    """Calculate measurement scoring for NDT
    Returns a scores dict
    """
    # TODO: this is just a stub - add NDT scoring where possible
    return {}


@metrics.timer("score_tcp_connect")
def score_tcp_connect(msm: dict) -> dict:
    """Calculate measurement scoring for tcp connect
    Returns a scores dict
    """
    # https://github.com/ooni/spec/blob/master/nettests/ts-008-tcp-connect.md
    # NOTE: this is *NOT* spec/blob/master/data-formats/df-005-tcpconnect.md
    # TODO: review scores
    scores = init_scores()
    tk = g_or(msm, "test_keys", {})
    assert msm["input"]
    conn_result = tk.get("connection")

    if conn_result == "success":
        return scores

    if conn_result == "generic_timeout_error":
        scores["blocking_general"] = 0.8
        return scores

    if conn_result == "connection_refused_error":
        scores["blocking_general"] = 0.8
        return scores

    if conn_result == "connect_error":
        scores["blocking_general"] = 0.8
        return scores

    if conn_result == "tcp_timed_out_error":
        scores["blocking_general"] = 0.8
        return scores

    # TODO: add missing error type
    scores["blocking_general"] = 1.0
    return scores


def score_dash(msm: dict) -> dict:
    """Calculate measurement scoring for DASH
    (Dynamic Adaptive Streaming over HTTP)
    Returns a scores dict
    """
    # TODO: review scores
    # TODO: any blocking scoring based on performance?
    scores = init_scores()  # type: Dict[str, Any]
    tk = g_or(msm, "test_keys", {})
    failure = tk.get("failure")
    if tk == {}:
        scores["accuracy"] = 0.0
        return scores

    if failure is None:
        pass
    elif failure == "connection_aborted":
        scores["blocking_general"] = 0.1
        scores["accuracy"] = 0.0
    elif failure == "json_parse_error":
        scores["blocking_general"] = 0.1
        scores["accuracy"] = 0.0
    elif failure == "eof_error":
        scores["blocking_general"] = 0.1
        scores["accuracy"] = 0.0
    elif failure == "json_processing_error":
        scores["blocking_general"] = 0.1
        scores["accuracy"] = 0.0
    elif failure == "http_request_failed":
        scores["blocking_general"] = 0.1
        scores["accuracy"] = 0.0
    elif failure == "connect_error":
        scores["blocking_general"] = 0.1
        scores["accuracy"] = 0.0
    elif failure == "generic_timeout_error":
        scores["blocking_general"] = 0.1
        scores["accuracy"] = 0.0
    elif failure == "broken_pipe":
        scores["blocking_general"] = 0.1
        scores["accuracy"] = 0.0
    elif failure == "connection_refused":
        scores["blocking_general"] = 0.1
        scores["accuracy"] = 0.0
    elif "ssl_error" in failure:
        scores["blocking_general"] = 0.1
        scores["accuracy"] = 0.0
    else:
        scores["msg"] = "Probe error"
        scores["accuracy"] = 0.0

    return scores


def score_meek_fronted_requests_test(msm: dict) -> dict:
    """Calculate measurement scoring for Meek
    Returns a scores dict
    """
    scores = init_scores()
    tk = g_or(msm, "test_keys", {})
    requests = tk.get("requests", ()) or ()

    if len(requests) == 0:
        # requests is empty: usually "success" is missing.
        scores["blocking_general"] = 1.0
        scores["accuracy"] = 0
        return scores

    success = tk.get("success")

    for r in requests:
        resp = r.get("response", {})
        if resp is None:
            # Error during probing?
            scores["blocking_general"] = 1.0
            if success is not None:
                log.info("Client bug: success != None")
            return scores

        if resp.get("code", 0) != 200:
            # A failed response is enough
            scores["blocking_general"] = 1.0
            if success is not False:
                log.info("Client bug: success != False")
            return scores

        headers = resp.get("headers", {})
        # headers can be a list or a dict
        if isinstance(headers, list):
            headers = {i[0]: i[1][0] for i in headers if i}
        server = headers.get("Server", "")
        if not server.startswith("ECAcc "):
            scores["blocking_general"] += 0.5

    return scores


def score_psiphon(msm: dict) -> dict:
    """Calculate measurement scoring for Psiphon
    Returns a scores dict
    """
    scores = init_scores()
    tk = g_or(msm, "test_keys", {})

    # https://github.com/ooni/spec/blob/master/nettests/ts-015-psiphon.md
    failure = tk.get("failure")
    bootstrap_time = tk.get("bootstrap_time", 0)

    if failure is None:
        if bootstrap_time == 0:
            # should not happen
            logbug(4, "invalid psiphon msmt", msm)
            scores["accuracy"] = 0.0

        else:
            # success
            scores["accuracy"] = 1.0

    else:
        # if bootstrap_time == 0: # there was an error bootstrapping Psiphon
        # else: # there was an error when using Psiphon
        scores["accuracy"] = 1.0
        scores["blocking_general"] = 1.0

    if "resolver_ip" not in msm:
        logbug(0, "no resolver_ip", msm)
        scores["accuracy"] = 0.0

    truntime = msm.get("test_runtime")
    scores["extra"] = dict(test_runtime=truntime, bootstrap_time=bootstrap_time)
    return scores


def score_tor(msm: dict) -> dict:
    """Calculate measurement scoring for Tor (test_name: tor)
    https://github.com/ooni/spec/blob/master/nettests/ts-023-tor.md
    Returns a scores dict
    """
    scores = init_scores()
    tk = g_or(msm, "test_keys", {})

    # targets -> <ipaddr:port>|<sha obfs4 fprint> -> failure
    #                                             -> network_events
    targets = tk.get("targets", {})
    if not targets:
        logbug(5, "missing Tor targets", msm)
        scores["accuracy"] = 0.0
        return scores

    blocked_cnt = 0
    not_run_cnt = 0
    success_cnt = 0
    if isinstance(targets, list):
        # targets were a list in early experiments, see tests/data/tor_list.json
        scores["accuracy"] = 0.0
        return scores

    for d in targets.values():
        if "failure" not in d or "network_events" not in d:
            logbug(6, "missing Tor failure or network_events field", msm)
            scores["accuracy"] = 0.0
            return scores

        f = d["failure"]
        # False: did not run: N/A
        # None: success
        # string: failed
        if f is False:
            not_run_cnt += 1
        elif f is None:
            success_cnt += 1
        elif f == "":
            # logbug(8
            assert 0, d
        else:
            blocked_cnt += 1

    if blocked_cnt + success_cnt:
        scores["blocking_general"] = blocked_cnt / (blocked_cnt + success_cnt)

    else:
        scores["accuracy"] = 0.0

    scores["extra"] = dict(test_runtime=msm.get("test_runtime"))
    return scores


def score_http_requests(msm: dict) -> dict:
    """Calculates measurement scoring for legacy test http_requests
    Returns a scores dict
    """
    scores = init_scores()
    tk = g_or(msm, "test_keys", {})
    body_length_match = tk.get("body_length_match")
    headers_match = tk.get("headers_match")
    rid = msm.get("report_id")
    inp = msm.get("input")
    failed = msm.get("control_failure") or msm.get("experiment_failure")
    if failed or body_length_match is None or headers_match is None:
        scores["accuracy"] = 0.0
        log.debug(f"Incorrect measurement t1 {rid} {inp}")
        return scores

    reachable = bool(body_length_match) and bool(headers_match)
    if not reachable:
        scores["blocking_general"] = 1.0

    zzfps = fingerprints["ZZ"]
    msm_cc = msm.get("probe_cc")
    ccfps = fingerprints.get(msm_cc, {})

    # Scan for fingerprint matches in the HTTP body and the HTTP headers
    # One request is from the probe and one is over Tor. If the latter
    # is blocked the msmt is failed.
    tk = g_or(msm, "test_keys", {})
    requests = tk.get("requests", []) or []
    for r in requests:
        is_tor = gn(r, "request", "tor", "is_tor")
        body = gn(r, "response", "body")
        if is_tor is None or body is None:
            scores["accuracy"] = 0.0
            log.debug(f"Incorrect measurement t2 {rid} {inp}")
            return scores

        if isinstance(body, dict):
            # TODO: is this needed?
            if "data" in body and g_or(body, "format", "") == "base64":
                log.debug("Decoding base64 body")
                body = b64decode(body["data"])

            else:
                logbug(3, "incorrect body of type dict", msm)
                body = None

        for fp in zzfps["body_match"] + g_or(ccfps, "body_match", []):
            bm = fp["body_match"]
            if isinstance(body, bytes):
                idx = body.find(bm.encode())
            else:
                idx = body.find(bm)

            if idx != -1:
                if is_tor:
                    scores["accuracy"] = 0.0
                    log.debug(f"Failed measurement t1 {rid} {inp}")
                    return scores
                scores["confirmed"] = True
                log.debug("matched body fp %s %r at pos %d", msm_cc, bm, idx)

        # Match HTTP headers if found
        headers = g_or(r, "headers", {})
        headers = {h.lower(): v for h, v in headers.items()}
        for fp in zzfps["header_full"] + g_or(ccfps, "header_full", []):
            name = fp["header_name"]
            if name in headers and headers[name] == fp["header_full"]:
                if is_tor:
                    scores["accuracy"] = 0.0
                    log.debug(f"Failed measurement t2 {rid} {inp}")
                    return scores
                scores["confirmed"] = True
                log.debug("matched header full fp %s %r", msm_cc, fp["header_full"])

        for fp in zzfps["header_prefix"] + g_or(ccfps, "header_prefix", []):
            name = fp["header_name"]
            prefix = fp["header_prefix"]
            if name in headers and headers[name].startswith(prefix):
                if is_tor:
                    scores["accuracy"] = 0.0
                    log.debug(f"Failed measurement {rid} {inp}")
                    return scores
                scores["confirmed"] = True
                log.debug("matched header prefix %s %r", msm_cc, prefix)

    return scores


def score_dns_consistency(msm: dict) -> dict:
    """Calculates measurement scoring for legacy test dns_consistency
    Returns a scores dict
    """
    # TODO: implement scoring
    scores = init_scores()
    return scores


def score_signal(msm: dict) -> dict:
    """Calculates measurement scoring for Signal test
    Returns a scores dict
    """
    # https://github.com/ooni/spec/blob/master/nettests/ts-029-signal.md
    scores = init_scores()
    tk = g_or(msm, "test_keys", {})
    if tk.get("failed_operation", True) or tk.get("failure", True):
        scores["accuracy"] = 0.0

    st = tk.get("signal_backend_status")
    if st == "ok":
        pass
    elif st == "blocked":
        scores["blocking_general"] = 1.0
        sbf = tk.get("signal_backend_failure")
        scores["analysis"] = {"signal_backend_failure": sbf}
    else:
        scores["accuracy"] = 0.0

    return scores


def score_stunreachability(msm: dict) -> dict:
    """Calculate measurement scoring for STUN reachability
    Returns a scores dict
    """
    # https://github.com/ooni/backend/issues/551
    scores = init_scores()
    tk = g_or(msm, "test_keys", {})
    scores["extra"] = dict(endpoint=tk.get("endpoint"))
    failure = tk.get("failure")
    if failure:
        scores["blocking_general"] = 1.0
        scores["extra"]["failure"] = failure

    return scores


def score_torsf(msm: dict) -> dict:
    """Calculate measurement scoring for Tor Snowflake
    Returns a scores dict
    """
    # https://github.com/ooni/ooni.org/issues/772
    scores = init_scores()
    tk = g_or(msm, "test_keys", {})
    failure = tk.get("failure")
    if failure:
        scores["blocking_general"] = 1.0
        return scores

    scores["extra"] = dict(
        bootstrap_time=tk.get("bootstrap_time"), test_runtime=msm.get("test_runtime")
    )
    return scores


def score_riseupvpn(msm: dict) -> dict:
    """Calculate measurement scoring for RiseUp VPN
    Returns a scores dict
    """
    # https://github.com/ooni/backend/issues/541
    scores = init_scores()
    tk = g_or(msm, "test_keys", {})
    tstatus = tk.get("transport_status") or {}
    obfs4 = tstatus.get("obfs4")
    openvpn = tstatus.get("openvpn")
    anomaly = (
        tk.get("api_status") == "blocked"
        or tk.get("ca_cert_status") is False
        or obfs4 == "blocked"
        or openvpn == "blocked"
    )
    if anomaly:
        scores["blocking_general"] = 1.0

    scores["extra"] = dict(test_runtime=msm.get("test_runtime"))
    return scores


@metrics.timer("score_measurement")
def score_measurement(msm: dict) -> dict:
    """Calculates measurement scoring. Returns a scores dict"""
    # Blocking locality: global > country > ISP > local
    # unclassified locality is stored in "blocking_general"

    tn = msm["test_name"]
    try:
        if tn == "telegram":
            return score_measurement_telegram(msm)
        if tn == "facebook_messenger":
            return score_measurement_facebook_messenger(msm)
        if tn == "http_header_field_manipulation":
            return score_measurement_hhfm(msm)
        if tn == "http_invalid_request_line":
            return score_http_invalid_request_line(msm)
        if tn == "whatsapp":
            return score_measurement_whatsapp(msm)
        if tn == "vanilla_tor":
            return score_vanilla_tor(msm)
        if tn == "web_connectivity":
            return score_web_connectivity_full(msm)
        if tn == "ndt":
            return score_ndt(msm)
        if tn == "tcp_connect":
            return score_tcp_connect(msm)
        if tn == "dash":
            return score_dash(msm)
        if tn == "meek_fronted_requests_test":
            return score_meek_fronted_requests_test(msm)
        if tn == "psiphon":
            return score_psiphon(msm)
        if tn == "tor":
            return score_tor(msm)
        if tn == "http_requests":
            return score_http_requests(msm)
        if tn == "dns_consistency":
            return score_dns_consistency(msm)
        if tn == "signal":
            return score_signal(msm)
        if tn == "stunreachability":
            return score_stunreachability(msm)
        if tn == "torsf":
            return score_torsf(msm)
        if tn == "riseupvpn":
            return score_riseupvpn(msm)

        log.debug("Unsupported test name %s", tn)
        scores = init_scores()
        scores["accuracy"] = 0.0
        return scores

    except AssertionError as e:
        # unknown / new client bugs are often catched by assertions
        if str(e).startswith("pbug "):  # suspected probe bug
            logbug(0, str(e)[4:], msm)
            scores = init_scores()
            scores["accuracy"] = 0.0
            return scores

        raise


def unwrap_msmt(post):
    fmt = post["format"].lower()
    if fmt == "json":
        return post["content"]
    if fmt == "yaml":
        return yaml.safe_load(post["content"])  # TODO: test


def msm_processor(queue):
    """Measurement processor worker"""
    if conf.no_write_to_db:
        log.info("Skipping DB connection setup")
    else:
        if conf.db_uri:
            db.setup(conf)
        if conf.clickhouse_url:
            db.setup_clickhouse(conf)

    while True:
        msm_tup = queue.get()
        if msm_tup is None:
            log.info("Worker with PID %d exiting", os.getpid())
            return

        process_measurement(msm_tup)


def flag_measurements_with_wrong_date(msm: dict, msmt_uid: str, scores: dict) -> None:
    if not msmt_uid.startswith("20") or len(msmt_uid) < 20:
        return
    try:
        recv_time = datetime.strptime(msmt_uid[:22], "%Y%m%d%H%M%S.%f_")
        start_time = msm.get("measurement_start_time") or ""
        start_time = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return

    delta = (recv_time - start_time).total_seconds()
    if delta < -3600:
        log.debug(f"Flagging measurement {msmt_uid} from the future")
        scores["accuracy"] = 0.0
        scores["msg"] = "Measurement start time from the future"
    elif delta > 31536000:
        log.debug(f"Flagging measurement {msmt_uid} as too old")
        scores["accuracy"] = 0.0
        scores["msg"] = "Measurement start time too old"


@metrics.timer("full_run")
def process_measurement(msm_tup) -> None:
    """Process a measurement:
    - Parse JSON if needed
    - Unwrap "content" key if needed
    - Score it
    - Upsert to fastpath table unless no_write_to_db is set
    """
    try:
        msm_jstr, measurement, msmt_uid = msm_tup
        assert msmt_uid
        if measurement is None:
            measurement = ujson.loads(msm_jstr)
        if sorted(measurement.keys()) == ["content", "format"]:
            measurement = unwrap_msmt(measurement)
        rid = measurement.get("report_id")
        inp = measurement.get("input")
        log.debug(f"Processing {msmt_uid} {rid} {inp}")
        if rid is None:
            log.debug(f"Ignoring measurement without report_id")
            metrics.incr("discarded_measurement")
            return

        if measurement.get("probe_cc", "").upper() == "ZZ":
            log.debug(f"Ignoring measurement with probe_cc=ZZ")
            metrics.incr("discarded_measurement")
            return

        if measurement.get("probe_asn", "").upper() == "AS0":
            log.debug(f"Ignoring measurement with ASN 0")
            metrics.incr("discarded_measurement")
            return

        scores = score_measurement(measurement)
        flag_measurements_with_wrong_date(measurement, msmt_uid, scores)

        # Generate anomaly, confirmed and failure to keep consistency
        # with the legacy pipeline, allowing simple queries in the API
        # and in manual analysis; also keep compatibility with Explorer
        anomaly = scores.get("blocking_general", 0.0) > 0.5
        failure = scores.get("accuracy", 1.0) < 0.5
        confirmed = scores.get("confirmed", False)

        if anomaly or failure or confirmed:
            log.debug(
                f"Storing {msmt_uid} {rid} {inp} A{int(anomaly)} F{int(failure)} C{int(confirmed)}"
            )
        sw_name = measurement.get("software_name", "unknown")
        sw_version = measurement.get("software_version", "unknown")
        platform = "unset"
        if "annotations" in measurement and isinstance(
            measurement["annotations"], dict
        ):
            platform = measurement["annotations"].get("platform", "unset")

        if conf.no_write_to_db:
            return

        if conf.db_uri:
            db.upsert_summary(
                measurement,
                scores,
                anomaly,
                confirmed,
                failure,
                msmt_uid,
                sw_name,
                sw_version,
                platform,
                conf.update,
            )
        if conf.clickhouse_url:
            db.clickhouse_upsert_summary(
                measurement,
                scores,
                anomaly,
                confirmed,
                failure,
                msmt_uid,
                sw_name,
                sw_version,
                platform,
            )
    except Exception as e:
        log.exception(e)
        metrics.incr("unhandled_exception")


def shut_down(queue):
    log.info("Shutting down workers")
    [queue.put(None) for n in range(NUM_WORKERS)]
    # FIXME
    # queue.close()
    # queue.join_thread()


def core():
    # There are 3 main data sources, in order of age:
    # - cans on S3
    # - older report files on collectors (max 1 day of age)
    # - report files on collectors fetched in "real-time"
    # Load json/yaml files and apply filters like canning

    if conf.noapi:
        # Process measurements from S3
        process_measurements_from_s3()
        return

    # Spawn worker processes
    # 'queue' is a singleton from the portable_queue module
    workers = [
        mp.Process(target=msm_processor, args=(queue,)) for n in range(NUM_WORKERS)
    ]
    try:
        [t.start() for t in workers]
        # Start HTTP API
        log.info("Starting HTTP API")
        start_http_api(queue)

    except Exception as e:
        log.exception(e)

    finally:
        log.info("Shutting down workers")
        time.sleep(1)
        shut_down(queue)
        time.sleep(1)
        log.info("Join")
        [w.join() for w in workers]
        log.info("Join done")
        clean_caches()


def setup_fingerprints():
    """Setup fingerprints lookup dictionary
    "ZZ" applies a fingerprint globally
    """
    # pre-process fingerprints to speed up lookup
    global fingerprints
    # cc -> fprint_type -> list of dicts
    fingerprints = {
        "ZZ": {"body_match": [], "header_prefix": [], "header_full": [], "dns_full": []}
    }
    for cc, fprints in fastpath.utils.fingerprints.items():
        d = fingerprints.setdefault(cc, {})
        for fp in fprints:
            assert fp["locality"] in LOCALITY_VALS, fp["locality"]
            if "body_match" in fp:
                d.setdefault("body_match", []).append(fp)
            elif "header_prefix" in fp:
                fp["header_name"] = fp["header_name"].lower()
                d.setdefault("header_prefix", []).append(fp)
            elif "header_full" in fp:
                fp["header_name"] = fp["header_name"].lower()
                d.setdefault("header_full", []).append(fp)
            elif "dns_full" in fp:
                d.setdefault("dns_full", []).append(fp)


def main():
    setup()
    setup_fingerprints()
    log.info("Starting")
    core()


if __name__ == "__main__":
    main()
