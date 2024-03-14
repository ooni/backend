---
title: "OONI Services"
---

OONI API components are broken up into smaller pieces that can be more easily
deployed and managed without worrying too much about the blast radius caused by
the deployment of a larger component.

To this end, we divide the OONI API sub-components into what we call
"services".

Each service (found in the `ooniapi/services` folder) should have a narrowly
defined scope. It's optimal to slice services up depending on how critical they
are (tier0, tier1, tier2) and what kinds of resources they need to access
(databases, object store, specific hosts, etc.).

There is also a `common` folder for all shared logic common to every component.

## Principles

We follow the principles of a building a [12 factor app](https://12factor.net/):

- **[I. Codebase](https://12factor.net/codebase)**, ooni/backend is the monorepo that tracks all the deploys of ooni/backend/ooniapi services
- **[II. Dependencies](https://12factor.net/dependencies)**, each dependency should be tracked in a single source of
  truth, which is the `pyproject.toml` for that service.
- **[III. Config](https://12factor.net/config)**, configuration is defined in a [pydantically](https://pydantic.dev/) typed `Settings`
  object which can be overriden for testing and configured for each environment
  (dev, test, prod).
- **[IV. Backing services](https://12factor.net/backing-services)**, it should be possible to swap out a backing service
  without needing any changes to the codebase. This makes it easy and agile to
  switch our postgresql deployment for a self hosted one or use a managed
  instance when that makes sense. Try to write tests and perform development in
  an environment as close to production as possible.
- **[V. Build, release, run](https://12factor.net/build-release-run)**, the app should be built into a single [docker](https://docs.docker.com/develop/develop-images/dockerfile_best-practices/)
  image that can be provisioned with the right config for that environment.
  Configuration is provisioned in a way that's specific to the enviroment (eg.
  Github Actions, AWS ECS, pytest).
- **[VI. Processes](https://12factor.net/processes)**, the service should define
  a single process call at the end of the Dockerfile which, assuming correct
  configuration, should be stateless.

- **[VII. Port binding](https://12factor.net/port-binding)**, services expose a
  HTTP service running with [uvicorn](https://www.uvicorn.org/). The port it
  binds to can be overriden via an environment variable.

- **[VIII. Concurrency](https://12factor.net/concurrency)**, it should be
  possible to run multiple instances of an OONI API Service to scale
  horizontally, since each concurrent instance doesn't share anything.

- **[IX. Disposability](https://12factor.net/disposability)**, each service
  should shutdown gracefully when they receive a SIGTERM, but also be robust
  against a sudden death, by being a [crash-only
  software](https://en.wikipedia.org/wiki/Crash-only_software).

- **[X. Dev/prod parity](https://12factor.net/dev-prod-parity)**, what we run on
  our machine is as close as possible to what we run in production. This means
  we setup local backing services (postgresql, clickhouse) and try to minimize
  the amount of stuff we mock in order to carry out testing.

- **[XI. Logs](https://12factor.net/logs)**, our logs are written to
  `STDOUT`/`STDERR`. It's up to the orchestration system to figure out what to
  do with them.

- **[XII. Admin processes](https://12factor.net/admin-processes)**, one-off
  admin tasks should be run inside of the docker image for the particular
  revision you are running that task for. For example if you need to run a DB
  migration you should do so from a docker container running the specific
  version of the sofware you want to update. Avoid the temptation to
  [prematurely automate](https://xkcd.com/1319/) one-off tasks that don't need
  to be run so often.

## List of OONI API Services

### Tier0

- `ooniprobe`, (aka `probe_services`), where probes send their measurements and
  get metadata to run experiments;
- `oonirun`, CRUD for editing OONI Run links, but also for probes to get the
  descriptors and run tests (this fact is what makes it tier0);
- `prioritization`, CRUD for editing the priorities of URLs and populating the
  appropriate clickhouse tables so they can be used by probe;
- `fastpath`, responsible for taking measurements blobs sent to `ooniprobe`
  service and storing them in s3;

### Tier1

- `data`, (aka OONI Data Kraken), where Explorer and other clients access the
  observations data and experiment results;
- `findings`, (aka `incidents`) backend for findings pages on explorer;
- `measurements`, backend for aggregation and list measurement endpoints (note
  also probe uses this, so it's maybe on the high end of tier1);
- ``

### Tier2

- `testlists`, for proposing changes to the test-lists and submitting a github PR;

## Developing a service

### Quickstart

For most python services the dev setup looks like this:

- Install [hatch](https://hatch.pypa.io/1.9/install/)

- Run `make run` to start the service locally

- Run `make test` to run the tests

- Run `make docker-build` to build a docker image of that service

### Implementation details

Each python based service should use [hatch](https://hatch.pypa.io) as a python
project manager.

#### Code layout

You can get some help in bootstrapping the project by running:

```
% hatch new ooni<servicename>
<servicename>
├── src
│   └── <servicename>
│       ├── __about__.py
│       └── __init__.py
├── tests
│   └── __init__.py
├── LICENSE.txt
├── README.md
└── pyproject.toml
```

Notice how each service should always start with the `ooni` prefix.

#### Makefile

Each service must include a `Makefile` which defines some common tasks that can
be run with `make`.

Not every task needs to be defined in the Makefile, just the ones which are
expected to be called by other services. To this end the `Makefile` acts an API
of sorts, providing a consistent way to perform certain
[SDLC](https://en.wikipedia.org/wiki/Systems_development_life_cycle) tasks by
hiding the implementation details on how they might happen for that particular
service.

It's recommended you implement the following `Makefile` targets for your
service:

- `test`, runs the full test suite for the service.
- `run`, starts the service locally for use in development. If possible do so with live-reload support.
- `build`, builds a source and binary distribution for the service and places it inside of `dist/`.
- `docker-build`, builds a tagged docker image of the current service revision.
- `docker-push`, pushes the docker image to the correct destination repository.
- `docker-smoketest`, performs a simple smoketest of the built docker image to
  make sure nothing broke in building it. It doesn't have to be an extensive
  test, but just check that the service is able to start and that there is
  nothing obviously broken with the build (eg. broken imports).
- `clean`, perform any necessary cleanup to restore the environment to a clean
  state (i.e. as if you just cloned the repo).
- `imagedefinitions.json`, generate an `imagedefinitions.json` file and place it
  in the `CWD` to be [used by
  codepipeline](https://docs.aws.amazon.com/codepipeline/latest/userguide/file-reference.html).

Be sure to properly define the [.PHONY targets](https://web.mit.edu/gnu/doc/html/make_4.html#SEC31)

Here is a sample template for your makefile:

```
SERVICE_NAME ?= ooniservicename

ECS_CONTAINER_NAME ?= ooniapi-service-$(SERVICE_NAME)
IMAGE_NAME ?= ooni/api-$(SERVICE_NAME)
DATE := $(shell python3 -c "import datetime;print(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d'))")
GIT_FULL_SHA ?= $(shell git rev-parse HEAD)
SHORT_SHA := $(shell echo ${GIT_FULL_SHA} | cut -c1-8)
PKG_VERSION := $(shell hatch version)

BUILD_LABEL := $(DATE)-$(SHORT_SHA)
VERSION_LABEL = v$(PKG_VERSION)
ENV_LABEL ?= latest

print-labels:
	echo "ECS_CONTAINER_NAME=${ECS_CONTAINER_NAME}"
	echo "PKG_VERSION=${PKG_VERSION}"
	echo "BUILD_LABEL=${BUILD_LABEL}"
	echo "VERSION_LABEL=${VERSION_LABEL}"
	echo "ENV_LABEL=${ENV_LABEL}"

init:
	hatch env create

docker-build:
	# We need to use tar -czh to resolve the common dir symlink
	tar -czh . | docker build \
		--build-arg BUILD_LABEL=${BUILD_LABEL} \
		-t ${IMAGE_NAME}:${BUILD_LABEL} \
		-t ${IMAGE_NAME}:${VERSION_LABEL} \
		-t ${IMAGE_NAME}:${ENV_LABEL} \
		-
	echo "built image: ${IMAGE_NAME}:${BUILD_LABEL} (${IMAGE_NAME}:${VERSION_LABEL} ${IMAGE_NAME}:${ENV_LABEL})"

docker-push:
	# We need to use tar -czh to resolve the common dir symlink
	docker push ${IMAGE_NAME}:${BUILD_LABEL}
	docker push ${IMAGE_NAME}:${VERSION_LABEL}
	docker push ${IMAGE_NAME}:${ENV_LABEL}

docker-smoketest:
	./scripts/docker-smoketest.sh ${IMAGE_NAME}:${BUILD_LABEL}

imagedefinitions.json:
	echo '[{"name":"${ECS_CONTAINER_NAME}","imageUri":"${IMAGE_NAME}:${BUILD_LABEL}"}]' > imagedefinitions.json

test:
	hatch run test

test-cov:
	hatch run test-cov

build:
	hatch build

clean:
	hatch clean
	rm -f imagedefinitions.json
	rm -rf build dist *eggs *.egg-info
	rm -rf .venv

run:
	hatch run uvicorn $(SERVICE_NAME).main:app

.PHONY: init test build clean docker print-labels
```

#### Build spec

The service must implement a `buildspec.yml` file that specifies how to
[run the build on code build](https://docs.aws.amazon.com/codebuild/latest/userguide/build-spec-ref.html).

Try to keep the buildspec as simple and non-specific to CodeBuild as possible,
so that we can decide to move to another build pipeline if needed in the future.

Here is a sample `buildspec.yml` file:

```
version: 0.2
env:
  variables:
    OONI_CODE_PATH: ooniapi/services/ooniservicename
    DOCKERHUB_SECRET_ID: oonidevops/dockerhub/access_token

phases:
  install:
    runtime-versions:
      python: 3.11

  pre_build:
    commands:
      - echo "Logging in to dockerhub"
      - DOCKER_SECRET=$(aws secretsmanager get-secret-value --secret-id $DOCKERHUB_SECRET_ID --query SecretString --output text)
      - echo $DOCKER_SECRET | docker login --username ooni --password-stdin

  build:
    commands:
      - export GIT_FULL_SHA=${CODEBUILD_RESOLVED_SOURCE_VERSION}
      - cd $OONI_CODE_PATH
      - make docker-build
      - make docker-smoketest
      - make docker-push
      - make imagedefinitions.json
      - cat imagedefinitions.json | tee ${CODEBUILD_SRC_DIR}/imagedefinitions.json

artifacts:
  files: imagedefinitions.json
```

Please note how the imagedefinitions file is being copied to the
`${CODEBUILD_SRC_DIR}`.
