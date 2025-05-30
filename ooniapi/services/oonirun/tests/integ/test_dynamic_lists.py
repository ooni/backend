from copy import deepcopy
import json
from pathlib import Path
from oonirun.common.clickhouse_utils import insert_click
import pytest
from ..test_oonirun import SAMPLE_OONIRUN, SAMPLE_META

def postj(client, url, **kw):
    response = client.post(url, json=kw)
    assert response.status_code == 200
    return response.json()

@pytest.fixture
def url_priorities(clickhouse_db):
    path = Path("tests/fixtures/data")
    filename = "url_priorities_us.json"
    file = Path(path, filename)

    with file.open("r") as f:
        j = json.load(f)

    # 'sign' is created with default value 0, causing a db error.
    # use 1 to prevent it
    for row in j:
        row["sign"] = 1

    query = "INSERT INTO url_priorities (sign, category_code, cc, domain, url, priority) VALUES"
    insert_click(clickhouse_db, query, j)

def test_engine_descriptor_basic(client, client_with_user_role, url_priorities):
    z = deepcopy(SAMPLE_OONIRUN)
    z['name'] = "Testing header parsing"
    z['nettests'][0]['targets_name'] = 'websites_list_prioritized'
    z['nettests'][0]['inputs'] = None
    z['nettests'][0]['inputs_extra'] = None
    z['nettests'] = z['nettests'][:1]

    # Create a link
    j = postj(client_with_user_role, "/api/v2/oonirun/links", **z)
    orlid = j['oonirun_link_id']

    r = client_with_user_role.post(
        f"/api/v2/oonirun/links/{orlid}/engine-descriptor/latest",
        json=SAMPLE_META
    )
    assert r.status_code == 200, r.json()
    j = r.json()

    urls = j["nettests"][0]["inputs"]
    assert len(urls) > 1, urls