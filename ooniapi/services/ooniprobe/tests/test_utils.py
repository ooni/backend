from ooniprobe.utils import get_first_ip

def test_get_first_ip():

    assert get_first_ip("1.1.1.1") == "1.1.1.1"
    assert get_first_ip("1.1.1.1, 2.2.2.2") == "1.1.1.1"
    assert get_first_ip("") == ""