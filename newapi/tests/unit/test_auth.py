import pytest

from ooniapi.auth import generate_login_url


def test_auth_explorer():
    redirect_to = (
        "https://explorer.ooni.org/country/IT?since=2021-01-01&until=2022-01-01"
    )
    login_url = generate_login_url(redirect_to, "TOK")
    exp = "https://explorer.ooni.org/login?token=TOK&redirect_path=%2Fcountry%2FIT&redirect_query=since%3D2021-01-01%26until%3D2022-01-01"
    assert login_url == exp


def test_auth_escaping():
    redirect_to = "https://test-list.test.ooni.org/../../%252E%252E%252F?since=2021-01-01&until=2022-01-01&token=BOGUS"
    login_url = generate_login_url(redirect_to, "TOK")
    exp = "https://test-list.test.ooni.org/login?token=TOK&redirect_path=%2F..%2F..%2F%25252E%25252E%25252F&redirect_query=since%3D2021-01-01%26until%3D2022-01-01%26token%3DBOGUS"
    assert login_url == exp


def test_auth_bogus():
    redirect_to = "https://invalid.ooni.org/country/IT?since=2021-01-01&until=2022-01-01&token=XXX"
    with pytest.raises(ValueError):
        login_url = generate_login_url(redirect_to, "TOK")
