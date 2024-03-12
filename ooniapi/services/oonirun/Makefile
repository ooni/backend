.PHONY: init test build clean docker

IMAGE_NAME ?= ooni/api-oonirun
DATE := $(shell python3 -c "import datetime;print(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d'))")
GIT_FULL_SHA ?= $(shell git rev-parse HEAD)
SHORT_SHA := $(shell echo ${GIT_FULL_SHA} | cut -c1-8)
PKG_VERSION := $(shell cat pyproject.toml | grep -e 'version\s*=' | cut -d '"' -f2)

BUILD_LABEL := $(DATE)-$(SHORT_SHA)
VERSION_LABEL = v$(PKG_VERSION)

check:
	echo "${GIT_FULL_SHA}"
	echo "${BUILD_LABEL}"
	echo "${PKG_VERSION}"

init:
	hatch env create

docker-build:
	# We need to use tar -czh to resolve the common dir symlink
	tar -czh . | docker build \
		--build-arg BUILD_LABEL=${BUILD_LABEL} \
		-t ${IMAGE_NAME}:${BUILD_LABEL} \
		-t ${IMAGE_NAME}:${VERSION_LABEL} \
		-t ${IMAGE_NAME}:latest \
		-

docker-push:
	# We need to use tar -czh to resolve the common dir symlink
	docker push ${IMAGE_NAME}:${BUILD_LABEL}
	docker push ${IMAGE_NAME}:${VERSION_LABEL}
	docker push ${IMAGE_NAME}:latest

imagedefinitions.json:
	echo '[{"name":"${IMAGE_NAME}","imageUri":"${IMAGE_NAME}:${BUILD_LABEL}"}]' > imagedefinitions.json

test:
	hatch run test

test-cov:
	hatch run test-cov

build:
	hatch build

clean:
	hatch clean
	rm imagedefinitions.json
	rm -rf build dist *eggs *.egg-info
	rm -rf .venv

run:
	hatch run uvicorn oonirun.main:app
