FROM debian:buster
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /app/
ENV DEBIAN_FRONTEND noninteractive

RUN echo 'deb http://deb.debian.org/debian buster-backports main' > /etc/apt/sources.list.d/backports.list

RUN apt-get update
RUN apt-get install --no-install-recommends -y ca-certificates gnupg
RUN echo 'deb http://deb-ci.ooni.org unstable main' \
  > /etc/apt/sources.list.d/ooni.list
RUN apt-key adv --verbose --keyserver hkp://keyserver.ubuntu.com --recv-keys "B5A08F01796E7F521861B449372D1FF271F2DD50"
RUN apt-get update

RUN apt-get install locales -y
RUN locale-gen en_US.UTF-8
RUN apt-get install git --no-install-recommends -y \
      build-essential \
      python3-dev \
      python3-pip \
      gunicorn3 \
      python3-boto3 \
      python3-flasgger \
      python3-flask \
      python3-flask-cors \
      python3-flask-restful \
      python3-flask-security \
      python3-lz4 \
      python3-psycopg2 \
      python3-pytest \
      python3-setuptools \
      python3-sqlalchemy \
      python3-sqlalchemy-utils \
      python3-statsd \
      python3-systemd \
      python3-jwt \
      python3-filelock \
      python3-git \
      python3-ujson
RUN apt-get autoremove -y
RUN apt-get clean
RUN rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
RUN pip3 install py-lz4framed pytest

RUN mkdir /etc/ooni/

# Copy the directory into the container
COPY newapi /app/

COPY newapi/api.conf.example /etc/ooni/api.conf

# Set our work directory to our app directory
WORKDIR /app/
