# That's an ugly temporary hack
# vimdiff af/shovel/daily_workflow.py pipeline/batch/daily_workflow.py

import hashlib
import logging
import uuid
import re
import os

from base64 import b64encode
from datetime import datetime

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("ooni-pipeline")

# json and simplejson are ~4 times slower, performance IS a feature
from ujson import loads as json_loads
from ujson import dumps as json_dumps

import yaml
from yaml import CLoader  # yaml.Loader is ~40 times slower

test_name_mappings = {
    "http_host": "http_host",
    "HTTP Host": "http_host",
    "http_requests_test": "http_requests",
    "http_requests": "http_requests",
    "HTTP Requests Test": "http_requests",
    "bridge_reachability": "bridge_reachability",
    "bridgereachability": "bridge_reachability",
    "TCP Connect": "tcp_connect",
    "tcp_connect": "tcp_connect",
    "DNS tamper": "dns_consistency",
    "dnstamper": "dns_consistency",
    "dns_consistency": "dns_consistency",
    "HTTP Invalid Request Line": "http_invalid_request_line",
    "http_invalid_request_line": "http_invalid_request_line",
    "http_header_field_manipulation": "http_header_field_manipulation",
    "HTTP Header Field Manipulation": "http_header_field_manipulation",
    "Multi Protocol Traceroute Test": "multi_protocol_traceroute",
    "multi_protocol_traceroute_test": "multi_protocol_traceroute",
    "multi_protocol_traceroute": "multi_protocol_traceroute",
    "traceroute": "multi_protocol_traceroute",
    "parasitic_traceroute_test": "parasitic_traceroute",
    "parasitic_tcp_traceroute_test": "parasitic_traceroute",
    "tls-handshake": "tls_handshake",
    "tls_handshake": "tls_handshake",
    "dns_injection": "dns_injection",
    "captivep": "captive_portal",
    "captiveportal": "captive_portal",
    "HTTPFilteringBypass": "http_filtering_bypass",
    "httpfilteringbypass": "http_filtering_bypass",
    "HTTPTrix": "http_trix",
    "httptrix": "http_trix",
    "http_test": "http_test",
    "http_url_list": "http_url_list",
    "dns_spoof": "dns_spoof",
    "netalyzrwrapper": "netalyzr_wrapper",
    "meek_fronted_requests_test": "meek_fronted_requests_test",
    "lantern_circumvention_tool_test": "lantern_circumvention_tool_test",
    "psiphon_test": "psiphon_test",
    "this_test_is_nameless": "this_test_is_nameless",
    "test_get_random_capitalization": "http_header_field_manipulation",
    "test_put_random_capitalization": "http_header_field_manipulation",
    "test_post_random_capitalization": "http_header_field_manipulation",
    "test_random_big_request_method": "http_invalid_request_line",
    "test_random_invalid_field_count": "http_invalid_request_line",
    "summary": "invalid",
    "test_get": "invalid",
    "test_post": "invalid",
    "test_put": "invalid",
    "test_send_host_header": "invalid",
}

schema = [
    "id",
    "input",
    "input_hashes",
    "report_id",
    "report_filename",
    "options",
    "probe_cc",
    "probe_asn",
    "probe_ip",
    "probe_city",
    "backend_version",
    "data_format_version",
    "test_name",
    "test_version",
    "test_start_time",
    "measurement_start_time",
    "test_runtime",
    "test_helpers",
    "software_name",
    "software_version",
    "bucket_date",
    "test_keys",
]

test_categories = {
    "dnst": {"dns_consistency", "dns_injection", "captive_portal"},
    "process": {"lantern", "psiphon"},
    "httpt": {
        "http_requests",
        "meek_fronted_requests",
        "domclass_collector",
        "http_keyword_filtering",
        "http_uk_mobile_networks",
        "http_header_field_manipulation",
        "http_url_list",
        "http_host",
        "squid",
        "captive_portal",
        "psiphon",
        "tor_http_requests_test",
    },
    "scapyt": {
        "chinatrigger",
        "keyword_filtering",
        "parasitic_traceroute",
        "multi_protocol_traceroute",
        "dns_spoof",
    },
    "tcpt": {"http_filtering_bypass", "http_invalid_request_line", "http_trix"},
}

regexps = {
    "ipv4": "(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})",
    "hostname": "([a-zA-Z0-9](?:(?:[a-zA-Z0-9-]*|(?<!-)\.(?![-.]))*[a-zA-Z0-9]+)?)",
}


def binary_to_base64_dict(data):
    if isinstance(data, unicode):
        data = data.encode("utf-8", "ignore")
    return {"data": b64encode(data), "format": "base64"}


def normalise_str(body):
    if body is None:
        return body
    # XXX: original encoding is lost
    try:
        body = body.replace("\0", "")
        if not isinstance(body, unicode):
            body = unicode(body, "ascii")
    except UnicodeDecodeError:
        try:
            body = unicode(body, "utf-8")
        except UnicodeDecodeError:
            body = binary_to_base64_dict(body)
    return body


def regex_or_empty_string(pattern, source):
    found = re.search(pattern, source)
    if found:
        return found.group(1)
    return ""


class NormaliseReport(object):
    """"This task is responsible for reading the RAW report that is
    in either YAML or JSON format from the specified path, transforming it into
    JSON, adding all the missing keys and normalising the values of the ones
    present.

    report_path:
        The file path to the specified report. It is expected that the
        report_path follows the following format:
            s3n:// | ssh:// [[USER]:[PASS]] @ [HOST] / OONI_PRIVATE_DIR
                                                    / { bucket_date } /
            { test_name }-{ timestamp }-{ asn }-{ probe_cc }-probe-v2.yaml

            Where bucket_date is the date of the bucket where the report is
            in expressed as %Y-%M-%d and timestamp is the timestamp of when
            the report was generated expressed as %Y%M%dT%H%m%s.
    """

    if datetime.fromtimestamp(0) != datetime(1970, 1, 1, 0, 0, 0):
        raise RuntimeError("NormaliseReport requires TZ=UTC")

    @staticmethod
    def _normalise_httpt(entry):
        def _normalise_headers(headers):
            # XXX: data loss -- ordering, formatting, duplicate headers, whitespace
            normalised_headers = {}
            for name, values in headers:
                value = values[0]
                if isinstance(value, list):
                    value = value[0]
                normalised_headers[name] = normalise_str(value)
            return normalised_headers

        experiment_requests = []
        control_requests = []

        url_option_idx = None
        url_option_names = ["--url", "-u"]
        for url_option in url_option_names:
            try:
                url_option_idx = entry.get("options").index(url_option) + 1
            except (ValueError, AttributeError):
                continue

        if url_option_idx is not None and entry["input"] is None:
            entry["input"] = entry["options"][url_option_idx]

        # This is needed to fix the requests and responses in the
        # tor_http_requests test.
        if entry["test_keys"].get("request", None) and entry["test_keys"].get(
            "response", None
        ):
            entry["test_keys"]["requests"] = entry["test_keys"].get("requests", [])
            entry["test_keys"]["requests"].append(
                {
                    "response": entry["test_keys"].pop("response"),
                    "request": entry["test_keys"].pop("request"),
                }
            )

        for session in entry["test_keys"].get("requests", []):
            if isinstance(session.get("response"), dict):
                session["response"]["body"] = normalise_str(session["response"]["body"])
                session["response"]["headers"] = _normalise_headers(
                    session["response"]["headers"]
                )
            else:
                session["response"] = {"body": None, "headers": {}}

            if isinstance(session.get("request"), dict):
                session["request"]["body"] = normalise_str(session["request"]["body"])
                session["request"]["headers"] = _normalise_headers(
                    session["request"]["headers"]
                )
            else:
                session["request"] = {"body": None, "headers": {}}

            is_tor = False
            exit_ip = None
            exit_name = None
            if session["request"]["url"].startswith("shttp"):
                session["request"]["url"] = session["request"]["url"].replace(
                    "shttp://", "http://"
                )
                is_tor = True
            elif session["request"].get("tor") is True:
                is_tor = True
            elif session["request"].get("tor") in [False, None, {"is_tor": False}]:
                is_tor = False
            elif session["request"].get("tor", {}).get("is_tor") is True:
                is_tor = True
                exit_ip = session["request"].get("tor", {}).get("exit_ip", None)
                exit_name = session["request"].get("tor", {}).get("exit_name", None)
            else:
                logger.error("Could not detect tor or not tor status")
                logger.debug(session)

            session["request"]["tor"] = {
                "is_tor": is_tor,
                "exit_ip": exit_ip,
                "exit_name": exit_name,
            }
            session["response_length"] = None
            for k, v in session["response"]["headers"].items():
                # sort of re-normalisation from body back to binary
                if k.lower() == "content-length":
                    session["response_length"] = v
            if is_tor is True:
                control_requests.append(session)
            else:
                experiment_requests.append(session)
        entry["test_keys"]["requests"] = []
        try:
            entry["test_keys"]["requests"].append(experiment_requests.pop(0))
        except IndexError:
            pass
        try:
            entry["test_keys"]["requests"].append(control_requests.pop(0))
        except IndexError:
            pass
        entry["test_keys"]["requests"] += experiment_requests
        entry["test_keys"]["requests"] += control_requests
        if entry["test_keys"].get("headers_diff", None) is not None:
            entry["test_keys"]["headers_diff"] = list(
                entry["test_keys"]["headers_diff"]
            )
        return entry

    @staticmethod
    def _normalise_dnst(entry):
        entry["test_keys"].pop("test_resolvers", None)

        errors = entry["test_keys"].pop("tampering", None)
        if errors:
            entry["test_keys"]["errors"] = errors
            entry["test_keys"]["successful"] = map(
                lambda e: e[0], filter(lambda e: e[1] is False, errors.items())
            )
            entry["test_keys"]["failed"] = map(
                lambda e: e[0], filter(lambda e: e[1] is not True, errors.items())
            )
            entry["test_keys"]["inconsistent"] = map(
                lambda e: e[0], filter(lambda e: e[1] is True, errors.items())
            )
        elif entry["test_name"] == "dns_consistency":
            entry["test_keys"]["errors"] = {}
            entry["test_keys"]["successful"] = []
            entry["test_keys"]["failed"] = []
            entry["test_keys"]["inconsistent"] = []

        queries = []
        for query in entry["test_keys"].pop("queries", []):
            try:
                query["hostname"] = regex_or_empty_string(
                    "\[Query\('(.+)'", query.pop("query")
                )
            except:
                query["hostname"] = None

            try:
                query["resolver_hostname"], query["resolver_port"] = query.pop(
                    "resolver"
                )
            except:
                query["resolver_hostname"], query["resolver_port"] = [None, None]

            query.pop("addrs", None)

            answers = []
            for answer in query.pop("answers", []):
                try:
                    ttl = regex_or_empty_string("ttl=(\d+)", answer[0])
                except Exception:
                    logger.error("Failed to parse ttl in %s" % answer[0])
                    ttl = None

                answer_type = regex_or_empty_string("type=([A-Z]+)", answer[0])

                normalised_answer = dict(ttl=ttl, answer_type=answer_type)

                if answer_type == "A":
                    normalised_answer["ipv4"] = regex_or_empty_string(
                        "address=" + regexps["ipv4"], answer[1]
                    )
                elif answer_type == "MX":
                    normalised_answer["hostname"] = regex_or_empty_string(
                        "address=" + regexps["ipv4"], answer[1]
                    )
                    normalised_answer["preference"] = regex_or_empty_string(
                        "preference=(\d+)", answer[1]
                    )
                elif answer_type in ["PTR", "CNAME"]:
                    normalised_answer["hostname"] = regex_or_empty_string(
                        "name=" + regexps["hostname"], answer[1]
                    )
                elif answer_type == "SOA":
                    normalised_answer["responsible_name"] = regex_or_empty_string(
                        "rname=" + regexps["hostname"], answer[1]
                    )
                    normalised_answer["hostname"] = regex_or_empty_string(
                        "mname=" + regexps["hostname"], answer[1]
                    )
                    normalised_answer["serial_number"] = regex_or_empty_string(
                        "serial=(\d+)", answer[1]
                    )
                    normalised_answer["refresh_interval"] = regex_or_empty_string(
                        "refresh=(\d+)", answer[1]
                    )
                    normalised_answer["retry_interval"] = regex_or_empty_string(
                        "retry=(\d+)", answer[1]
                    )
                    normalised_answer["minimum_ttl"] = regex_or_empty_string(
                        "minimum=(\d+)", answer[1]
                    )
                    normalised_answer["expiration_limit"] = regex_or_empty_string(
                        "expire=(\d+)", answer[1]
                    )
                answers.append(normalised_answer)
            query["answers"] = answers

            failure = query.get("failure", None)
            if not failure and len(answers) == 0:
                failure = "no_answer"
            query["failure"] = failure

            queries.append(query)
        entry["test_keys"]["queries"] = queries
        return entry

    @staticmethod
    def _normalise_scapyt(entry):
        answered_packets = []
        sent_packets = []
        for pkt in entry["test_keys"].get("answered_packets", []):
            try:
                sanitised_packet = {
                    "raw_packet": binary_to_base64_dict(pkt[0]["raw_packet"]),
                    "summary": pkt[0]["summary"],
                }
                answered_packets.append(sanitised_packet)
            except IndexError:
                logger.error("Failed to find the index of the packet")
                continue
        for pkt in entry["test_keys"].get("sent_packets", []):
            try:
                sanitised_packet = {
                    "raw_packet": binary_to_base64_dict(pkt[0]["raw_packet"]),
                    "summary": pkt[0]["summary"],
                }
                sent_packets.append(sanitised_packet)
            except IndexError:
                logger.error("Failed to find the index of the packet")
                continue
        entry["test_keys"]["sent_packets"] = sent_packets
        entry["test_keys"]["answered_packets"] = answered_packets
        return entry

    @staticmethod
    def _normalise_tcpt(entry):
        return entry

    @staticmethod
    def _normalise_process(entry):
        return entry

    @staticmethod
    def _normalise_tls_handshake(entry):
        entry["test_keys"]["cert_serial_no"] = hex(
            entry["test_keys"].get("cert_serial_no", 0)
        )
        entry["test_keys"]["session_key"] = binary_to_base64_dict(
            entry["test_keys"].get("session_key", "")
        )

        normalised_subjects = []
        for name, value in entry["test_keys"].get("cert_subject", []):
            value = normalise_str(value)
        entry["test_keys"]["cert_subject"] = normalised_subjects

        normalised_issuer = []
        for name, value in entry["test_keys"].get("cert_issuer", []):
            value = normalise_str(value)
        entry["test_keys"]["cert_issuer"] = normalised_issuer

        return entry

    @staticmethod
    def _normalise_captive_portal(entry):
        if isinstance(entry.get("google_dns_cp", None), set):
            entry["google_dns_cp"] = list(entry["google_dns_cp"])
        elif isinstance(entry.get("google_dns_cp", {}).get("addresses", None), set):
            entry["google_dns_cp"]["addresses"] = list(
                entry["google_dns_cp"]["addresses"]
            )
        return entry

    @staticmethod
    def _nest_test_keys(entry):
        if entry["test_keys"] is None:
            entry["test_keys"] = {}
        for test_key in set(entry.keys()) - set(schema):
            entry["test_keys"][test_key] = entry.pop(test_key)

        return entry

    @classmethod
    def _normalise_entry(self, entry, bucket_date, perma_fname, hashuuid):
        if isinstance(entry.get("report"), dict):
            entry.update(entry.pop("report"))

        test_name = entry.get("test_name", "invalid")
        test_name = test_name_mappings.get(test_name, test_name.lower())
        entry["test_name"] = test_name

        entry["bucket_date"] = bucket_date

        if not entry.get("id"):
            entry["id"] = str(uuid.UUID(bytes=hashuuid))
        entry["report_filename"] = perma_fname

        # Ensure all the keys in the schema are present
        for key in schema:
            entry[key] = entry.get(key, None)

        if entry.get("data_format_version", "0.1.0") == "0.2.0":
            if entry["test_keys"] is None:
                entry = self._nest_test_keys(entry)
            return entry

        test_start_time = datetime.fromtimestamp(entry.pop("start_time", 0))
        try:
            tst = entry.pop("test_start_time")
            # This is the old test_start_time key that now is called
            # "measurement_start_time"
            if isinstance(tst, float):
                measurement_start_time = datetime.fromtimestamp(tst)
            elif tst is None:
                measurement_start_time = test_start_time
            else:
                test_start_time = datetime.strptime(tst, "%Y-%m-%d %H:%M:%S")
                measurement_start_time = datetime.strptime(
                    entry.get("measurement_start_time"), "%Y-%m-%d %H:%M:%S"
                )
        except KeyError:
            # Failback to using the start_time
            measurement_start_time = test_start_time

        entry["measurement_start_time"] = measurement_start_time.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        entry["test_start_time"] = test_start_time.strftime("%Y-%m-%d %H:%M:%S")

        entry["data_format_version"] = "0.2.0"

        if isinstance(entry.get("options", []), dict):
            entry["options"] = entry["options"].get("subargs", [])

        entry = self._nest_test_keys(entry)

        if test_name in test_categories["httpt"]:
            entry = self._normalise_httpt(entry)
        if test_name in test_categories["dnst"]:
            entry = self._normalise_dnst(entry)
        if test_name in test_categories["tcpt"]:
            entry = self._normalise_tcpt(entry)
        if test_name in test_categories["process"]:
            entry = self._normalise_processt(entry)
        if test_name in test_categories["scapyt"]:
            entry = self._normalise_scapyt(entry)
        if test_name == "captive_portal":
            entry = self._normalise_captive_portal(entry)
        if test_name == "tls_handshake":
            entry = self._normalise_tls_handshake(entry)
        return entry


class SanitiseReport(object):
    @staticmethod
    def _sanitise_bridge_reachability(entry, bridge_db):
        test_keys = entry["test_keys"]
        if not test_keys.get("bridge_address", None):
            test_keys["bridge_address"] = entry["input"]

        regexp = (
            "(Learned fingerprint ([A-Z0-9]+)"
            "\s+for bridge (([0-9]+\.){3}[0-9]+\:\d+))|"
            "((new bridge descriptor .+?\s+"
            "at (([0-9]+\.){3}[0-9]+)))"
        )
        if test_keys.get("tor_log"):
            test_keys["tor_log"] = re.sub(regexp, "[REDACTED]", test_keys["tor_log"])
        else:
            test_keys["tor_log"] = ""

        hashed_fingerprint = None
        if (
            test_keys["bridge_address"]
            and test_keys["bridge_address"].strip() in bridge_db
        ):
            b = bridge_db[test_keys["bridge_address"].strip()]
            test_keys["distributor"] = b["distributor"]
            test_keys["transport"] = b["transport"]
            fingerprint = b["fingerprint"].decode("hex")
            hashed_fingerprint = hashlib.sha1(fingerprint).hexdigest()
            test_keys["bridge_address"] = None
        else:
            bridge_line = test_keys["bridge_address"].split(" ")
            fingerprint = None
            if len(bridge_line) > 2 and len(bridge_line[2]) == 40:
                fingerprint = bridge_line[2].decode("hex")
            elif len(bridge_line) > 1 and len(bridge_line[1]) == 40:
                fingerprint = bridge_line[1].decode("hex")

            test_keys["distributor"] = None
            if fingerprint:
                hashed_fingerprint = hashlib.sha1(fingerprint).hexdigest()

        if hashed_fingerprint is not None:
            entry["input"] = hashed_fingerprint
        test_keys["bridge_hashed_fingerprint"] = hashed_fingerprint
        entry["test_keys"] = test_keys
        return entry

    @staticmethod
    def _sanitise_tcp_connect(entry, bridge_db):
        if entry["input"] and entry["input"].strip() in bridge_db.keys():
            b = bridge_db[entry["input"].strip()]
            fingerprint = b["fingerprint"].decode("hex")
            hashed_fingerprint = hashlib.sha1(fingerprint).hexdigest()
            entry["test_keys"]["bridge_hashed_fingerprint"] = hashed_fingerprint
            entry["input"] = hashed_fingerprint
            return entry
        return entry
