APP_ENV = development
DOCKER_EXTRA =
DOCKER_COMPOSE = docker-compose -f docker-compose.yml -f config/$(APP_ENV).yml  $(DOCKER_EXTRA)

default:
	@echo "ERR: Did not specify a command"
	@exit 1

.state/docker-build-$(APP_ENV):
	$(DOCKER_COMPOSE) build
	#
	# Set the state
	mkdir -p .state
	touch .state/docker-build-$(APP_ENV)

clean:
	rm -rf measurements/static/dist

build:
	$(DOCKER_COMPOSE) build
	#
	# Set the state
	mkdir -p .state
	touch .state/docker-build-$(APP_ENV)

serve-d: .state/docker-build-$(APP_ENV)
	$(DOCKER_COMPOSE) up -d

serve: .state/docker-build-$(APP_ENV)
	$(DOCKER_COMPOSE) up

debug: .state/docker-build-$(APP_ENV)
	$(DOCKER_COMPOSE) run --service-ports web python -m measurements shell

load-fixtures:
	$(DOCKER_COMPOSE) run web python -m measurements updatefiles --file dev/fixtures.txt --no-check

test-unit:
	echo "Running unittests"
	$(DOCKER_COMPOSE) run web pytest -m unit

test-functional:
	echo "Running functional tests"
	$(DOCKER_COMPOSE) run web pytest -m functional

test: APP_ENV=testing
test: test-unit .state/docker-build-$(APP_ENV) test-functional

dropdb:
	$(DOCKER_COMPOSE) run db psql -h db -d postgres -U postgres -c "DROP DATABASE IF EXISTS measurements"

develop: APP_ENV=development
develop: .state/docker-build-$(APP_ENV) serve

develop-rebuild: APP_ENV=development
develop-rebuild: build serve

staging: APP_ENV=staging
staging: serve-d

.PHONY: default build serve clean debug develop develop-rebuild dropdb test
