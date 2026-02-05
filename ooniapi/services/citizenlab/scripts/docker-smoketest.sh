#!/bin/bash

set -ex

if [ $# -eq 0 ]; then
  echo "Error: No Docker image name provided."
  echo "Usage: $0 [IMAGE_NAME]"
  exit 1
fi

IMAGE=$1
CONTAINER_NAME=ooniapi-smoketest-$RANDOM
PORT=$((RANDOM % 10001 + 30000))

cleanup() {
    echo "cleaning up"
    docker logs $CONTAINER_NAME
    docker stop $CONTAINER_NAME >/dev/null 2>&1
    docker rm $CONTAINER_NAME >/dev/null 2>&1
}

echo "[+] Running smoketest of ${IMAGE}"
docker run -d --name $CONTAINER_NAME -p $PORT:8000 ${IMAGE}

trap cleanup INT TERM EXIT

sleep 2
response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$PORT/health)
if [ "${response}" -eq 200 ]; then
  echo "Smoke test passed: Received 200 OK from /health endpoint."
else
  echo "Smoke test failed: Did not receive 200 OK from /health endpoint. Received: $response"
  exit 1
fi
