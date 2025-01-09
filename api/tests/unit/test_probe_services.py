
import ipaddress
import ooniapi.probe_services
from ooniapi.probe_services import random_web_test_helpers

def round_robin_web_test_helpers(ipa) -> List[Dict]:
    """Round robin test helpers based on the probe ipaddr.
    0.th is special and gets only 10% of the traffic.
    """
    try:
        # ipaddr as (large) integer representation (v4 or v6)
        q = int(ipaddress.ip_address(ipa))
        q = q % 100
    except Exception:
        q = 12  # pick 1.th

    if q < 10:
        shift = 0
    else:
        shift = q % 4 + 1

    out = []
    for n in range(5):
        n = (n + shift) % 5
        out.append({"address": f"https://{n}.th.ooni.org", "type": "https"})

    return out


def test_web_test_helpers():
    r1 = random_web_test_helpers(
        [
            "https://0.th.ooni.org",
            "https://1.th.ooni.org",
            "https://2.th.ooni.org",
            "https://3.th.ooni.org",
            "https://4.th.ooni.org",
        ]
    )
    r2 = round_robin_web_test_helpers("1.2.3.4")
    th1 = set(list(map(lambda x: x["address"], r1)))
    th2 = set(list(map(lambda x: x["address"], r2)))
    assert th1 == th2
