FROM python:3.5.2-slim
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
    && apt-get install curl -y \
    && curl -sL https://deb.nodesource.com/setup_6.x | bash - \
    && apt-get install git postgresql-client bzip2 gcc g++ make libpq-dev libffi-dev nodejs --no-install-recommends -y \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

COPY package.json /tmp/package.json

# Install NPM dependencies
RUN set -x \
    && npm install -g gulp-cli \
    && cd /tmp \
    && npm install \
    && mkdir /app \
    && cp -a /tmp/node_modules /app/

COPY requirements /tmp/requirements

# Install Python dependencies
RUN set -x \
    && pip install -U pip setuptools \
    && pip install -r /tmp/requirements/dev.txt \
                   -r /tmp/requirements/tests.txt \
    && pip install -r /tmp/requirements/deploy.txt \
                   -r /tmp/requirements/main.txt

# Copy the directory into the container
COPY . /app/

# Set our work directory to our app directory
WORKDIR /app/
