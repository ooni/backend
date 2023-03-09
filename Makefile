#
# This file is used to run tests manually and from .github/workflows/test_new_api.yml
#
TESTARGS ?= tests/functional/test_private_explorer.py tests/integ/test_aggregation.py tests/integ/test_citizenlab.py tests/integ/test_integration.py tests/integ/test_integration_auth.py tests/integ/test_prioritization.py tests/integ/test_private_api.py tests/integ/test_probe_services.py tests/unit/test_prio.py tests/integ/test_params_validation.py tests/functional/test_probe_services.py

#tests/integ/test_prioritization_nodb.py
#tests/integ/test_probe_services_nodb.py
#tests/integ/test_integration_auth.py

.state/docker-build: Dockerfile
	docker-compose build --force-rm api
	mkdir -p .state
	touch .state/docker-build

serve: .state/docker-build
	docker-compose up --remove-orphans

build:
	@$(MAKE) .state/docker-build

initdb:
	# Setup database fixtures
	# Fetch fingerprints from github
	# run fastpath to populate the DB
	docker-compose run --rm api python3 -m pytest --setup-only --create-db

tests: .state/docker-build
	docker-compose run --rm api python3 -m pytest $(T) $(TESTARGS)

.PHONY: build initdb tests serve
