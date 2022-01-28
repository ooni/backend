# Publised to Explorer in private.py
# Also used in measurement.py

TEST_GROUPS = {
    "websites": ["web_connectivity"],
    "im": ["facebook_messenger", "signal", "telegram", "whatsapp"],
    "middlebox": ["http_invalid_request_line", "http_header_field_manipulation"],
    "performance": ["ndt", "dash"],
    "circumvention": [
        "bridge_reachability",
        "meek_fronted_requests_test",
        "vanilla_tor",
        "tcp_connect",
        "psiphon",
        "tor",
        "torsf",
        "riseupvpn",
    ],
    "legacy": [
        "http_requests",
        "dns_consistency",
        "http_host",
        "multi_protocol_traceroute",
    ],
    "experimental": [
        "urlgetter",
        "dnscheck",
        "stunreachability",
    ],
}

# Used in ooniapi/measurements.py for validation
TEST_NAMES = []
for v in TEST_GROUPS.values():
    assert isinstance(v, list)
    TEST_NAMES.extend(v)


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
