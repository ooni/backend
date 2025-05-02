import json
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest


# def test_fastpath_error_data_is_empty():
#     url = f"http://127.0.0.1:8472/"
#     data = ""

#     with pytest.raises(TypeError, match="POST data should be bytes, an iterable of bytes, or a file object. It cannot be of type str."):
#         urlopen(url, data)

# def test_fastpath_error_measurement_uid_is_empty():
#     measurement_uid = ""
#     url = f"http://127.0.0.1:8472/{measurement_uid}"
#     data = "some_data".encode('utf-8')

#     with pytest.raises(HTTPError, match="Internal Server Error"):
#         urlopen(url, data)

# def test_fastpath_error_measurement_uid_does_not_start_with_2():
#     measurement_uid = "10210208220710.181572_MA_ndt_7888edc7748936bf"
#     url = f"http://127.0.0.1:8472/{measurement_uid}"
#     data = "some_data".encode('utf-8')

#     with pytest.raises(HTTPError, match="Internal Server Error"):
#         urlopen(url, data)

# def test_fastpath_response_ok():
#     measurement_uid = "20210208220710.181572_MA_ndt_7888edc7748936bf"
#     url = f"http://127.0.0.1:8472/{measurement_uid}"
#     data = {}

#     response = urlopen(url, json.dumps(data).encode('utf-8'))

#     assert response.getcode() == 200
#     assert response.read() == b""

def test_fastpath_TESTS(fastpath_service):
    raise ValueError("Crashing on purpose")
    print(fastpath_service)
    measurement_uid = "20210208220710.181572_MA_ndt_7888edc7748936bf"
    url = f"http://127.0.0.1:8472/{measurement_uid}"
    data = {
        'report_id': 'report_id',
        # 'input': 'input',
        'probe_cc': 'ZZ'
    }

    response = urlopen(url, json.dumps(data).encode('utf-8'))

    assert response.getcode() == 200
    assert response.read() == b""