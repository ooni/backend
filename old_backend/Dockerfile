# Build: run ooni-sysadmin.git/scripts/docker-build from this directory

FROM python:2.7.15-slim
ENV PYTHONUNBUFFERED 1

ENV PYTHONPATH /app/

# Setup the locales in the Dockerfile
RUN set -x \
    && apt-get update \
    && apt-get install locales -y \
    && locale-gen en_US.UTF-8

RUN set -x \
    && apt-get install gcc g++ make python-dev -y

COPY requirements.txt /tmp/requirements.txt

# Install Python dependencies
RUN set -x \
    && pip install -U pip setuptools \
    && pip install -r /tmp/requirements.txt

# Install tor

RUN set -x \
    && apt-get install tor -y

# Copy the directory into the container
COPY . /app/

# Set our work directory to our app directory
WORKDIR /app/
