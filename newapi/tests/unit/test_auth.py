import pytest

from ooniapi.auth import validate_redirect_url


def test_auth_explorer():
    redirect_to = (
        "https://explorer.ooni.org/country/IT?since=2021-01-01&until=2022-01-01"
    )
    redirect_to2, login_fqdn = validate_redirect_url(redirect_to)
    assert redirect_to2 == redirect_to
    assert login_fqdn == "explorer.ooni.org"


def test_auth_bogus():
    redirect_to = "https://invalid.ooni.org/country/IT"
    with pytest.raises(ValueError):
        validate_redirect_url(redirect_to)
