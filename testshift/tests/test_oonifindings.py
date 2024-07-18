from typing import Dict

import httpx

LEGACY_HOST = "https://backend-hel.ooni.org"
ACTIVE_HOST = "https://api.dev.ooni.io"


def check_response_keys(legacy_response: Dict, active_response: Dict):
    return legacy_response.keys() == active_response.keys()


def test_oonifindings():
    with httpx.Client(base_url=LEGACY_HOST) as legacy_client, httpx.Client(base_url=ACTIVE_HOST) as active_client:
        legacy_response = legacy_client.get("api/v1/incidents/search?only_mine=false")
        active_response = active_client.get("api/v1/incidents/search?only_mine=false")
        legacy_incidents, active_incidents = legacy_response.json(), active_response.json()
        assert len(legacy_incidents) == len(active_incidents)
        for idx in range(len(legacy_incidents)):
            assert check_response_keys(legacy_incidents[idx], active_incidents[idx])

        legacy_response = legacy_client.get("api/v1/incidents/search?only_mine=true")
        active_response = active_client.get("api/v1/incidents/search?only_mine=true")
        legacy_incidents, active_incidents = legacy_response.json(), active_response.json()
        assert len(legacy_incidents) == len(active_incidents)
        for idx in range(len(legacy_incidents)):
            assert check_response_keys(legacy_incidents[idx], active_incidents[idx])
        
        sample_incident = ""
        legacy_response = legacy_client.get(f"api/v1/incidents/show/{sample_incident}")
        active_response = legacy_client.get(f"api/v1/incidents/show/{sample_incident}")
        assert check_response_keys(legacy_response.json(), active_response.json())
