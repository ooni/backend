from copy import deepcopy
from oonirun.common.clickhouse_utils import insert_click
import pytest
from ..test_oonirun import SAMPLE_OONIRUN, SAMPLE_META


def postj(client, url, **kw):
    response = client.post(url, json=kw)
    assert response.status_code == 200
    return response.json()


def test_engine_descriptor_basic(client, client_with_user_role, url_priorities):
    z = deepcopy(SAMPLE_OONIRUN)
    z["name"] = "Testing simple prioritizationpri"
    z["nettests"][0]["targets_name"] = "websites_list_prioritized"
    z["nettests"][0]["inputs"] = None
    z["nettests"][0]["inputs_extra"] = None
    z["nettests"] = z["nettests"][:1]

    # Create a link
    j = postj(client_with_user_role, "/api/v2/oonirun/links", **z)
    orlid = j["oonirun_link_id"]

    # Get link
    r = client.post(
        f"/api/v2/oonirun/links/{orlid}/engine-descriptor/latest", json=SAMPLE_META
    )
    assert r.status_code == 200, r.json()
    j = r.json()

    urls = j["nettests"][0]["inputs"]
    assert len(urls) > 1, urls


def test_check_in_url_category_news(client, client_with_user_role, url_priorities):
    """
    Test that you can filter by category codes
    """
    z = deepcopy(SAMPLE_OONIRUN)
    z["name"] = "Categories filtering"
    z["nettests"][0]["targets_name"] = "websites_list_prioritized"
    z["nettests"][0]["inputs"] = None
    z["nettests"][0]["inputs_extra"] = None
    z["nettests"] = z["nettests"][:1]

    # Create a link
    j = postj(client_with_user_role, "/api/v2/oonirun/links", **z)
    orlid = j["oonirun_link_id"]

    # fetch the link
    meta = deepcopy(SAMPLE_META)
    meta["website_category_codes"] = ["NEWS"]
    j = postj(client, f"/api/v2/oonirun/links/{orlid}/engine-descriptor/latest", **meta)
    inputs = j["nettests"][0]["inputs"]
    inputs_extra = j["nettests"][0]["inputs_extra"]
    assert len(inputs), inputs
    assert len(inputs) == len(inputs_extra)
    for extra in inputs_extra:
        assert extra["category_code"] == "NEWS"


def test_prioritization_with_measurements(
    client, client_with_user_role, url_priorities, measurements
):
    """
    Test priorization including measurements
    """
    z = deepcopy(SAMPLE_OONIRUN)
    z["name"] = "Testing header parsing"
    z["nettests"][0]["targets_name"] = "websites_list_prioritized"
    z["nettests"][0]["inputs"] = None
    z["nettests"][0]["inputs_extra"] = None
    z["nettests"] = z["nettests"][:1]

    # Create a link
    j = postj(client_with_user_role, "/api/v2/oonirun/links", **z)
    orlid = j["oonirun_link_id"]

    # fetch the link
    meta = deepcopy(SAMPLE_META)
    # In ES we have more measurements for twitter, (see tests/fixtures/data/measurements.json)
    # so twitter should NOT show up first
    meta["probe_cc"] = "ES"
    j = postj(client, f"/api/v2/oonirun/links/{orlid}/engine-descriptor/latest", **meta)
    inputs = j["nettests"][0]["inputs"]
    assert len(inputs), inputs
    assert "twitter.com" not in inputs[0], "Twitter should not be the first one"

    # Twitter with a different asn can be first
    meta["probe_cc"] = "ES"
    meta["probe_asn"] = "AS9999"
    j = postj(client, f"/api/v2/oonirun/links/{orlid}/engine-descriptor/latest", **meta)
    inputs = j["nettests"][0]["inputs"]
    assert len(inputs), inputs
    assert "twitter.com" in inputs[0], "Twitter should be the first one"

    # Similarly, in IT twitter should be first, and facebook last
    meta["probe_cc"] = "IT"
    meta["probe_asn"] = "AS1234"
    j = postj(client, f"/api/v2/oonirun/links/{orlid}/engine-descriptor/latest", **meta)
    inputs = j["nettests"][0]["inputs"]
    assert len(inputs), inputs
    assert "twitter.com" in inputs[0], "Twitter should be the first one"
    assert "facebook.com" in inputs[-1], "Facebook should be the last one"


def test_priorities_basic(
    client,
    client_with_user_role,
    measurements,
    url_priorities,
    super_prioritized_website,
):
    z = deepcopy(SAMPLE_OONIRUN)
    z["name"] = "Testing header parsing"
    z["nettests"][0]["targets_name"] = "websites_list_prioritized"
    z["nettests"][0]["inputs"] = None
    z["nettests"][0]["inputs_extra"] = None
    z["nettests"] = z["nettests"][:1]

    # Create a link
    j = postj(client_with_user_role, "/api/v2/oonirun/links", **z)
    orlid = j["oonirun_link_id"]

    meta = deepcopy(SAMPLE_META)
    meta["probe_cc"] = "ES"
    j = postj(client, f"/api/v2/oonirun/links/{orlid}/engine-descriptor/latest", **meta)
    inputs = j["nettests"][0]["inputs"]
    assert len(inputs), inputs
    assert "ooni.org" in inputs[0], "Ooni should be the first one"
