from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

# Publised to Explorer in private.py

TEST_NAMES = {
    "web_connectivity": "Web Connectivity",
    "facebook_messenger": "Facebook Messenger",
    "telegram": "Telegram",
    "whatsapp": "WhatsApp",
    "http_invalid_request_line": "HTTP Invalid Request Line",
    "http_header_field_manipulation": "HTTP Header Field Manipulation",
    "ndt": "NDT",
    "dash": "DASH",
    "bridge_reachability": "Bridge Reachability",
    "meek_fronted_requests_test": "Meek Fronted Requests",
    "vanilla_tor": "Vanilla Tor",
    "tcp_connect": "TCP Connect",
    "http_requests": "HTTP Requests",
    "dns_consistency": "DNS Consistency",
    "http_host": "HTTP Host",
    "multi_protocol_traceroute": "Multi Protocol Traceroute",
    "psiphon": "Psiphon",
    "tor": "Tor",
}

TEST_GROUPS = {
    "websites": ["web_connectivity"],
    "im": ["facebook_messenger", "telegram", "whatsapp"],
    "middlebox": ["http_invalid_request_line", "http_header_field_manipulation"],
    "performance": ["ndt", "dash"],
    "circumvention": [
        "bridge_reachability",
        "meek_fronted_requests_test",
        "vanilla_tor",
        "tcp_connect",
        "psiphon",
        "tor",
    ],
    "legacy": [
        "http_requests",
        "dns_consistency",
        "http_host",
        "multi_protocol_traceroute",
    ],
}


def get_test_group_case():
    """
    Returns a postgres CASE statement to return the test_group based on the
    value of test_name.
    """
    c = "CASE\n"
    for tg_name, tests in TEST_GROUPS.items():
        c += "WHEN test_name = ANY('{{{}}}') THEN '{}'\n".format(
            ",".join(tests), tg_name
        )
    c += "ELSE 'unknown'\n"
    c += "END\n"
    return c
