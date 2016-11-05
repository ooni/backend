APP_ENV = development

default:
	@echo "ERR: Did not specify a command"
	@exit 1

.state/docker-build:
	docker-compose -f docker-compose.yml -f config/$(APP_ENV).yml build
	
	# Set the state
	mkdir -p .state
	touch .state/docker-build-$(APP_ENV)

clean:
	rm -rf measurements/static/dist

build:
	docker-compose -f docker-compose.yml -f config/$(APP_ENV).yml build
	
	# Set the state
	mkdir -p .state
	touch .state/docker-build-$(APP_ENV)

serve-d: .state/docker-build-$(APP_ENV)
	docker-compose -f docker-compose.yml -f config/$(APP_ENV).yml up -d

serve: .state/docker-build-$(APP_ENV)
	docker-compose -f docker-compose.yml -f config/$(APP_ENV).yml up

debug: .state/docker-build-$(APP_ENV)
	docker-compose run --service-ports web python -m measurements shell

load-fixtures:
	docker-compose run web python -m measurements updatefiles --file dev/fixtures.txt

test-unit:
	echo "Running unittests"

test-functional:
	echo "Running functional tests"

test-e2e:
	echo "Running end to end tests"

test: APP_ENV=testing
test: build test-unit test-functional dropdb load-fixtures test-e2e

dropdb:
	docker-compose run web psql -h db -d postgres -U postgres -c "DROP DATABASE IF EXISTS measurements"
	docker-compose run web psql -h db -d postgres -U postgres -c "CREATE DATABASE measurements ENCODING 'UTF8'"

develop: APP_ENV=development
develop: build serve

staging: APP_ENV=staging
staging: serve-d

.PHONY: default build serve clean debug dropdb test
