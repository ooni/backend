from flask import url_for

def test_api_list_reports_index(client):
    resp = client.get(url_for('api.api_list_report_files'))
    assert resp.status_code == 200
    assert isinstance(resp.json['results'], list)
    assert isinstance(resp.json['metadata'], dict)

    assert isinstance(resp.json['metadata']['limit'], int)
    assert isinstance(resp.json['metadata']['count'], int)
    assert isinstance(resp.json['metadata']['pages'], int)
    assert isinstance(resp.json['metadata']['offset'], int)
    assert isinstance(resp.json['metadata']['current_page'], int)

    assert any([
        isinstance(resp.json['metadata']['next_url'], str),
        resp.json['metadata']['next_url'] is None
    ])

def test_api_list_reports_error(client):
    resp = client.get(url_for('api.api_list_report_files', order="INVALID"))
    assert resp.status_code == 400
    assert resp.json['error_message'] == "Invalid order"

    resp = client.get(url_for('api.api_list_report_files', order_by="INVALID"))
    assert resp.status_code == 400
    assert resp.json['error_message'] == "Invalid order_by"

def test_api_docs(client):
     resp = client.get(url_for('api_docs.api_docs'))
     assert resp.status_code == 200

def test_pages_index(client):
    resp = client.get(url_for('pages.index'))
    assert resp.status_code == 200

def test_pages_stats(client):
    resp = client.get(url_for('pages.stats'))
    assert resp.status_code == 200


def test_pages_files_index(client):
    resp = client.get(url_for('pages.files_index'))
    assert resp.status_code == 200

def test_pages_files_by_date_list(client):
    resp = client.get(url_for('pages.files_by_date'))
    assert resp.status_code == 200

def test_pages_files_by_date_calendar(client):
    resp = client.get(url_for('pages.files_by_date', view="calendar"))
    assert resp.status_code == 200

def test_pages_files_on_date(client):
    resp = client.get(url_for('pages.files_on_date', date='2016-01-01'))
    assert resp.status_code == 200

def test_pages_files_by_country_list(client):
    resp = client.get(url_for('pages.files_by_country'))
    assert resp.status_code == 200

def test_pages_files_by_country_flag(client):
    resp = client.get(url_for('pages.files_by_country', view="flag"))
    assert resp.status_code == 200

def test_pages_files_in_country(client):
    resp = client.get(url_for('pages.files_in_country', country_code='IT'))
    assert resp.status_code == 200

def test_pages_download_file_404(client):
    resp = client.get(url_for('pages.files_download',
                              textname="DOES_NOT_EXIST"))
    assert resp.status_code == 404
