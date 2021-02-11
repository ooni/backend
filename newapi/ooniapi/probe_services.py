"""
OONI Probe Services API
"""

from base64 import b64encode
from datetime import datetime
from os import urandom

from pathlib import Path
from hashlib import sha512
from urllib.request import urlopen

import ujson
from flask import Blueprint, current_app, request, make_response
from flask.json import jsonify

# import jwt  # debdeps: python3-jwt

from ooniapi.config import metrics
from ooniapi.utils import cachedjson

from ooniapi.prio import generate_test_list

probe_services_blueprint = Blueprint("ps_api", "probe_services")


def req_json():
    # Some probes are not setting the JSON mimetype.
    # if request.is_json():
    #    return request.json
    return ujson.loads(request.data)


def generate_report_id(test_name, cc: str, asn_i: int) -> str:
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    cid = "1"  # collector id  TODO read from conf
    rand = b64encode(urandom(12), b"oo").decode()
    rid = f"{ts}_{test_name}_{cc}_{asn_i}_n{cid}_{rand}"
    return rid


@probe_services_blueprint.route("/api/v1/check-in", methods=["POST"])
def check_in():
    """Probe Services: check-in. Probes ask for tests to be run
    ---
    parameters:
      - in: body
        name: probe self-description
        required: true
        schema:
          type: object
          properties:
            probe_cc:
              type: string
              description: Two letter, uppercase country code
              example: IT
            probe_asn:
              type: string
              description: ASN, two uppercase letters followed by number
              example: AS1234
            platform:
              type: string
              example: android
            software_name:
              type: string
              example: ooniprobe
            software_version:
              type: string
              example: 0.0.1
            on_wifi:
              type: boolean
            charging:
              description: set only on devices with battery; true when charging
              type: boolean
            run_type:
              type: string
              description: timed or manual
              example: timed

            web_connectivity:
              type: object
              properties:
                category_codes:
                  description: List/array of URL categories, all uppercase
                  type: array
                  items:
                    type: string
                    example: NEWS
        description: probe_asn and probe_cc are not provided if unknown

    responses:
      '200':
        description: Give a URL test list to a probe running web_connectivity
          tests; additional data for other tests;
        content:
          application/json:
            schema:
              type: object
              properties:
                v:
                  type: int
                probe_cc:
                  type: string
                  description: probe CC inferred from GeoIP or None
                probe_asn:
                  type: string
                  description: probe ASN inferred from GeoIP or None
                tests:
                  type: object
                  properties:
                    web_connectivity:
                      type: object
                      report_id:
                        type: string
    """

    # TODO: Implement throttling
    # TODO: Add geoip
    data = req_json()
    probe_cc = data.get("probe_cc", "ZZ").upper()
    asn = data.get("probe_asn", "AS0")
    # run_type = data.get("run_type", "timed")
    charging = data.get("charging", True)
    url_limit = 100 if charging else 20

    if "web_connectivity" not in data:
        category_codes = ()
    else:
        category_codes = data["web_connectivity"].get("category_codes", ())
        if isinstance(category_codes, str):
            category_codes = category_codes.split(",")

    assert asn.startswith("AS")
    asn_i = int(asn[2:])
    assert probe_cc.isalpha()
    assert len(probe_cc) == 2
    category_codes = tuple(category_codes)
    for c in category_codes:
        assert c.isalpha()

    try:
        test_items = generate_test_list(probe_cc, category_codes, url_limit)
    except:
        test_items = []

    resp = dict(
        v=1,
        tests={
            "web_connectivity": {"urls": test_items},
        },
        conf={
        }
    )

    # get asn, asn_i, probe_cc, network name
    test_names = (
        "bridge_reachability",
        "dash",
        "dns_consistency",
        "dnscheck",
        "facebook_messenger",
        "http_header_field_manipulation",
        "http_host",
        "http_invalid_request_line",
        "http_requests",
        "meek_fronted_requests_test",
        "multi_protocol_traceroute",
        "ndt",
        "psiphon",
        "riseupvpn",
        "tcp_connect",
        "telegram",
        "tor",
        "urlgetter",
        "vanilla_tor",
        "web_connectivity",
        "whatsapp",
    )
    for tn in test_names:
        stn = tn.replace("_", "")
        rid = generate_report_id(stn, probe_cc, asn_i)
        resp["tests"].setdefault(tn, {})
        resp["tests"][tn]["report_id"] = rid

    return jsonify(resp)


@probe_services_blueprint.route("/api/v1/collectors")
@metrics.timer("list_collectors")
def list_collectors():
    """Probe Services: list collectors
    ---
    responses:
      '200':
        description: List available collectors
    """
    # TODO load from configuration file
    j = [
        {"address": "httpo://guegdifjy7bjpequ.onion", "type": "onion"},
        {"address": "https://ams-pg.ooni.org:443", "type": "https"},
        {
            "address": "https://dkyhjv0wpi2dk.cloudfront.net",
            "front": "dkyhjv0wpi2dk.cloudfront.net",
            "type": "cloudfront",
        },
        {"address": "httpo://guegdifjy7bjpequ.onion", "type": "onion"},
        {"address": "https://ams-pg.ooni.org:443", "type": "https"},
        {
            "address": "https://dkyhjv0wpi2dk.cloudfront.net",
            "front": "dkyhjv0wpi2dk.cloudfront.net",
            "type": "cloudfront",
        },
    ]
    return cachedjson(1, j)


@probe_services_blueprint.route("/api/v1/test-helpers")
@metrics.timer("list_test_helpers")
def list_test_helpers():
    """Probe Services: List test helpers
    ---
    responses:
      200:
        description: A single user item
        schema:
          type: object
          properties:
            dns:
              type: object
            http-return-json-headers:
              type: object
            ssl:
              type: object
            tcp-echo:
              type: object
            traceroute:
              type: object
            web-connectivity:
              type: object
    """
    j = {
        "dns": [
            {"address": "37.218.241.93:57004", "type": "legacy"},
            {"address": "37.218.241.93:57004", "type": "legacy"},
        ],
        "http-return-json-headers": [
            {"address": "http://37.218.241.94:80", "type": "legacy"},
            {"address": "http://37.218.241.94:80", "type": "legacy"},
        ],
        "ssl": [
            {"address": "https://37.218.241.93", "type": "legacy"},
            {"address": "https://37.218.241.93", "type": "legacy"},
        ],
        "tcp-echo": [
            {"address": "37.218.241.93", "type": "legacy"},
            {"address": "37.218.241.93", "type": "legacy"},
        ],
        "traceroute": [
            {"address": "37.218.241.93", "type": "legacy"},
            {"address": "37.218.241.93", "type": "legacy"},
        ],
        "web-connectivity": [
            {"address": "httpo://o7mcp5y4ibyjkcgs.onion", "type": "legacy"},
            {"address": "https://wcth.ooni.io", "type": "https"},
            {
                "address": "https://d33d1gs9kpq1c5.cloudfront.net",
                "front": "d33d1gs9kpq1c5.cloudfront.net",
                "type": "cloudfront",
            },
            {"address": "httpo://y3zq5fwelrzkkv3s.onion", "type": "legacy"},
            {"address": "https://wcth.ooni.io", "type": "https"},
            {
                "address": "https://d33d1gs9kpq1c5.cloudfront.net",
                "front": "d33d1gs9kpq1c5.cloudfront.net",
                "type": "cloudfront",
            },
        ],
    }
    return cachedjson(1, **j)


# @probe_services_blueprint.route("/api/v1/test-list/psiphon-config")
# def serve_psiphon_config():
#    """Probe Services: Psiphon data
#    Not implemented
#    ---
#    responses:
#      '200':
#        description: TODO
#    """
#    #decoded = jwt.decode(encoded, key, algorithms="HS256")
#    return jsonify({"msg": "not implemented"})  # TODO


# @probe_services_blueprint.route("/api/v1/test-list/tor-targets")
# def serve_tor_targets():
#    """Probe Services: Tor targets
#    ---
#    responses:
#      '200':
#        description: TODO
#    """
#    return jsonify({"msg": "not implemented"})  # TODO


# Unneded: we use an external test helper
# @probe_services_blueprint.route("/api/private/v1/wcth")


def jerror(msg, code=400):
    return make_response(jsonify(error=msg), code)


@probe_services_blueprint.route("/invalidpath")
def invalidpath():
    return jerror(404, code=404)


@probe_services_blueprint.route("/bouncer/net-tests", methods=["POST"])
def bouncer_net_tests():
    """Probe Services: (legacy)
    ---
    parameters:
      - in: body
        name: open report data
        required: true
        schema:
          type: object
          properties:
            net-tests:
              type: array
    responses:
      '200':
        description: TODO
        content:
          application/json:
            schema:
              type: object
    """
    log = current_app.logger
    try:
        data = req_json()
        nt = data.get("net-tests")[0]
        name = nt["name"]
        version = nt["version"]
    except:
        return jerror("Malformed request")

    j = {
        "net-tests": [
            {
                "collector": "httpo://guegdifjy7bjpequ.onion",
                "collector-alternate": [
                    {"type": "https", "address": "https://ams-pg.ooni.org"},
                    {
                        "front": "dkyhjv0wpi2dk.cloudfront.net",
                        "type": "cloudfront",
                        "address": "https://dkyhjv0wpi2dk.cloudfront.net",
                    },
                ],
                "input-hashes": None,
                "name": name,
                "test-helpers": {
                    "tcp-echo": "37.218.241.93",
                    "http-return-json-headers": "http://37.218.241.94:80",
                    "web-connectivity": "httpo://y3zq5fwelrzkkv3s.onion",
                },
                "test-helpers-alternate": {
                    "web-connectivity": [
                        {"type": "https", "address": "https://wcth.ooni.io"},
                        {
                            "front": "d33d1gs9kpq1c5.cloudfront.net",
                            "type": "cloudfront",
                            "address": "https://d33d1gs9kpq1c5.cloudfront.net",
                        },
                    ]
                },
                "version": version,
            }
        ]
    }
    return jsonify(j)


@probe_services_blueprint.route("/report", methods=["POST"])
@metrics.timer("open_report")
def open_report():
    """Probe Services: Open report
    ---
    parameters:
      - in: body
        name: open report data
        required: true
        schema:
          type: object
          properties:
            data_format_version:
              type: string
            format:
              type: string
            probe_asn:
              type: string
            probe_cc:
              type: string
            software_name:
              type: string
            software_version:
              type: string
            test_name:
              type: string
            test_start_time:
              type: string
            test_version:
              type: string
    responses:
      '200':
        description: Open report confirmation
        content:
          application/json:
            schema:
              type: object
              properties:
                backend_version:
                  type: string
                report_id:
                  type: string
                supported_formats:
                  type: array
                  items:
                    type: string
    """
    log = current_app.logger

    try:
        data = req_json()
    except Exception as e:
        log.error(e)
        return jerror("JSON expected")

    log.info("Open report %r", data)
    asn = data.get("probe_asn", "AS0").upper()
    if len(asn) > 8 or len(asn) < 3 or not asn.startswith("AS"):
        asn = "AS0"
    try:
        asn_i = int(asn[2:])
    except:
        asn_i = 0
    cc = data.get("probe_cc", "ZZ").upper().replace("_", "")
    if len(cc) != 2:
        cc = "ZZ"
    test_name = data.get("test_name", "").lower().replace("_", "")
    rid = generate_report_id(test_name, cc, asn_i)
    return jsonify(
        backend_version="1.3.5", supported_formats=["yaml", "json"], report_id=rid
    )


@probe_services_blueprint.route("/report/<report_id>", methods=["POST"])
@metrics.timer("receive_measurement")
def receive_measurement(report_id):
    """Probe Services: Submit measurement
    ---
    parameters:
      - name: report_id
        in: path
        example: 20210208T162755Z_ndt_DZ_36947_n1_8swgXi7xNuRUyO9a
        type: string
        minLength: 10
        required: true
    responses:
      200:
        description: Acknowledge
        schema:
          type: object
          properties:
            measurement_uid:
              type: string
          example: {"measurement_uid": "20210208220710.181572_MA_ndt_7888edc7748936bf"}
    """
    log = current_app.logger
    try:
        rid_timestamp, test_name, cc, asn, format_cid, rand = report_id.split("_")
    except:
        log.info("Unexpected report_id %r", report_id[:200])
        return jerror("Incorrect format")

    # TODO validate the timestamp?
    good = len(cc) == 2 and test_name.isalnum() and 1 < len(test_name) < 30
    if not good:
        log.info("Unexpected report_id %r", report_id[:200])
        return jerror("Incorrect format")

    try:
        asn_i = int(asn)
    except ValueError:
        log.info("ASN value not parsable %r", asn)
        return jerror("Incorrect format")

    if asn_i == 0:
        log.info("Discarding ASN == 0")
        metrics.incr("receive_measurement_discard_asn_0")
        return jsonify()

    if cc.upper() == "ZZ":
        log.info("Discarding CC == ZZ")
        metrics.incr("receive_measurement_discard_cc_zz")
        return jsonify()

    # Write the whole body of the measurement in a directory based on a 1-hour
    # time window
    now = datetime.utcnow()
    hour = now.strftime("%Y%m%d%H")
    dirname = f"{hour}_{cc}_{test_name}"
    spooldir = Path(current_app.config["MSMT_SPOOL_DIR"])
    msmtdir = spooldir / "incoming" / dirname
    msmtdir.mkdir(parents=True, exist_ok=True)

    data = request.data
    h = sha512(data).hexdigest()[:16]
    ts = now.strftime("%Y%m%d%H%M%S.%f")
    # msmt_uid is a unique id based on upload time, cc, testname and hash
    msmt_uid = f"{ts}_{cc}_{test_name}_{h}"
    msmt_f_tmp = msmtdir / f"{msmt_uid}.post.tmp"
    msmt_f_tmp.write_bytes(data)
    msmt_f = msmtdir / f"{msmt_uid}.post"
    msmt_f_tmp.rename(msmt_f)
    metrics.incr("receive_measurement_count")

    try:
        url = f"http://127.0.0.1:8472/{msmt_uid}"
        urlopen(url, data, 59)
        return jsonify(measurement_uid=msmt_uid)

    except Exception as e:
        log.exception(e)
        return jsonify()


@probe_services_blueprint.route("/report/<report_id>/close", methods=["POST"])
def close_report(report_id):
    """Probe Services: Close report
    ---
    responses:
      '200':
        description: Close a report
    """
    return cachedjson(1)
