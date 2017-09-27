APP_ENV = development
VERSION = $(shell cat package.json \
  | grep version \
  | head -1 \
  | awk -F: '{ print $$2 }' \
  | sed 's/[",]//g' \
  | tr -d '[[:space:]]')
APP_NAME = openobservatory/ooni-api:$(VERSION)

PYTHON_WITH_ENV = PYTHONPATH=$(shell pwd) APP_ENV=$(APP_ENV) python

default:
	@echo "ERR: Did not specify a command"
	@exit 1

clean:
	rm -rf measurements/static/dist

build:
	docker build -t $(APP_NAME) .

dev:
	$(PYTHON_WITH_ENV) -m measurements run -p 3000 --reload

# XXX remove these if devtool backward compatibility does not matter
serve: dev
develop: dev
develop-rebuild: dev

shell:
	$(PYTHON_WITH_ENV) -m measurements shell

create-tables:
	$(PYTHON_WITH_ENV) -m measurements create_tables

load-fixtures:
	$(PYTHON_WITH_ENV) -m measurements updatefiles --file dev/fixtures.txt --no-check

test-unit:
	$(PYTHON_WITH_ENV) -m coverage run -m pytest --strict -m unit

test-functional:
	$(PYTHON_WITH_ENV) -m coverage run -m pytest --strict -m functional

test: test-unit test-functional
	$(PYTHON_WITH_ENV) -m coverage report -m

dropdb:
	psql -h db -d postgres -U postgres -c "DROP DATABASE IF EXISTS measurements"

push: build
	echo "Pushing $(APP_NAME) to docker hub"
	docker push openobservatory/ooni-measurements:$(VERSION)

.PHONY: default dev build clean shell \
		test test-unit test-functional \
		create-tables dropdb \
		develop develop-rebuild serve
