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
