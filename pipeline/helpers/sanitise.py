from __future__ import absolute_import, print_function, unicode_literals

import re
import hashlib


class Sanitisers(object):
    def __init__(self, bridge_db):
        self.bridge_db = bridge_db

    def http_template(self, entry):
        return entry

    def http_requests(self, entry):
        entry['test_name'] = 'http_requests'
        return entry

    def scapy_template(self, entry):
        return entry

    def dns_template(self, entry):
        return entry

    def dns_consistency(self, entry):
        entry['test_name'] = 'dns_consistency'
        tampered_resolvers = []
        for k, v in entry['tampering'].items():
            if v == True:
                tampered_resolvers.append(k)
        entry['tampered_resolvers'] = tampered_resolvers
        entry['tampering_detected'] = len(tampered_resolvers) > 0
        return entry

    def captive_portal(self, entry):
        entry['test_name'] = 'captive_portal'
        return entry

    def null(self, entry):
        return entry

    def bridge_reachability_tcp_connect(self, entry):
        if entry['input'] and entry['input'].strip() in self.bridge_db.keys():
            b = self.bridge_db[entry['input'].strip()]
            fingerprint = b['fingerprint'].decode('hex')
            hashed_fingerprint = hashlib.sha1(fingerprint).hexdigest()
            entry['bridge_hashed_fingerprint'] = hashed_fingerprint
            entry['input'] = hashed_fingerprint
            return entry
        return entry

    def bridge_reachability(self, entry):
        entry['test_name'] = 'bridge_reachability'
        if not entry.get('bridge_address'):
            entry['bridge_address'] = entry['input']

        if entry['bridge_address'] and \
                entry['bridge_address'].strip() in self.bridge_db:
            b = self.bridge_db[entry['bridge_address'].strip()]
            entry['distributor'] = b['distributor']
            entry['transport'] = b['transport']
            fingerprint = b['fingerprint'].decode('hex')
            hashed_fingerprint = hashlib.sha1(fingerprint).hexdigest()
            entry['input'] = hashed_fingerprint
            entry['bridge_address'] = None
            regexp = ("(Learned fingerprint ([A-Z0-9]+)"
                    "\s+for bridge (([0-9]+\.){3}[0-9]+\:\d+))|"
                    "((new bridge descriptor .+?\s+"
                    "at (([0-9]+\.){3}[0-9]+)))")
            if entry.get('tor_log'):
                entry['tor_log'] = re.sub(regexp, "[REDACTED]", entry['tor_log'])
            else:
                entry['tor_log'] = None
        else:
            entry['distributor'] = None
            hashed_fingerprint = None

        entry['bridge_hashed_fingerprint'] = hashed_fingerprint

        return entry

    def tcp_connect(self, entry):
        entry = self.bridge_reachability_tcp_connect(entry)
        entry['test_name'] = 'tcp_connect'
        return entry

    def default(self, entry):
        return entry


def get_sanitisers(test_name):
    sanitise_mapping = {
        "http_host": "http_template",
        "HTTP Host": "http_template",

        "http_requests_test": ["http_template",
                               "http_requests"],
        "http_requests": ["http_template", "http_requests"],
        "HTTP Requests Test": ["http_template",
                               "http_requests"],

        "bridge_reachability": "bridge_reachability",
        "bridgereachability": "bridge_reachability",

        "TCP Connect": "tcp_connect",
        "tcp_connect": "tcp_connect",

        "DNS tamper": ["dns_template", "dns_consistency"],
        "dns_consistency": ["dns_template", "dns_consistency"],

        "HTTP Invalid Request Line": "null",
        "http_invalid_request_line": "null",

        "http_header_field_manipulation": "null",
        "HTTP Header Field Manipulation": "null",

        "Multi Protocol Traceroute Test": ["scapy_template"],
        "multi_protocol_traceroute_test": ["scapy_template"],
        "traceroute": ["scapy_template"],

        "parasitic_traceroute_test": "null",

        "tls-handshake": "null",

        "dns_injection": "null",

        "captivep": "captive_portal",
        "captiveportal": "captive_portal",

        # These are ignored as we don't yet have analytics for them
        "HTTPFilteringBypass": False,
        "HTTPTrix": False,
        "http_test": False,
        "http_url_list": False,
        "dns_spoof": False,
        "netalyzrwrapper": False,

        # These are ignored because not code for them is available
        "tor_http_requests_test": False,
        "sip_requests_test": False,
        "tor_exit_ip_test": False,
        "website_probe": False,
        "base_tcp_test": False,

        # These are ignored because they are invalid reports
        "summary": False,
        "test_get": False,
        "test_put": False,
        "test_post": False,
        "this_test_is_nameless": False,
        "test_send_host_header": False,
        "test_random_big_request_method": False,
        "test_get_random_capitalization": False,
        "test_put_random_capitalization": False,
        "test_post_random_capitalization": False,
        "test_random_invalid_field_count": False,
        "keyword_filtering_detection_based_on_rst_packets": False,
        "default": "default"
    }
    return sanitise_mapping.get(test_name)


def run(test_name, entry, bridge_db=None):
    if bridge_db is None:
        try:
            from pipeline.helpers.settings import bridge_db_mapping
            bridge_db = bridge_db_mapping
        except ImportError:
            raise ValueError(
                "You must either pass bridge_db or copy"
                " pipeline/helpers/settings.example.py to"
                " pipeline/helpers/settings.py and configure it"
            )

    sanitisers = Sanitisers(bridge_db)
    test_sanitisers = get_sanitisers(test_name)
    if test_sanitisers in (False, None):
        return entry
    if not isinstance(test_sanitisers, list):
        sanitise = getattr(sanitisers, test_sanitisers)
        return sanitise(entry)
    for test_sanitiser in test_sanitisers:
        sanitise = getattr(sanitisers, test_sanitiser)
        entry = sanitise(entry)
    return entry
