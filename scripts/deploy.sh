#!/bin/bash
# This script deploys to a testing server

set -e

ENV=$1
SSH_KEY=$2

MACHINE_NAME="measurements"

echo "Using SSH Key $SSH_KEY"

# Another possible approach
# docker login -u $DOCKER_USER -p $DOCKER_PASS
# docker push openobservatory/ooni-measurements:$SHA1

# Create the machine only if it does not exist
(docker-machine status $MACHINE_NAME 2>&1| grep -q "Host does not exist") &&
    docker-machine create --driver generic \
            --generic-ip-address=$DEPLOY_HOST \
            --generic-ssh-key $SSH_KEY \
            $MACHINE_NAME

# Print out the IP of this machine
docker-machine ip measurements

eval "$(docker-machine env measurements)"
docker-compose -f docker-compose.yml -f config/${ENV}.yml build
docker-compose -f docker-compose.yml -f config/${ENV}.yml up -d
