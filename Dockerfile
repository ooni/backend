FROM python:3.5.2-slim
ENV PYTHONUNBUFFERED 1

ENV PYTHONPATH /app/

# Setup the locales in the Dockerfile
RUN set -x \
    && apt-get update \
    && apt-get install locales -y \
    && locale-gen en_US.UTF-8

# Install measurements Dependencies
# XXX verify fingerprint for nodesource bash script
RUN set -x \
    && apt-get update \
    && apt-get install curl -y \
    && curl -sL https://deb.nodesource.com/setup_6.x | bash - \
    && curl -sS https://dl.yarnpkg.com/debian/pubkey.gpg | apt-key add - \
    && echo "deb https://dl.yarnpkg.com/debian/ stable main" | tee /etc/apt/sources.list.d/yarn.list \
    && apt-get update \
    && apt-get install git postgresql-client bzip2 gcc g++ make \
        libpq-dev libffi-dev nodejs yarn --no-install-recommends -y \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

COPY package.json /tmp/package.json
COPY yarn.lock /tmp/yarn.lock

# Install NPM dependencies
RUN set -x \
    && npm install -g gulp-cli

RUN set -x \
    && cd /tmp \
    && yarn install --loglevel http \
    && mkdir /app \
    && cp -a /tmp/node_modules /app/

COPY requirements /tmp/requirements

# Install Python dependencies
RUN set -x \
    && pip install -U pip setuptools \
    && pip install -r /tmp/requirements/tests.txt \
    && pip install -r /tmp/requirements/deploy.txt \
                   -r /tmp/requirements/main.txt

# Copy the directory into the container
COPY . /app/

RUN set -x \
    && cd /app/ \
    && gulp dist

# Set our work directory to our app directory
WORKDIR /app/
