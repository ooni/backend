from unittest.mock import MagicMock, Mock

import ooniapi.probe_services
from ooniapi.probe_services import random_web_test_helpers, round_robin_web_test_helpers


def test_web_test_helpers():
    ooniapi.probe_services.extract_probe_ipaddr = Mock(return_value="1.2.3.4")
    r1 = random_web_test_helpers(
        [
            "https://0.th.ooni.org",
            "https://1.th.ooni.org",
            "https://2.th.ooni.org",
            "https://3.th.ooni.org",
            "https://4.th.ooni.org",
        ]
    )
    r2 = round_robin_web_test_helpers()
    th1 = set(list(map(lambda x: x["address"], r1)))
    th2 = set(list(map(lambda x: x["address"], r2)))
    assert th1 == th2
