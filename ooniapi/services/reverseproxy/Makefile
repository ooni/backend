SERVICE_NAME ?= reverseproxy
PKG_VERSION = 1.0.0

ECS_CONTAINER_NAME ?= ooniapi-service-$(SERVICE_NAME)
IMAGE_NAME ?= ooni/api-$(SERVICE_NAME)
DATE := $(shell python3 -c "import datetime;print(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d'))")
GIT_FULL_SHA ?= $(shell git rev-parse HEAD)
SHORT_SHA := $(shell echo ${GIT_FULL_SHA} | cut -c1-8)

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
	echo "noop"

docker-build:
	docker build \
		--build-arg BUILD_LABEL=${BUILD_LABEL} \
		-t ${IMAGE_NAME}:${BUILD_LABEL} \
		-t ${IMAGE_NAME}:${VERSION_LABEL} \
		-t ${IMAGE_NAME}:${ENV_LABEL} \
		.
	echo "built image: ${IMAGE_NAME}:${BUILD_LABEL} (${IMAGE_NAME}:${VERSION_LABEL} ${IMAGE_NAME}:${ENV_LABEL})"

docker-push:
	docker push ${IMAGE_NAME}:${BUILD_LABEL}
	docker push ${IMAGE_NAME}:${VERSION_LABEL}
	docker push ${IMAGE_NAME}:${ENV_LABEL}

docker-smoketest:
	./scripts/docker-smoketest.sh ${IMAGE_NAME}:${BUILD_LABEL}

imagedefinitions.json:
	echo '[{"name":"${ECS_CONTAINER_NAME}","imageUri":"${IMAGE_NAME}:${BUILD_LABEL}"}]' > imagedefinitions.json

test:
	echo "noop"

test-cov:
	echo "noop"

build:
	docker build .

clean:
	hatch clean
	rm -f imagedefinitions.json
	rm -rf build dist *eggs *.egg-info
	rm -rf .venv

run:
	./run.sh

.PHONY: init test build clean docker
