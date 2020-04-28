# Build: run ooni-sysadmin.git/scripts/docker-build from this directory

FROM python:3.7-slim
ENV PYTHONUNBUFFERED 1

ENV PYTHONPATH /app/

# Setup the locales in the Dockerfile
RUN set -x \
    && apt-get update \
    && apt-get install locales -y \
    && locale-gen en_US.UTF-8

# Install measurements Dependencies
RUN set -x \
    && apt-get update \
    && apt-get install git postgresql-client bzip2 gcc g++ make \
        libpq-dev libffi-dev --no-install-recommends -y \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

COPY requirements /tmp/requirements

# Install Python dependencies
RUN set -x \
    && pip install -U pip setuptools \
    && pip install -r /tmp/requirements/tests.txt \
    && pip install -r /tmp/requirements/deploy.txt \
                   -r /tmp/requirements/main.txt

# Copy the directory into the container
COPY . /app/

# Set our work directory to our app directory
WORKDIR /app/
