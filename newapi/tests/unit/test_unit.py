from flask import url_for


def test_api_list_reports_index(client):
    resp = client.get(url_for("/api/v1.measurements_api_list_files"))
    assert resp.status_code == 200
    assert isinstance(resp.json["results"], list)
    assert isinstance(resp.json["metadata"], dict)

    assert isinstance(resp.json["metadata"]["limit"], int)
    assert isinstance(resp.json["metadata"]["count"], int)
    assert isinstance(resp.json["metadata"]["pages"], int)
    assert isinstance(resp.json["metadata"]["offset"], int)
    assert isinstance(resp.json["metadata"]["current_page"], int)

    assert any(
        [
            isinstance(resp.json["metadata"]["next_url"], str),
            resp.json["metadata"]["next_url"] is None,
        ]
    )


def test_api_list_reports_error(client):
    resp = client.get(url_for("/api/v1.measurements_api_list_files", order="INVALID"))
    assert resp.status_code == 400
    assert resp.json["title"] == "Bad Request"
    assert resp.json["detail"].startswith("'INVALID' is not one of")

    resp = client.get(
        url_for("/api/v1.measurements_api_list_files", order_by="INVALID")
    )
    assert resp.status_code == 400
    assert resp.json["title"] == "Bad Request"
    assert resp.json["detail"].startswith("'INVALID' is not one of")


def test_api_docs(client):
    resp = client.get(url_for("api_docs.api_docs"))
    assert resp.status_code == 200


def test_pages_index(client):
    resp = client.get(url_for("pages.index"))
    assert resp.status_code == 200


def test_pages_download_file_404(client):
    resp = client.get(url_for("pages.files_download", textname="/2019-01-01/DOES_NOT_EXIST"))
    assert resp.status_code == 404
