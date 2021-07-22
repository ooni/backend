import json


def jd(o):
    return json.dumps(o, indent=2, sort_keys=True)


def fjd(o):
    # non-indented JSON dump
    return json.dumps(o, sort_keys=True)


def privapi(client, subpath):
    response = client.get(f"/api/_/{subpath}")
    assert response.status_code == 200
    assert response.is_json
    return response.json
