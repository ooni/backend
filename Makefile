APP_ENV := "development"

default:
	@echo "ERR: Did not specify a command"
	@exit 1

.state/docker-build:
	docker-compose build -f docker-compose.yml -f config/$(APP_ENV).yml
	
	# Set the state
	mkdir -p .state
	touch .state/docker-build

clean:
	rm -rf measurements/static/dist

build:
	docker-compose build -f docker-compose.yml -f config/$(APP_ENV).yml
	
	# Set the state
	mkdir -p .state
	touch .state/docker-build

serve: .state/docker-build
	docker-compose up -f docker-compose.yml -f config/$(APP_ENV).yml

debug: .state/docker-build
	docker-compose run --service-ports web

test:
	echo "Running tests"
	#docker-compose run web python -m measurements updatefiles --file dev/fixtures.txt

dropdb:
	docker-compose run web psql -h db -d postgres -U postgres -c "DROP DATABASE IF EXISTS measurements"
	docker-compose run web psql -h db -d postgres -U postgres -c "CREATE DATABASE measurements ENCODING 'UTF8'"

.PHONY: default build serve clean debug dropdb test
