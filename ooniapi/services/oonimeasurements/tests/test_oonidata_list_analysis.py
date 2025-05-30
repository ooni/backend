import pytest

route = "api/v1/analysis"
since = "2024-11-01"
until = "2024-11-02"

def test_oonidata_list_analysis(client):
    response = client.get(route)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) == 0


def test_oonidata_list_analysis_with_since_and_until(client, params_since_and_until_with_two_days):
    response = client.get(route, params=params_since_and_until_with_two_days)

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
def test_oonidata_list_analysis_with_filters(client, filter_param, filter_value, params_since_and_until_with_two_days):
    params = params_since_and_until_with_two_days
    params[filter_param] = filter_value

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for result in json["results"]:
        assert result[filter_param] == filter_value, result


def test_oonidata_list_analysis_filtering_by_probe_asn_as_a_string_with_since_and_until(client, params_since_and_until_with_two_days):
    params = params_since_and_until_with_two_days
    probe_asn = 45758
    params["probe_asn"] =  "AS" + str(probe_asn)

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for result in json["results"]:
        assert result["probe_asn"] == probe_asn, result

def test_oonidata_list_analysis_order_default(client, params_since_and_until_with_two_days):
    response = client.get(route, params=params_since_and_until_with_two_days)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for i in range(1, len(json["results"])):
        assert "measurement_start_time" in json["results"][i], json["results"][i]
        previous_date = json["results"][i - 1]["measurement_start_time"]
        current_date = json["results"][i]["measurement_start_time"]
        assert previous_date >= current_date, f"The dates are not ordered: {previous_date} < {current_date}"


def test_oonidata_list_analysis_order_asc(client, params_since_and_until_with_two_days):
    params = params_since_and_until_with_two_days
    params["order"] = "ASC"

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for i in range(1, len(json["results"])):
        assert "measurement_start_time" in json["results"][i], json["results"][i]
        previous_date = json["results"][i - 1]["measurement_start_time"]
        current_date = json["results"][i]["measurement_start_time"]
        assert previous_date <= current_date, f"The dates are not ordered: {previous_date} > {current_date}"


@pytest.mark.parametrize(
    "field, order",
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
def test_oonidata_list_analysis_order_by_field(client, field, order, params_since_and_until_with_two_days):
    params = params_since_and_until_with_two_days
    params['order_by'] = field
    params['order'] = order

    response = client.get(route, params=params)
    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for i in range(1, len(json["results"])):
        assert field in json["results"][i], json["results"][i]
        previous = json["results"][i - 1][field]
        current = json["results"][i][field]
        if order == "asc":
            assert previous <= current, f"The {field} values are not ordered in ascending order: {previous} > {current}"
        else:
            assert previous >= current, f"The {field} values are not ordered in descending order: {previous} < {current}"


def test_oonidata_list_analysis_limit_by_default(client, params_since_and_until_with_two_days):
    response = client.get(route, params=params_since_and_until_with_two_days)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) == 100

def test_oonidata_list_analysis_with_limit_and_offset(client, params_since_and_until_with_two_days):
    params = params_since_and_until_with_two_days
    params["limit"] = 10

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) == 10
