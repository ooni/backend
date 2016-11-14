APP_ENV = development

default:
	@echo "ERR: Did not specify a command"
	@exit 1

.state/docker-build-$(APP_ENV):
	docker-compose -f docker-compose.yml -f config/$(APP_ENV).yml build
	#
	# Set the state
	mkdir -p .state
	touch .state/docker-build-$(APP_ENV)

clean:
	rm -rf measurements/static/dist

build:
	docker-compose -f docker-compose.yml -f config/$(APP_ENV).yml build
	#
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
	docker-compose run web python -m measurements updatefiles --file dev/fixtures.txt --no-check

test-unit:
	echo "Running unittests"
	docker-compose run web pytest -m unit

test-functional:
	echo "Running functional tests"
	docker-compose run web pytest -m functional

test: APP_ENV=testing
test: test-unit dropdb .state/docker-build-$(APP_ENV) load-fixtures test-functional

dropdb:
	docker-compose run db psql -h db -d postgres -U postgres -c "DROP DATABASE IF EXISTS measurements"

develop: APP_ENV=development
develop: .state/docker-build-$(APP_ENV) serve

develop-rebuild: APP_ENV=development
develop-rebuild: build serve

staging: APP_ENV=staging
staging: serve-d

.PHONY: default build serve clean debug develop develop-rebuild dropdb test
