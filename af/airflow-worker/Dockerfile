# BUILD: docker build --rm -t ooni/airflow-worker .

FROM ooni/airflow

MAINTAINER Leonid Evdokimov <leon@darkk.net.ru>

USER root

COPY af-docker /etc/sudoers.d/
COPY docker-trampoline /usr/local/bin/

RUN set -ex \
    && apt-get update \
    && apt-get install -y curl apt-transport-https ca-certificates \
    && curl -fsSL https://yum.dockerproject.org/gpg | apt-key add - \
    && apt-key fingerprint 58118E89F3A912897C070ADBF76221572C52609D | grep '^ *Key fingerprint = 5811 8E89 F3A9 1289 7C07  0ADB F762 2157 2C52 609D$' \
    && :

COPY docker.list /etc/apt/sources.list.d/

RUN set -ex \
    && apt-get update \
    && apt-get install -y sudo docker-engine \
    && apt-get clean \
    && chmod 440 /etc/sudoers.d/af-docker \
    && rm -rf \
        /var/lib/apt/lists/* \
        /tmp/* \
        /var/tmp/* \
    && :

# switch it back
USER airflow
