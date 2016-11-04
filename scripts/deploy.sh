#!/bin/bash
# This script deploys to a testing server

set -e

ENV=$1
SSH_KEY=$2

echo "Using SSH Key $SSH_KEY"

# Another possible approach
# docker login -u $DOCKER_USER -p $DOCKER_PASS
# docker push openobservatory/ooni-measurements:$SHA1

docker-machine create --driver generic \
            --generic-ip-address=$DEPLOY_HOST \
            --generic-ssh-key $SSH_KEY \
            measurements

# Print out the IP of this machine
docker-machine ip measurements

eval "$(docker-machine env measurements)"
docker-compose -f docker-compose.yml -f config/${ENV}.yml build
docker-compose -f docker-compose.yml -f config/${ENV}.yml up -d
