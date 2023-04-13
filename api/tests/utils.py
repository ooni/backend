import json
from pathlib import Path


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


def getjson(client, url):
    response = client.get(url)
    assert response.status_code == 200
    assert response.is_json
    return response.json


def mock_load_json():
    known = ("/etc/ooni/tor_targets.json", "/etc/ooni/psiphon_config.json")

    def load_json(fn):
        if fn in known:
            f = Path("tests/integ/data") / Path(fn).name
            print(f"    Mocking probe_services._load_json {fn} -> {f}")
            return json.loads(f.read_text())
        raise NotImplementedError(f"Unexpected fname to be mocked out: {fn}")

    return load_json
