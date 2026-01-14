import requests as r


def test_fastpath_error_measurement_uid_is_empty(fastpath_service):
    measurement_uid = ""
    url = f"{fastpath_service}/{measurement_uid}"
    resp = r.post(url, data={})
    assert resp.status_code == 500
    assert "Internal Server Error" in resp.content.decode()

def test_fastpath_error_measurement_uid_does_not_start_with_2(fastpath_service):
    measurement_uid = "10210208220710.181572_MA_ndt_7888edc7748936bf"
    url = f"{fastpath_service}/{measurement_uid}"
    resp = r.post(url, data = b"")

    assert resp.status_code == 500
    assert "Internal Server Error" in resp.content.decode()


def test_fastpath_empty_response_ok(fastpath_service):
    measurement_uid = "20210208220710.181572_MA_ndt_7888edc7748936bf"
    url = f"{fastpath_service}/{measurement_uid}"
    data = {}

    response = r.post(url, data=data)

    assert response.status_code == 200
    assert response.content == b""

def test_fastpath_basic(fastpath_service):
    measurement_uid = "20210208220710.181572_MA_ndt_7888edc7748936bf"
    url = f"{fastpath_service}/{measurement_uid}"
    data = {
        'report_id': 'report_id',
        # 'input': 'input',
        'probe_cc': 'ZZ'
    }

    response = r.post(url, data=data)

    assert response.status_code == 200
    assert response.content == b""