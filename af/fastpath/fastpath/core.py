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
import hashlib
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
from fastpath.mytypes import MsmtTup
import fastpath.portable_queue as queue

import fastpath.utils

LOCALITY_VALS = ("general", "global", "country", "isp", "local")

NUM_WORKERS = 3

log = logging.getLogger("fastpath")
metrics = setup_metrics(name="fastpath")

conf = Namespace()
fingerprints = None


def parse_date(d):
    return datetime.strptime(d, "%Y-%m-%d").date()


def setup_dirs(conf, root):
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


def setup():
    os.environ["TZ"] = "UTC"
    global conf
    ap = ArgumentParser(__doc__)
    ap.add_argument("--start-day", type=lambda d: parse_date(d))
    ap.add_argument("--end-day", type=lambda d: parse_date(d))
    ap.add_argument("--devel", action="store_true", help="Devel mode")
    ap.add_argument("--noapi", action="store_true", help="Do not start API feeder")
    ap.add_argument("--stdout", action="store_true", help="Log to stdout")
    ap.add_argument("--db-uri", help="Database DSN or URI.")
    ap.add_argument(
        "--update",
        action="store_true",
        help="Update summaries and files instead of logging an error",
    )
    ap.add_argument(
        "--stop-after", type=int, help="Stop after feeding N measurements", default=None
    )
    ap.add_argument(
        "--no-write-to-db",
        action="store_true",
        help="Do not insert measurement in database",
    )
    ap.add_argument(
        "--keep-s3-cache",
        action="store_true",
        help="Keep files downloaded from S3 in the local cache",
    )
    conf = ap.parse_args()

    if conf.devel or conf.stdout or no_journal_handler:
        format = "%(relativeCreated)d %(process)d %(levelname)s %(name)s %(message)s"
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format=format)

    else:
        log.addHandler(JournalHandler(SYSLOG_IDENTIFIER="fastpath"))
        log.setLevel(logging.DEBUG)

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

    setup_dirs(conf, root)


def per_s(name, item_count, t0):
    """Generate a gauge metric of items per second"""
    delta = time.time() - t0
    if delta > 0:
        metrics.gauge(f"{name}_per_s", item_count / delta)


@metrics.timer("clean_caches")
def clean_caches():
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


def prepare_for_json_normalize(report):
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


def process_measurements_from_s3():
    """Pull measurements from S3 and process them"""
    if conf.no_write_to_db:
        log.info("Skipping DB connection setup")
    else:
        db.setup(conf)

    for measurement_tup in s3feeder.stream_cans(conf, conf.start_day, conf.end_day):
        assert measurement_tup is not None
        assert len(measurement_tup) == 3
        msm_jstr, msm, msm_uid = measurement_tup
        assert msm_jstr is None or isinstance(msm_jstr, (str, bytes)), type(msm_jstr)
        assert msm is None or isinstance(msm, dict)
        process_measurement(measurement_tup)


@metrics.timer("match_fingerprints")
def match_fingerprints(measurement):
    """Match fingerprints against HTTP headers and bodies.
    Used only on web_connectivity
    """
    msm_cc = measurement["probe_cc"]

    zzfps = fingerprints["ZZ"]
    ccfps = fingerprints.get(msm_cc, {})

    test_keys = measurement.get("test_keys", None)
    if test_keys is None:
        return []

    matches = []
    requests = test_keys.get("requests", ()) or ()
    for req in requests:
        r = req.get("response", None)
        if r is None:
            continue

        # Match HTTP body if found
        body = r["body"]

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
            if name in headers and headers[name].startswith(prefix):
                matches.append(fp)
                log.debug("matched header prefix %s %r", msm_cc, prefix)

    return matches


def all_keys_true(d, keys):
    """Check for values set to True in a dict"""
    if isinstance(keys, str):
        keys = (keys,)
    for k in keys:
        if d.get(k, None) is not True:
            return False

    return True


def all_keys_false(d, keys):
    """Check for values set to True in a dict"""
    if isinstance(keys, str):
        keys = (keys,)
    for k in keys:
        if d.get(k, None) is not False:
            return False

    return True


def all_keys_none(d, keys):
    """Check for values set to None in a dict"""
    if isinstance(keys, str):
        keys = (keys,)
    for k in keys:
        if d.get(k, True) is not None:
            return False

    return True


def logbug(id: int, desc: str, msm: dict):
    """Log unexpected measurement contents, possibly due to a bug in the probe
    The id helps locating the call to logbug()
    """
    # Current highest logbug id: 7
    # TODO: use assertions for unknown bugs
    rid = msm.get("report_id", "")
    url = "https://explorer.ooni.org/measurement/{}".format(rid) if rid else "no rid"
    sname = msm.get("software_name", "unknown")
    sversion = msm.get("software_version", "unknown")
    if id > 0:
        # unknown, possibly new bug
        log.warning("probe_bug %d: %s %s %s %s", id, sname, sversion, desc, url)
    else:
        log.info("known_probe_bug: %s %s %s %s", sname, sversion, desc, url)


def _detect_unknown_failure(tk):
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
def score_measurement_facebook_messenger(msm):
    tk = msm["test_keys"]
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
        score = 0

    else:
        score = 0
        for key in consistency_keys:
            v = tk.get(key, None)
            if v is False:
                score += 0.5
                scores[key] = v

        for key in anomaly_keys:
            v = tk.get(key, None)
            if v is True:
                score += 0.5
                scores[key] = v

    scores["blocking_general"] = score
    return scores


def _extract_tcp_connect(tk):
    # https://github.com/ooni/spec/blob/master/data-formats/df-005-tcpconnect.md
    # NOTE: this is *NOT* ts-008-tcp-connect.md
    # First the probe tests N TCP connections
    tcp_connect = tk.get("tcp_connect", [])
    accessible_endpoints = 0
    unreachable_endpoints = 0
    for entry in tcp_connect:
        s = entry.get("status", {})
        success = s.get("success", None)
        if success is True:
            accessible_endpoints += 1
        elif success is False:
            unreachable_endpoints += 1
        else:
            pass  # unknown

    return accessible_endpoints, unreachable_endpoints


@metrics.timer("score_measurement_telegram")
def score_measurement_telegram(msm):
    """Calculate measurement scoring for Telegram.
    Returns a scores dict
    """
    # Ignore tcp_blocking, http_blocking and web_failure from the probe
    tk = msm["test_keys"]
    del msm
    web_status = tk.get("telegram_web_status", None)
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
    requests = tk.get("requests", ()) or ()
    for request in requests:
        if "request" not in request:
            # client bug
            continue
        if request["request"]["url"] in (
            "https://web.telegram.org/",
            "http://web.telegram.org/",
        ):
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
        scores["msg"] = "Telegam failure: {}".format(web_failure)
    return scores


@metrics.timer("score_measurement_hhfm")
def score_measurement_hhfm(msm):
    """Calculate http_header_field_manipulation"""
    tk = msm["test_keys"]
    rid = msm["report_id"]
    del msm
    scores = init_scores()

    # See test_functional.py:test_score_measurement_hhfm_stats
    #
    # exp_req_failure = tk["requests"][0].get("failure", None)
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
    except (KeyError, IndexError):
        # See 20191028T115649Z_AS28573_eIrzDM4njwMjxBi0ODrerI5N03zM7qQoCvl4xpapTccdW0kCRg"
        scores["blocking_general"] = 0.0
        return scores

    # See 20191027T002012Z_AS45595_p2qNg0FmL4d2kIuLQXEn36MbraErPPA5i64eE1e6nLfGluHpLk
    if resp is None:
        # Broken test?
        scores["blocking_general"] = 0.0
        return scores

    resp_body = resp.get("body", None)
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
def score_http_invalid_request_line(msm):
    """Calculate measurement scoring for http_invalid_request_line"""
    # https://github.com/ooni/spec/blob/master/nettests/ts-007-http-invalid-request-line.md
    tk = msm["test_keys"]
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


@metrics.timer("score_measurement_whatsapp")
def score_measurement_whatsapp(msm):
    """Calculate measurement scoring for Whatsapp.
    Returns a scores dict
    """
    # https://github.com/ooni/spec/blob/master/nettests/ts-018-whatsapp.md
    # TODO: check data_format_version?

    score = 0
    tk = msm["test_keys"]

    # msg = ""
    # for req in msm.get("requests", []):
    #    if "X-FB-TRIP-ID" not in req.get("response", {}).get("headers", {}):
    #        score += 0.2
    #        msg += "Missing HTTP header"

    # Disabled due to bug in the probe https://github.com/ooni/probe-engine/issues/341
    # if tk.get("registration_server_status", "ok") != "ok":
    #     score += 0.2
    # if tk.get("whatsapp_web_failure", None) != None:
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

    # registration_server_failure = tk.get("registration_server_failure", None)
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

        # TODO: handle elif url == "http://web.whatsapp.com/":

        elif url == "https://v.whatsapp.net/v2/register":
            # In case of connection failure "response" might be empty
            registration_accessible = b.get("failure", None) is None

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
def score_vanilla_tor(msm):
    """Calculate measurement scoring for Tor (test_name: vanilla_tor)
    Returns a scores dict
    """
    tk = msm["test_keys"]
    scores = init_scores()

    nks = ("error", "success", "tor_log", "tor_progress_summary", "tor_progress_tag")
    if msm["software_name"] == "ooniprobe" and all_keys_none(tk, nks):
        if tk["tor_progress"] == 0:
            # client bug?
            scores["msg"] = "Client bug"
            return scores

    tor_log = tk.get("tor_log", None)
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
    tk = msm.get("test_keys", None)
    if tk is None:
        logbug(9, "test_keys is None", msm)
        scores["accuracy"] = 0.0
        return scores

    for m in matches:
        l = "blocking_" + m["locality"]
        scores[l] += 1.0

    # "title_match" is often missing from the raw msmt
    # e.g. 20190912T145602Z_AS9908_oXVmdAo2BZ2Z6uXDdatwL9cN5oiCllrzpGWKY49PlM4vEB03X7
    tm = tk.get("title_match", None)
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
    blocking_types = ("tcp_ip", "dns", "http-diff", "http-failure")
    if "blocking" not in tk:
        logbug(7, "missing blocking field", msm)
        scores["accuracy"] = 0.0

    elif tk["blocking"] in blocking_types:
        scores["blocking_general"] = 1.0
        scores["analysis"] = {"blocking_type": tk["blocking"]}

    elif tk["blocking"] in (None, False):
        pass

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
    return scores


@metrics.timer("score_ndt")
def score_ndt(msm) -> dict:
    """Calculate measurement scoring for NDT
    Returns a scores dict
    """
    # TODO: this is just a stub - add NDT scoring where possible
    return {}


@metrics.timer("score_tcp_connect")
def score_tcp_connect(msm) -> dict:
    """Calculate measurement scoring for tcp connect
    Returns a scores dict
    """
    # https://github.com/ooni/spec/blob/master/nettests/ts-008-tcp-connect.md
    # NOTE: this is *NOT* spec/blob/master/data-formats/df-005-tcpconnect.md
    # TODO: review scores
    scores = init_scores()
    tk = msm["test_keys"]
    assert msm["input"]
    conn_result = tk.get("connection", None)

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


def score_dash(msm) -> dict:
    """Calculate measurement scoring for DASH
    (Dynamic Adaptive Streaming over HTTP)
    Returns a scores dict
    """
    # TODO: review scores
    # TODO: any blocking scoring based on performance?
    scores = init_scores()  # type: Dict[str, Any]
    failure = msm["test_keys"].get("failure", None)
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


def score_meek_fronted_requests_test(msm) -> dict:
    """Calculate measurement scoring for Meek
    Returns a scores dict
    """
    scores = init_scores()
    tk = msm["test_keys"]
    requests = tk.get("requests", ()) or ()

    if len(requests) == 0:
        # requests is empty: usually "success" is missing.
        scores["blocking_general"] = 1.0
        scores["accuracy"] = 0
        return scores

    success = tk.get("success", None)

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

        server = resp.get("headers", {}).get("Server", "")
        if not server.startswith("ECAcc "):
            scores["blocking_general"] += 0.5

    return scores


def score_psiphon(msm) -> dict:
    """Calculate measurement scoring for Psiphon
    Returns a scores dict
    """
    scores = init_scores()
    tk = msm.get("test_keys", {})

    # https://github.com/ooni/spec/blob/master/nettests/ts-015-psiphon.md
    failure = tk.get("failure", None)
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

    return scores


def score_tor(msm) -> dict:
    """Calculate measurement scoring for Tor (test_name: tor)
    https://github.com/ooni/spec/blob/master/nettests/ts-023-tor.md
    Returns a scores dict
    """
    scores = init_scores()
    tk = msm.get("test_keys", {})

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

    return scores


def score_http_requests(msm) -> dict:
    """Calculates measurement scoring for legacy test http_requests
    Returns a scores dict
    """
    scores = init_scores()
    tk = msm.get("test_keys", {})
    body_length_match = tk.get("body_length_match", None)
    headers_match = tk.get("headers_match", None)
    rid = msm.get("report_id", None)
    inp = msm.get("input", None)
    failed = msm.get("control_failure", None) or msm.get("experiment_failure", None)
    if failed or body_length_match is None or headers_match is None:
        scores["accuracy"] = 0.0
        log.debug(f"Incorrect measurement t1 {rid} {inp}")
        return scores

    reachable = bool(body_length_match) and bool(headers_match)
    if not reachable:
        scores["blocking_general"] = 1.0

    zzfps = fingerprints["ZZ"]
    msm_cc = msm.get("probe_cc", None)
    ccfps = fingerprints.get(msm_cc, {})

    # Scan for fingerprint matches in the HTTP body and the HTTP headers
    # One request is from the probe and one is over Tor. If the latter
    # is blocked the msmt is failed.
    tk = msm.get("test_keys", {})
    for r in tk.get("requests", []):
        is_tor = r.get("request", {}).get("tor", {}).get("is_tor", None)
        body = r.get("response", {}).get("body", None)
        if is_tor is None or body is None:
            scores["accuracy"] = 0.0
            log.debug(f"Incorrect measurement t2 {rid} {inp}")
            return scores

        if isinstance(body, dict):
            # TODO: is this needed?
            if "data" in body and body.get("format", "") == "base64":
                log.debug("Decoding base64 body")
                body = b64decode(body["data"])

            else:
                logbug(3, "incorrect body of type dict", msm)
                body = None

        for fp in zzfps["body_match"] + ccfps.get("body_match", []):
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
        headers = r.get("headers", {})
        headers = {h.lower(): v for h, v in headers.items()}
        for fp in zzfps["header_full"] + ccfps.get("header_full", []):
            name = fp["header_name"]
            if name in headers and headers[name] == fp["header_full"]:
                if is_tor:
                    scores["accuracy"] = 0.0
                    log.debug(f"Failed measurement t2 {rid} {inp}")
                    return scores
                scores["confirmed"] = True
                log.debug("matched header full fp %s %r", msm_cc, fp["header_full"])

        for fp in zzfps["header_prefix"] + ccfps.get("header_prefix", []):
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


def score_dns_consistency(msm) -> dict:
    """Calculates measurement scoring for legacy test dns_consistency
    Returns a scores dict
    """
    # TODO: implement scoring
    scores = init_scores()
    return scores


def score_signal(msm) -> dict:
    """Calculates measurement scoring for Signal test
    Returns a scores dict
    """
    # https://github.com/ooni/spec/blob/master/nettests/ts-029-signal.md
    scores = init_scores()
    tk = msm.get("test_keys", {})
    if tk.get("failed_operation", True) or tk.get("failure", True):
        scores["accuracy"] = 0.0

    st = tk.get("signal_backend_status")
    if st == "ok":
        pass
    elif st == "blocked":
        scores["blocking_general"] = 1.0
    else:
        scores["accuracy"] = 0.0

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
            matches = match_fingerprints(msm)
            return score_web_connectivity(msm, matches)
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


@metrics.timer("trivial_id")
def trivial_id(msm: dict) -> str:
    """Generate a trivial id of the measurement to allow upsert if needed
    This is used for legacy (before measurement_uid) measurements
    - 32-bytes hexdigest
    - Deterministic / stateless with no DB interaction
    - Malicious/bugged msmts with collisions on report_id/input/test_name lead
    to different hash values avoiding the collision
    - Malicious/duplicated msmts that are semantically identical to the "real"
    one lead to harmless collisions
    """
    # NOTE: we want the id to stay the same when a msmt is fetched from SSH
    # and from a can on ooni-data-private/canned
    # Implementing a rolling hash without ujson.dumps is 2x faster
    # A rolling hash on only the first 2 levels of the dict is 10x faster
    #
    # Same output with Python's json
    VER = "00"
    msm_jstr = ujson.dumps(msm, sort_keys=True, ensure_ascii=False).encode()
    tid = VER + hashlib.shake_128(msm_jstr).hexdigest(15)
    return tid


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
        db.setup(conf)

    while True:
        msm_tup = queue.get()
        if msm_tup is None:
            log.info("Worker with PID %d exiting", os.getpid())
            return

        process_measurement(msm_tup)


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
        if measurement is None:
            measurement = ujson.loads(msm_jstr)
        if sorted(measurement.keys()) == ["content", "format"]:
            measurement = unwrap_msmt(measurement)
        rid = measurement.get("report_id", None)
        inp = measurement.get("input", None)
        log.debug(f"Processing {msmt_uid} {rid} {inp}")
        if measurement.get("probe_cc", "").upper() == "ZZ":
            log.debug(f"Ignoring measurement with probe_cc=ZZ")
            metrics.incr("discarded_measurement")
            return

        if measurement.get("probe_asn", "").upper() == "AS0":
            log.debug(f"Ignoring measurement with ASN 0")
            metrics.incr("discarded_measurement")
            return

        scores = score_measurement(measurement)
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

        if msmt_uid is None:
            msmt_uid = trivial_id(measurement)  # legacy measurement

        if conf.no_write_to_db:
            return

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
    fingerprints = {"ZZ": {"body_match": [], "header_prefix": [], "header_full": []}}
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


def main():
    setup()
    setup_fingerprints()
    log.info("Starting")
    core()


if __name__ == "__main__":
    main()
