
CONTAINER_NAME ?= $(SERVICE_NAME)
IMAGE_NAME ?= ooni/$(SERVICE_NAME)
DATE := $(shell python3 -c "import datetime;print(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d'))")
GIT_FULL_SHA ?= $(shell git rev-parse HEAD)
SHORT_SHA := $(shell echo ${GIT_FULL_SHA} | cut -c1-8)
# PKG_VERSION := $(shell hatch version) where to get the PKG version?
PKG_VERSION = 0.1

BUILD_LABEL := $(DATE)-$(SHORT_SHA)
VERSION_LABEL = v$(PKG_VERSION)
ENV_LABEL ?= latest


local_quickdeploy:
	cp fastpath/*.py /usr/local/lib/python3.9/
	systemctl restart fastpath

local_functests:
	# PYTHONPATH=. pytest-3 -s --log-cli-level info $(args)
	pytest -s --log-cli-level info $(args)

local_functests_coverage:
	PYTHONPATH=. pytest-3 -s --cov=fastpath

local_functests_profile:
	austin -o austin.log pytest-3 -s  --log-cli-level info fastpath/tests/test_functional.py::test_windowing_on_real_data
	/usr/share/perl5/Devel/NYTProf/flamegraph.pl austin.log > profile.svg

local_run_devel:
	nice python3 -c'from fastpath.fastpath import main; main()' --devel \
		--start-day=2019-7-20 --end-day=2019-7-21 $(args)

local_monitor_metrics:
	sudo tcpdump -npqi lo udp port 8125 -A -lU | grep --line-buffered fastpat | sed 's/.*fastpath\.//'

builddeb:
	dpkg-buildpackage -us -uc -b

ver := $(shell dpkg-parsechangelog --show-field Version)

beta_deploydeb:
	echo deploying $(ver)
	rsync -avp ../fastpath_$(ver)_all.deb  $(shell cat .betahost):/tmp/
	ssh $(shell cat .betahost) sudo dpkg -i /tmp/fastpath_$(ver)_all.deb

beta_quickdeploy:
	rsync -ap fastpath/*.py $(shell cat .betahost):/usr/lib/python3.7/dist-packages/fastpath/
	rsync -ap fastpath/tests/*.py $(shell cat .betahost):/usr/lib/python3.7/dist-packages/fastpath/tests/

beta_shell:
	ssh $(shell cat .betahost) $(args)

beta_run_devel:
	ssh $(shell cat .betahost) killall fastpath >/dev/null || true
	ssh $(shell cat .betahost) -t fastpath --devel \
		--start-day=2019-7-20 --end-day=2019-7-21 $(args)

beta_run_devel_profile:
	ssh $(shell cat .betahost) killall fastpath || true
	ssh $(shell cat .betahost) -t python3 -m cProfile -o profile \
		/usr/bin/fastpath --devel \
		--start-day=2019-7-20 --end-day=2019-7-21 $(args)
	rsync -ap $(shell cat .betahost):~/profile .

beta_functests:
	# e.g. make beta_quickdeploy beta_functests args='-k foo'
	ssh $(shell cat .betahost) killall fastpath || true
	ssh $(shell cat .betahost) -t PYTHONPATH=. pytest-3 -s  --log-cli-level info \
		/usr/lib/python3.7/dist-packages/fastpath/tests $(args)

beta_monitor_metrics:
	ssh $(shell cat .betahost) \
		"tcpdump -npqi lo udp port 8125 -A -l | grep --line-buffered fastpat | sed 's/.*fastpath\.//'"

docker:
	docker compose --profile default up --build -d

# Runs docker in foreground, useful for checking errors in the image before it runs
docker-fg:
	docker compose --profile default up --build 

# Runs both fastpath and the testing clickhous. 
# Mind the fastpath configuration in fastpath.conf
docker-all: docker-clickhouse
	echo "Waiting for clickhouse..."
	sleep 4 
	docker compose --profile default up --build -d 

# Turns off every service
docker-down:
	docker compose --profile all down 

# If you need to test the fastpath locally you can use this rule to spawn the clickhouse database
# locally and then use `make docker` or `make docker-fg` to start the fastpath container. Ex:
# ```
# make docker-clickhouse
# make docker
# ```
# You can also use `make docker-all` for that purpose
docker-clickhouse:
	docker compose --profile clickhouse up -d

# Use this to login into the fastpath service container, useful for testing
docker-login:
	docker compose exec fastpath bash

# Get logs from the fastpath docker service
docker-logs:
	docker compose logs fastpath -f 

# Get logs for a specified service. Example: 
# `make docker-logs-for args="clickhouse-server"`
docker-logs-for:
	docker compose logs $(args) -f 

# Used for actually building the fastpath docker image
docker-build: 
# We need to use tar -czh to resolve the common dir symlink
	tar -czh . | docker build \
		--build-arg BUILD_LABEL=${BUILD_LABEL} \
		-t ${IMAGE_NAME}:${BUILD_LABEL} \
		-t ${IMAGE_NAME}:${VERSION_LABEL} \
		-t ${IMAGE_NAME}:${ENV_LABEL} \
		-
	echo "built image: ${IMAGE_NAME}:${BUILD_LABEL} (${IMAGE_NAME}:${VERSION_LABEL} ${IMAGE_NAME}:${ENV_LABEL})"