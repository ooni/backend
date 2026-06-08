SERVICE_NAME ?= reuploader

CONTAINER_NAME ?= $(SERVICE_NAME)
IMAGE_NAME ?= ooni/$(SERVICE_NAME)
DATE := $(shell python3 -c "import datetime;print(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d'))")
GIT_FULL_SHA ?= $(shell git rev-parse HEAD)
SHORT_SHA := $(shell echo ${GIT_FULL_SHA} | cut -c1-8)
# this magic line will parse the version from the changelog file
PKG_VERSION = $(shell grep -m1 '^fastpath (' debian/changelog | sed -E 's/^fastpath \(([^)]+)\).*/\1/')


BUILD_LABEL := $(DATE)-$(SHORT_SHA)
ENV_LABEL ?= latest

# Used for building the reuploader docker image
docker-build:
	docker build \
		--build-arg BUILD_LABEL=${BUILD_LABEL} \
		-t ${IMAGE_NAME}:${BUILD_LABEL} \
		-t ${IMAGE_NAME}:${ENV_LABEL} \
		.
	echo "built image: ${IMAGE_NAME}:${BUILD_LABEL} (${IMAGE_NAME}:${ENV_LABEL})"

docker-push:
	docker push ${IMAGE_NAME}:${BUILD_LABEL}
	docker push ${IMAGE_NAME}:${ENV_LABEL}

imagedefinitions.json:
	echo '[{"name":"${ECS_CONTAINER_NAME}","imageUri":"${IMAGE_NAME}:${BUILD_LABEL}"}]' > imagedefinitions.json

# Used by other ECS services but not implemented yet
docker-smoketest:
	echo "Smoketest not yet implemented"
