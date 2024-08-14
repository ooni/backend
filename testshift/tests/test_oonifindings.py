from typing import Dict

import httpx

LEGACY_HOST = "https://api.ooni.io"
ACTIVE_HOST = "https://api.dev.ooni.io"


# NOTE: The new API has been updated to include one new response
# field which we do not use and hence default to an empty value.
#
# `creator_account_id`: ""
def check_search_response_keys(legacy_response: Dict, active_response: Dict):
    legacy_keys = list(legacy_response.keys())
    active_keys = list(active_response.keys())

    assert len(active_keys) == len(legacy_keys) + 1

    active_keys.remove("creator_account_id")
    return sorted(active_keys) == sorted(legacy_keys)


def test_oonifindings():
    with httpx.Client(base_url=LEGACY_HOST) as legacy_client, httpx.Client(base_url=ACTIVE_HOST) as active_client:
        legacy_response = legacy_client.get("api/v1/incidents/search?only_mine=false")
        active_response = active_client.get("api/v1/incidents/search?only_mine=false")
        legacy_incidents, active_incidents = legacy_response.json()["incidents"], active_response.json()["incidents"]

        assert len(legacy_incidents) == len(active_incidents)

        for idx in range(len(legacy_incidents)):
            assert check_search_response_keys(legacy_incidents[idx], active_incidents[idx])

        legacy_response = legacy_client.get("api/v1/incidents/search?only_mine=true")
        active_response = active_client.get("api/v1/incidents/search?only_mine=true")
        legacy_incidents, active_incidents = legacy_response.json()["incidents"], active_response.json()["incidents"]

        assert len(legacy_incidents) == len(active_incidents)

        for idx in range(len(legacy_incidents)):
            assert check_search_response_keys(legacy_incidents[idx], active_incidents[idx])

        incident_id = "330022197701"
        legacy_response = legacy_client.get(f"api/v1/incidents/show/{incident_id}")
        active_response = active_client.get(f"api/v1/incidents/show/{incident_id}")

        legacy_incident = legacy_response.json()["incident"]
        active_incident = active_response.json()["incident"]

        assert check_search_response_keys(legacy_incident, active_incident)
