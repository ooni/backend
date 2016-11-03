default:
	@echo "ERR: Did not specify a command"
	@exit 1

.state/docker-build:
	docker-compose build
	
	# Set the state
	mkdir -p .state
	touch .state/docker-build

clean:
	rm -rf measurements/static/dist

build:
	docker-compose build
	
	# Set the state
	mkdir -p .state
	touch .state/docker-build

serve: .state/docker-build
	docker-compose up

debug: .state/docker-build
	docker-compose run --service-ports web

.PHONY: default build serve clean debug
