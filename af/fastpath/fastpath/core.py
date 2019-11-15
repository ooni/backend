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


@metrics.timer("score_measurement")
def score_measurement(msm, matches):
    """Calculate measurement scoring. Returns a summary dict
    """
    # Extract interesting fields
    fields = (
        "input",
        "measurement_start_time",
        "probe_asn",
        "probe_cc",
        "report_id",
        "test_name",
        "test_start_time",
    )
    summary = {k: msm[k] for k in fields}

    # Blocking locality: global > country > ISP > local
    # unclassified locality is stored in "blocking_general"

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

    # TODO: add IM tests scoring here

    # TODO: add heuristic to split blocking_general into local/ISP/country/global
    scores["blocking_general"] += (
        scores["blocking_country"]
        + scores["blocking_global"]
        + scores["blocking_isp"]
        + scores["blocking_local"]
    )
    summary["scores"] = scores
    return summary


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
    db.setup()
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
                summary = score_measurement(measurement, matches)
                db.upsert_summary(measurement, summary, tid, fn, conf.update)
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
