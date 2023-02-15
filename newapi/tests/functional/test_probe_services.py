from collections import Counter
import ooniapi.probe_services

from unittest.mock import patch


@patch("ooniapi.probe_services.extract_probe_ipaddr")
def test_round_robin_web_test_helpers(mock):
    # test fallback without mocked ipaddr
    li = ooniapi.probe_services.round_robin_web_test_helpers()
    assert li == [
        {"address": "https://1.th.ooni.org", "type": "https"},
        {"address": "https://2.th.ooni.org", "type": "https"},
        {"address": "https://3.th.ooni.org", "type": "https"},
        {"address": "https://0.th.ooni.org", "type": "https"},
    ]

    c = Counter()
    for n in range(200):
        mock.return_value = f"1.2.3.{n}"
        li = ooniapi.probe_services.round_robin_web_test_helpers()
        assert len(li) == 4
        addr = li[0]["address"]  # statistics on the first TH returned
        c[addr] += 1

    assert c == Counter(
        {
            "https://0.th.ooni.org": 20,
            "https://1.th.ooni.org": 60,
            "https://2.th.ooni.org": 60,
            "https://3.th.ooni.org": 60,
        }
    )
