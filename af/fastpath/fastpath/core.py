#!/usr/bin/env python3
# -*- coding: utf-8 -*-


"""
OONI Fastpath

See README.adoc

"""

# Compatible with Python3.6 and 3.7 - linted with Black
# debdeps: python3-setuptools

from argparse import ArgumentParser, Namespace
from configparser import ConfigParser
from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
import hashlib
import logging
import multiprocessing as mp
import os
import sys
import time

import ujson  # debdeps: python3-ujson
import lz4.frame as lz4frame  # debdeps: python3-lz4

try:
    from systemd.journal import JournalHandler  # debdeps: python3-systemd
    no_journal_handler = False
except ImportError:
    # this will be the case on macOS for example
    no_journal_handler = True

# Feeds measurements from Collectors over SSH
import fastpath.sshfeeder as sshfeeder

# Feeds measurements from S3
import fastpath.s3feeder as s3feeder

# Push measurements into Postgres
import fastpath.db as db

from fastpath.metrics import setup_metrics
import fastpath.portable_queue as queue

import fastpath.utils

LOCALITY_VALS = ("general", "global", "country", "isp", "local")

NUM_WORKERS = 15

log = logging.getLogger("fastpath")
metrics = setup_metrics(name="fastpath")

conf = Namespace()
fingerprints = None


def parse_date(d):
    return datetime.strptime(d, "%Y-%m-%d").date()


def setup():
    os.environ["TZ"] = "UTC"
    global conf
    ap = ArgumentParser(__doc__)
    ap.add_argument("--start-day", type=lambda d: parse_date(d))
    ap.add_argument("--end-day", type=lambda d: parse_date(d))
    ap.add_argument("--devel", action="store_true", help="Devel mode")
    ap.add_argument("--stdout", action="store_true", help="Log to stdout")
    ap.add_argument("--db-uri", help="Database DSN or URI. The string is logged!")
    ap.add_argument(
        "--update",
        action="store_true",
        help="Update summaries and files instead of logging an error",
    )
    ap.add_argument("--interact", action="store_true", help="Interactive mode")
    ap.add_argument(
        "--stop-after", type=int, help="Stop after feeding N measurements", default=None
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
    conf.conffile = root / "etc/fastpath.conf"
    log.info("Using conf file %r", conf.conffile)
    cp = ConfigParser()
    with open(conf.conffile) as f:
        cp.read_file(f)
        conf.collector_hostnames = cp["DEFAULT"]["collectors"].split()
        log.info("collectors: %s", conf.collector_hostnames)

    conf.vardir = root / "var/lib/fastpath"
    conf.cachedir = conf.vardir / "cache"
    conf.s3cachedir = conf.cachedir / "s3"
    conf.dfdir = conf.vardir / "dataframes"
    conf.outdir = conf.vardir / "output"
    conf.msmtdir = conf.outdir / "measurements"
    for p in (
        conf.vardir,
        conf.cachedir,
        conf.s3cachedir,
        conf.dfdir,
        conf.outdir,
        conf.msmtdir,
    ):
        p.mkdir(parents=True, exist_ok=True)


def per_s(name, item_count, t0):
    """Generate a gauge metric of items per second
    """
    delta = time.time() - t0
    if delta > 0:
        metrics.gauge(f"{name}_per_s", item_count / delta)


@metrics.timer("clean_caches")
def clean_caches():
    """Cleanup local caches.
    """
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


@metrics.timer("load_s3_reports")
def load_s3_reports(day) -> dict:
    # TODO: move this into s3feeder
    t0 = time.time()
    path = conf.s3cachedir / str(day)
    log.info("Scanning %s", path.absolute())
    files = []
    with os.scandir(path) as d:
        for e in d:
            if not e.is_file():
                continue
            if e.name == "index.json.gz":
                continue
            files.append(e)

    fcnt = 0
    for e in sorted(files, key=lambda f: f.name):
        log.debug("Ingesting %s", e.name)
        fn = os.path.join(path, e.name)
        fcnt += 1
        for measurement_tup in s3feeder.load_multiple(fn):
            yield measurement_tup

        remaining = (time.time() - t0) * (len(files) - fcnt) / fcnt
        metrics.gauge("load_s3_reports_eta", remaining)
        metrics.gauge("load_s3_reports_remaining_files", len(files) - fcnt)
        remaining = timedelta(seconds=remaining)
        log.info("load_s3_reports remaining time: %s", remaining)


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


def fetch_measurements(start_day, end_day) -> dict:
    """Fetch measurements from S3 and the collectors
    """
    # no --start-day or --end-day   -> Run over SSH
    # --start-day                   -> Run on old cans, then over SSH
    # --start-day and --end-day     -> Run on old cans
    # --start-day and --end-day  with the same date     -> NOP
    today = date.today()
    if start_day and start_day < today:
        # TODO: fetch day N+1 while processing day N
        log.info("Fetching older cans from S3")
        day = start_day
        while day < (end_day or today):
            log.info("Processing %s", day)
            s3feeder.fetch_cans_for_a_day_with_cache(conf, day)
            for measurement_tup in load_s3_reports(day):
                yield measurement_tup

            day += timedelta(days=1)

        if end_day:
            return

    ## Fetch measurements from collectors: backlog and then realtime ##
    log.info("Starting fetching over SSH")
    for measurement_tup in sshfeeder.feed_measurements_from_collectors(conf):
        yield measurement_tup


@metrics.timer("match_fingerprints")
def match_fingerprints(measurement):
    """Match fingerprints against HTTP headers and bodies.
    Used only on web_connectivity
    """
    msm_cc = measurement["probe_cc"]

    zzfps = fingerprints["ZZ"]
    ccfps = fingerprints.get(msm_cc, {})

    matches = []
    for req in measurement["test_keys"].get("requests", ()):
        r = req.get("response", None)
        if r is None:
            continue

        # Match HTTP body if found
        body = r["body"]
        if body is not None:
            for fp in zzfps["body_match"] + ccfps.get("body_match", []):
                # fp: {"body_match": "...", "locality": "..."}
                tb = time.time()
                bm = fp["body_match"]
                if bm in body:
                    matches.append(fp)
                    log.debug("matched body fp %s %r", msm_cc, bm)

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


def truekeys(d, keys):
    """Check for values set to True in a dict"""
    if isinstance(keys, str):
        keys = (keys,)
    for k in keys:
        if d.get(k, None) != True:
            return False

    return True


def falsekeys(d, keys):
    """Check for values set to True in a dict"""
    if isinstance(keys, str):
        keys = (keys,)
    for k in keys:
        if d.get(k, None) != False:
            return False

    return True


def nonekeys(d, keys):
    """Check for values set to None in a dict"""
    if isinstance(keys, str):
        keys = (keys,)
    for k in keys:
        if d.get(k, True) != None:
            return False

    return True


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

    scores = {f"blocking_{l}": 0.0 for l in LOCALITY_VALS}

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
    if truekeys(tk, trues) and falsekeys(tk, "facebook_tcp_blocking"):
        score = 0

    else:
        score = 0
        for key in consistency_keys:
            v = tk.get(key, None)
            if v == False:
                score += 0.5
                scores[key] = v

        for key in anomaly_keys:
            v = tk.get(key, None)
            if v == True:
                score += 0.5
                scores[key] = v

    scores["blocking_general"] = score
    return scores


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

    # Then the probe tests N HTTP connections
    http_success_cnt = 0
    http_failure_cnt = 0
    web_failure = None
    for request in tk.get("requests", []):
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

    scores = {f"blocking_{l}": 0.0 for l in LOCALITY_VALS}
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
    """Calculated http_header_field_manipulation
    """
    tk = msm["test_keys"]
    rid = msm["report_id"]
    del msm
    scores = {f"blocking_{l}": 0.0 for l in LOCALITY_VALS}

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


@metrics.timer("score_measurement_whatsapp")
def score_measurement_whatsapp(msm):
    """Calculate measurement scoring for Whatsapp.
    Returns a scores dict
    """
    # TODO: check data_format_version?

    score = 0
    tk = msm["test_keys"]
    msg = ""
    for req in msm.get("requests", []):
        if "X-FB-TRIP-ID" not in req.get("response", {}).get("headers", {}):
            score += 0.2
            msg += "Missing HTTP header"

    # del msm
    if tk.get("registration_server_status", "ok") != "ok":
        score += 0.2
    if tk.get("whatsapp_web_failure", None) != None:
        score += 0.2
    if tk.get("whatsapp_endpoints_status", "ok") != "ok":
        score += 0.2
    if tk.get("whatsapp_web_status", "ok") != "ok":
        # TODO: recalculate using HTML body title
        score += 0.2
    if tk.get("whatsapp_endpoints_dns_inconsistent", []) != []:
        score += 0.2
    if tk.get("whatsapp_endpoints_blocked", []) != []:
        score += 0.2

    registration_server_failure = tk.get("registration_server_failure", None)
    if registration_server_failure is not None:
        if registration_server_failure.startswith("unknown_failure"):
            # Client error
            # TODO: implement confidence = 0
            score = 0
        else:
            score += 0.2

    if (
        msm.get("software_name", "") == "ooniprobe"
        and msm.get("software_version", "") in ("2.1.0", "2.2.0", "2.3.0")
        and tk.get("whatsapp_web_status", "") == "blocked"
    ):
        # The probe is reporting a false positive: due to the empty client headers
        # it hits https://www.whatsapp.com/unsupportedbrowser
        if score == 0.2:
            score = 0

    scores = {f"blocking_{l}": 0.0 for l in LOCALITY_VALS}
    scores["blocking_general"] = score
    return scores


@metrics.timer("score_vanilla_tor")
def score_vanilla_tor(msm):
    """Calculate measurement scoring for Tor
    Returns a scores dict
    """
    tk = msm["test_keys"]
    scores = {f"blocking_{l}": 0.0 for l in LOCALITY_VALS}

    nks = ("error", "success", "tor_log", "tor_progress_summary", "tor_progress_tag")
    if msm["software_name"] == "ooniprobe" and nonekeys(tk, nks):
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
    scores = {f"blocking_{l}": 0.0 for l in LOCALITY_VALS}

    for m in matches:
        l = "blocking_" + m["locality"]
        scores[l] += 1.0

    # Feature extraction

    if msm.get("title_match", True) is False:
        scores["blocking_general"] += 0.5

    if "body_proportion" in msm["test_keys"]:
        # body_proportion can be missing or can be None
        delta = abs((msm["test_keys"]["body_proportion"] or 1.0) - 1.0)
        scores["blocking_general"] += delta

    # TODO: add heuristic to split blocking_general into local/ISP/country/global
    scores["blocking_general"] += (
        scores["blocking_country"]
        + scores["blocking_global"]
        + scores["blocking_isp"]
        + scores["blocking_local"]
    )
    return scores


@metrics.timer("score_measurement")
def score_measurement(msm, matches) -> dict:
    """Calculate measurement scoring. Returns a scores dict
    """
    # Blocking locality: global > country > ISP > local
    # unclassified locality is stored in "blocking_general"

    tn = msm["test_name"]
    if tn == "telegram":
        return score_measurement_telegram(msm)
    if tn == "facebook_messenger":
        return score_measurement_facebook_messenger(msm)
    if tn == "http_header_field_manipulation":
        return score_measurement_hhfm(msm)
    if tn == "whatsapp":
        return score_measurement_whatsapp(msm)
    if tn == "vanilla_tor":
        return score_vanilla_tor(msm)

    if tn == "web_connectivity":
        return score_web_connectivity(msm, matches)

    log.debug("Unsupported test name %s", tn)
    return {f"blocking_{l}": 0.0 for l in LOCALITY_VALS}


@metrics.timer("trivial_id")
def trivial_id(msm):
    """Generate a trivial id of the measurement to allow upsert if needed
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
    return msm_jstr, tid


def generate_filename(tid):
    """Generate filesystem-safe filename from a measurement
    """
    return tid + ".json.lz4"


@metrics.timer("writeout_measurement")
def writeout_measurement(msm_jstr, fn, update):
    """Safely write measurement to disk
    """
    # Different processes might be trying to write the same file at the same
    # time due to naming collisions. Use a safe tmpfile and atomic link
    # NamedTemporaryFile creates files with permissions 600
    # but we want other users (Nginx) to be able to read the measurement

    suffix = ".{}.tmp".format(os.getpid())
    with NamedTemporaryFile(suffix=suffix, dir=conf.msmtdir) as f:
        with lz4frame.open(f, "w") as lzf:
            lzf.write(msm_jstr)
            # os.fsync(lzf.fileno())

            final_fname = conf.msmtdir.joinpath(fn)
            try:
                os.chmod(f.name, 0o644)
                os.link(f.name, final_fname)
            except FileExistsError:
                if update:
                    # update access time - used for cache cleanup
                    # no need to overwrite the file
                    os.utime(final_fname)
                else:
                    log.info("Refusing to overwrite %s", final_fname)
                    metrics.incr("report_id_input_file_collision")
                    os.utime(final_fname)

    metrics.incr("wrote_uncompressed_bytes", len(msm_jstr))


def msm_processor(queue):
    """Measurement processor worker
    """
    db.setup(conf)
    while True:
        msm_tup = queue.get()

        if msm_tup is None:
            return

        with metrics.timer("full_run"):
            try:
                msm_jstr, measurement = msm_tup
                if measurement is None:
                    measurement = ujson.loads(msm_jstr)
                msm_jstr, tid = trivial_id(measurement)
                fn = generate_filename(tid)
                writeout_measurement(msm_jstr, fn, conf.update)
                if measurement.get("test_name", None) == "web_connectivity":
                    matches = match_fingerprints(measurement)
                else:
                    matches = []
                scores = score_measurement(measurement, matches)
                db.upsert_summary(measurement, scores, tid, fn, conf.update)
                db.trim_old_measurements(conf)
            except Exception as e:
                log.exception(e)
                metrics.incr("unhandled_exception")


def shut_down(queue):
    log.info("Shutting down workers")
    [queue.put(None) for n in range(NUM_WORKERS)]
    # FIXME
    #queue.close()
    #queue.join_thread()


def core():
    measurement_cnt = 0

    # There are 3 main data sources, in order of age:
    # - cans on S3
    # - older report files on collectors (max 1 day of age)
    # - report files on collectors fetched in "real-time"
    # Load json/yaml files and apply filters like canning

    t00 = time.time()
    scores = None

    # Spawn worker processes
    # 'queue' is a singleton from the portable_queue module
    workers = [
        mp.Process(target=msm_processor, args=(queue,)) for n in range(NUM_WORKERS)
    ]
    try:
        [t.start() for t in workers]

        for measurement_tup in fetch_measurements(conf.start_day, conf.end_day):
            assert len(measurement_tup) == 2
            msm_jstr, msm = measurement_tup
            assert msm_jstr is None or isinstance(msm_jstr, (str, bytes)), type(
                msm_jstr
            )
            assert msm is None or isinstance(msm, dict)

            measurement_cnt += 1
            while queue.qsize() >= 500:
                time.sleep(0.1)
            queue.put(measurement_tup)
            metrics.gauge("queue_size", queue.qsize())

            if conf.stop_after is not None and measurement_cnt >= conf.stop_after:
                log.info(
                    "Exiting with stop_after. Total runtime: %f", time.time() - t00
                )
                break

            # Interact from CLI
            if conf.devel and conf.interact:
                import bpython  # debdeps: bpython3

                bpython.embed(locals_=locals())
                break

    except Exception as e:
        log.exception(e)

    finally:
        shut_down(queue)
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
