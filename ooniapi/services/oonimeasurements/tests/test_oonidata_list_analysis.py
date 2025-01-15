import pytest

route = "api/v1/analysis"
since = "2024-11-01"
until = "2024-11-02"

def test_oonidata_list_analysis(client):
    response = client.get(route)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) == 0

def test_oonidata_list_analysis_with_since_and_until(client):
    response = client.get(f"{route}?since={since}&until={until}")

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for result in json["results"]:
        assert "test_name" in result, result
        assert "probe_cc" in result, result

@pytest.mark.parametrize(
    "filter_param, filter_value",
    [
        ("measurement_uid", "20241101233756.866609_TH_webconnectivity_1bf55fb5699c39ec"),
        ("probe_asn", 45758),
        ("probe_cc", "IT"),
        ("test_name", "web_connectivity"),
    ]
)
def test_oonidata_list_analysis_with_filters(client, filter_param, filter_value):
    params = {
        "since": since,
        "until": until
    }
    params[filter_param] = filter_value

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for result in json["results"]:
        assert result[filter_param] == filter_value, result

def test_oonidata_list_analysis_filtering_by_probe_asn_as_a_string_with_since_and_until(client):
    probe_asn = 45758
    probe_asn_as_a_string =  "AS" + str(probe_asn)

    response = client.get(f"{route}?probe_asn={probe_asn_as_a_string}&since={since}&until={until}")

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for result in json["results"]:
        assert result["probe_asn"] == probe_asn, result

def test_oonidata_list_analysis_order_default(client):
    response = client.get(f"{route}?since={since}&until={until}")

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for i in range(1, len(json["results"])):
        assert "measurement_start_time" in json["results"][i], json["results"][i]
        previous_date = json["results"][i - 1]["measurement_start_time"]
        current_date = json["results"][i]["measurement_start_time"]
        assert previous_date >= current_date, f"The dates are not ordered: {previous_date} < {current_date}"

def test_oonidata_list_analysis_order_asc(client):
    response = client.get(f"{route}?order=ASC&since={since}&until={until}")

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for i in range(1, len(json["results"])):
        assert "measurement_start_time" in json["results"][i], json["results"][i]
        previous_date = json["results"][i - 1]["measurement_start_time"]
        current_date = json["results"][i]["measurement_start_time"]
        assert previous_date <= current_date, f"The dates are not ordered: {previous_date} > {current_date}"

@pytest.mark.parametrize(
    "order_param, order",
    [
        ("input", "asc"),
        ("probe_cc", "asc"),
        ("probe_asn", "asc"),
        ("test_name", "asc"),
        ("input", "desc"),
        ("probe_cc", "desc"),
        ("probe_asn", "desc"),
        ("test_name", "desc"),
    ]
)
def test_oonidata_list_analysis_order_by_field(client, order_param, order):
    response = client.get(f"{route}?order_by={order_param}&order={order}&since={since}&until={until}")

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for i in range(1, len(json["results"])):
        assert order_param in json["results"][i], json["results"][i]
        previous = json["results"][i - 1][order_param]
        current = json["results"][i][order_param]
        if order == "asc":
            assert previous <= current, f"The {order_param} values are not ordered in ascending order: {previous} > {current}"
        else:
            assert previous >= current, f"The {order_param} values are not ordered in descending order: {previous} < {current}"

def test_oonidata_list_analysis_limit_by_default(client):
    response = client.get(f"{route}?since={since}&until={until}")

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) == 100

def test_oonidata_list_analysis_with_limit_and_offset(client):
    response = client.get(f"{route}?limit=10&offset=10&since={since}&until={until}")

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) == 10
