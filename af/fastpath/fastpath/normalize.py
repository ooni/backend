#
# Normalize YAML reports
#

from datetime import datetime
import logging
import re
import hashlib
import uuid

import lz4.frame as lz4frame  # debdeps: python3-lz4


log = logging.getLogger("normalize")


class UnsupportedTestError(Exception):
    pass


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

# Some values overlap across categories e.g. captive_portal
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


## Simhash generation

from itertools import groupby

simhash_re = re.compile(r"[\w\u4e00-\u9fcc]+")


def gen_simhash(s):
    content = s.lower()
    content = "".join(re.findall(simhash_re, content))
    mx = max(len(content) - 4 + 1, 1)
    features = [content[i : i + 4] for i in range(mx)]
    features = ((k, sum(1 for _ in g)) for k, g in groupby(sorted(features)))
    v = [0] * 64
    masks = [1 << i for i in range(64)]
    for h, w in features:
        h = h.encode("utf-8")
        h = int(hashlib.md5(h).hexdigest(), 16)
        for i in range(64):
            v[i] += w if h & masks[i] else -w
    ans = 0
    for i in range(64):
        if v[i] > 0:
            ans |= masks[i]
    return ans


### Normalize entries across format versions ###


def nest_test_keys(entry):
    if entry["test_keys"] is None:
        entry["test_keys"] = {}
    for test_key in set(entry.keys()) - set(schema):
        entry["test_keys"][test_key] = entry.pop(test_key)

    return entry


def normalize_str(body):
    if body is None:
        return None
    assert len(body) < 10000
    if isinstance(body, bytes):
        return body.decode("UTF-8", "backslashreplace")
    return body.replace("\0", "")


def normalize_body(body):
    if body is None:
        return None

    if isinstance(body, bytes):
        return body.decode("UTF-8", "backslashreplace")

    return body.replace("\0", "")


def regex_or_empty_string(pattern, source):
    found = re.search(pattern, source)
    if found:
        return found.group(1)
    return ""


def normalize_httpt(entry):
    def normalize_headers(headers):
        # XXX: data loss -- ordering, formatting, duplicate headers, whitespace
        normalized_headers = {}
        for name, values in headers:
            value = values[0]
            if isinstance(value, list):
                value = value[0]
            normalized_headers[name] = normalize_str(value)
        return normalized_headers

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
            session["response"]["body"] = normalize_body(session["response"]["body"])
            session["response"]["headers"] = normalize_headers(
                session["response"]["headers"]
            )
        else:
            session["response"] = {"body": None, "headers": {}}

        if isinstance(session.get("request"), dict):
            session["request"]["body"] = normalize_body(session["request"]["body"])
            session["request"]["headers"] = normalize_headers(
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
            log.error("Could not detect tor or not tor status")
            log.debug(session)

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
        entry["test_keys"]["headers_diff"] = list(entry["test_keys"]["headers_diff"])
    return entry


def normalize_dnst(entry):
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
            query["resolver_hostname"], query["resolver_port"] = query.pop("resolver")
        except:
            query["resolver_hostname"], query["resolver_port"] = [None, None]

        query.pop("addrs", None)

        answers = []
        for answer in query.pop("answers", []):
            try:
                ttl = regex_or_empty_string("ttl=(\d+)", answer[0])
            except Exception:
                log.error("Failed to parse ttl in %s" % answer[0])
                ttl = None

            answer_type = regex_or_empty_string("type=([A-Z]+)", answer[0])

            normalized_answer = dict(ttl=ttl, answer_type=answer_type)

            if answer_type == "A":
                normalized_answer["ipv4"] = regex_or_empty_string(
                    "address=" + regexps["ipv4"], answer[1]
                )
            elif answer_type == "MX":
                normalized_answer["hostname"] = regex_or_empty_string(
                    "address=" + regexps["ipv4"], answer[1]
                )
                normalized_answer["preference"] = regex_or_empty_string(
                    "preference=(\d+)", answer[1]
                )
            elif answer_type in ["PTR", "CNAME"]:
                normalized_answer["hostname"] = regex_or_empty_string(
                    "name=" + regexps["hostname"], answer[1]
                )
            elif answer_type == "SOA":
                normalized_answer["responsible_name"] = regex_or_empty_string(
                    "rname=" + regexps["hostname"], answer[1]
                )
                normalized_answer["hostname"] = regex_or_empty_string(
                    "mname=" + regexps["hostname"], answer[1]
                )
                normalized_answer["serial_number"] = regex_or_empty_string(
                    "serial=(\d+)", answer[1]
                )
                normalized_answer["refresh_interval"] = regex_or_empty_string(
                    "refresh=(\d+)", answer[1]
                )
                normalized_answer["retry_interval"] = regex_or_empty_string(
                    "retry=(\d+)", answer[1]
                )
                normalized_answer["minimum_ttl"] = regex_or_empty_string(
                    "minimum=(\d+)", answer[1]
                )
                normalized_answer["expiration_limit"] = regex_or_empty_string(
                    "expire=(\d+)", answer[1]
                )
            answers.append(normalized_answer)
        query["answers"] = answers

        failure = query.get("failure", None)
        if not failure and len(answers) == 0:
            failure = "no_answer"
        query["failure"] = failure

        queries.append(query)
    entry["test_keys"]["queries"] = queries
    return entry


def normalize_tcpt(entry):
    return entry


def normalize_process(entry):
    return entry


def normalize_entry(entry, bucket_date, perma_fname, esha):
    """Autoclaving
    """
    hashuuid = esha[:16]  # sha1 is 20 bytes

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
            entry = nest_test_keys(entry)
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

    entry = nest_test_keys(entry)

    assert test_name not in test_categories["process"]

    # Some values overlap across categories so multiple ifs are needed
    if test_name in test_categories["httpt"]:
        entry = normalize_httpt(entry)
    if test_name in test_categories["dnst"]:
        entry = normalize_dnst(entry)

    # Ignore old, rare tests
    if test_name in test_categories["scapyt"]:
        raise UnsupportedTestError

    if test_name in ("captive_portal", "tls_handshake"):
        raise UnsupportedTestError

    # TODO: tests these in
    # test_normalize_yaml_sanitise_tcp_connect_bridge_reach
    if entry["test_name"] == "tcp_connect":
        # On 2019-10-08 the last bridge_reachability entry from YAML
        # in the metadb was from 2016-10-12
        raise UnsupportedTestError

    elif entry["test_name"] == "bridge_reachability":
        # On 2019-10-08 the last bridge_reachability entry from YAML
        # in the metadb was from 2016-10-12
        raise UnsupportedTestError

    return entry


### Stream entries from YAML.lz4 files ####

import yaml
from yaml import CLoader


class BlobSlicerError(RuntimeError):
    pass


class BrokenFrameError(BlobSlicerError):
    pass


class TruncatedReportError(BlobSlicerError):
    pass


import functools
import string


def stream_yaml_blobs(fd):
    head = b""
    for blob in iter(functools.partial(fd.read, 1048576), ""):
        if len(blob) == 0:
            break
        bloboff = fd.tell() - len(blob)
        head, blob = b"", head + blob
        start = 0
        while head == b"":
            prefix = blob[start : start + 4]
            if prefix == b"---\n":  # ordinary preamble
                end = blob.find(b"\n...\n", start)
                if end != -1:
                    yield bloboff + start, blob[start : end + 5]
                    start = end + 5
                else:
                    head = blob[start:]
            elif not prefix:
                break
            elif prefix == b"...\n":  # duplicate trailer
                # e.g. 2013-05-05/20130505T065614Z-VN-AS24173-dns_consistency-no_report_id-0.1.0-probe.yaml
                start += 4
            elif len(prefix) < 4:  # need next blob
                head = blob[start:]
            elif chr(prefix[0]) == "#":  # comment
                # e.g. 2013-09-12/20130912T144929Z-MD-AS1547-dns_consistency-no_report_id-0.1.0-probe.yaml
                end = blob.find(b"\n", start)
                if end != -1:
                    start = end + 1
                else:
                    head = blob[start:]
            else:
                raise BrokenFrameError(bloboff + start, prefix)

    if head:
        raise TruncatedReportError(fd.tell() - len(head), head[:100])


def generate_report_id(header):
    # TODO: test
    start_time = datetime.fromtimestamp(header.get("start_time", 0))
    report_id = start_time.strftime("%Y%m%dT%H%M%SZ_")
    value_to_hash = header.get("probe_cc", "ZZ").encode("utf-8")
    value_to_hash += header.get("probe_asn", "AS0").encode("utf-8")
    value_to_hash += header.get("test_name", "invalid").encode("utf-8")
    value_to_hash += header.get("software_version", "0.0.0").encode("utf-8")
    probe_city = header.get("probe_city", "None")
    # probe_city = probe_city.encode("utf-8")  # u'Reykjav\xedk' in bucket 2014-02-20
    # probe_city = (
    #   probe_city.encode("utf-8")
    #   if isinstance(probe_city, unicode)
    #   else str(probe_city)
    # )  # u'Reykjav\xedk' in bucket 2014-02-20
    # probe_city = probe_city.decode() #encode("utf-8")
    value_to_hash += probe_city.encode("utf-8")
    report_id += "".join(
        string.ascii_letters[b % len(string.ascii_letters)]
        for b in hashlib.sha512(value_to_hash).digest()
    )[:50]
    return report_id


def iter_yaml_lz4_reports(fn):

    fd = lz4frame.open(fn)
    report_gen = stream_yaml_blobs(fd)

    off, header = next(report_gen)
    headsha = hashlib.sha1(header)
    # XXX: bad header kills whole bucket
    header = yaml.load(header, Loader=CLoader)
    if not header.get("report_id"):
        header["report_id"] = generate_report_id(header)

    for off, entry in report_gen:
        entry_len = len(entry)
        esha = headsha.copy()
        esha.update(entry)
        esha = esha.digest()
        try:
            entry = yaml.load(entry, Loader=CLoader)
            if not entry:  # e.g. '---\nnull\n...\n'
                continue
            if "test_start_time" in entry and "test_start_time" in header:
                header.pop("test_start_time")
            entry.update(header)
            yield off, entry_len, esha, entry, None
        except Exception as exc:
            yield off, entry_len, esha, None, exc

    fd.close()


## Entry points


def iter_yaml_msmt_normalized(data):
    """Yields normalized measurements from a YAML BytesIO
    """
    report_gen = stream_yaml_blobs(data)

    off, header = next(report_gen)
    headsha = hashlib.sha1(header)
    # XXX: bad header kills whole bucket
    header = yaml.load(header, Loader=CLoader)
    if not header.get("report_id"):
        header["report_id"] = generate_report_id(header)

    for off, entry in report_gen:
        esha = headsha.copy()
        esha.update(entry)
        esha = esha.digest()
        try:
            entry = yaml.load(entry, Loader=CLoader)
            if not entry:  # e.g. '---\nnull\n...\n'
                continue
            if "test_start_time" in entry and "test_start_time" in header:
                header.pop("test_start_time")
            entry.update(header)
            yield normalize_entry(entry, "2018-05-07", "??", esha)
        except Exception as exc:
            yield normalize_entry(entry, "2018-05-07", "??", esha)


def iter_yaml_lz4_reports_normalized(fn):
    """Yields normalized measurements from a yaml.lz4 file
    """
    for r in iter_yaml_lz4_reports(fn):
        off, entry_len, esha, entry, exc = r
        yield normalize_entry(entry, "2018-05-07", "??", esha)
