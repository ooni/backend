import pytest

from ooniapi import measurements as apimsm


def test_param_report_id_missing(app):
    params = {}
    with app.test_request_context("/", query_string=params):
        pytest.raises(Exception, apimsm.param_report_id)


def test_param_report_id_valid(app):
    rid = "20220816T111242Z_webconnectivity_IR_197207_n1_KJYYCOK8vwUiOBSe"
    params = {"report_id": rid}
    with app.test_request_context("/", query_string=params):
        rid_x = apimsm.param_report_id()
        assert rid == rid_x


def test_param_report_id_invalid(app):
    rid = "20220816T111242Z_webconnectivity_IR_197207_n1_KJYYCOK8vwUiOBSe+"
    params = {"report_id": rid}
    with app.test_request_context("/", query_string=params):
        pytest.raises(Exception, apimsm.param_report_id)


def test_param_url_empty(app):
    params = {"input": ""}
    with app.test_request_context("/", query_string=params):
        assert apimsm.param_url("input") == ""


def test_param_url_invalid(app):
    params = {"input": "(-/"}
    with app.test_request_context("/", query_string=params):
        pytest.raises(Exception, apimsm.param_url)


def test_param_input_or_none_invalid(app):
    params = {"input": ""}
    with app.test_request_context("/", query_string=params):
        assert apimsm.param_input_or_none() is None

    with app.test_request_context("/"):
        assert apimsm.param_input_or_none() is None


def test_param_input_or_none_valid(app):
    valid_inputs = [
        "https://foo.org",
        "http://foo.org",
        "https://8.8.4.4/dns-query",
        "dot://doh-de.blahdns.com/dns-query",
        "dot://8.8.8.8:853/",
        "dot://[2a00:5a60::ad2:0ff]:853",
        "stun://stun.voip.blackberry.com:3478",
        "obfs3 83.212.101.3:80",
        "obfs3 83.212.101.3:80 A09D536DD1752D542E1FBB3C9CE4449D51298239",
        "fte 50.7.176.114:80 2BD466989944867075E872310EBAD65BC88C8AEF",
        "udp://8.8.8.8",
        "scramblesuit 83.212.101.3:443",
        "https://ru.wikipedia.org/wiki/Вторжение_России_на_Украину_(2022)",
        "obfs4 154.35.22.9:80 C73AD cert=gEWN/bS",
        "obfs4 154.35.22.10:40348",
        "1.1.1.1",
        "178.62.197.82:443",
    ]
    for inp in valid_inputs:
        params = {"input": inp}
        with app.test_request_context("/", query_string=params):
            assert apimsm.param_input_or_none() == inp


def test_param_domain_or_none_valid(app):
    valid_domains = [
        "foo.org",
        "8.8.4.4",
        "doh-de.blahdns.com",
        "8.8.8.8:853",
        "[2a00:5a60::ad2:0ff]:853",
        "stun.voip.blackberry.com:3478",
    ]
    for dom in valid_domains:
        params = {"domain": dom}
        with app.test_request_context("/", query_string=params):
            assert apimsm.param_domain_or_none("domain") == dom
