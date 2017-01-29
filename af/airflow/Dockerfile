# BUILD: docker build --rm -t ooni/airflow .

FROM puckel/docker-airflow@sha256:9544f52a7488594a3fbbac991171e1add29e2582e2875dc5dd6420bdfdfbc7a6

MAINTAINER Leonid Evdokimov <leon@darkk.net.ru>

USER root

RUN set -ex \
    && curl --location -o /var/tmp/dumb-init_1.2.0_amd64.deb https://github.com/Yelp/dumb-init/releases/download/v1.2.0/dumb-init_1.2.0_amd64.deb \
    && echo '9af7440986893c904f24c086c50846ddc5a0f24864f5566b747b8f1a17f7fd52  /var/tmp/dumb-init_1.2.0_amd64.deb' >/var/tmp/SHA256SUM \
    && sha256sum --strict --check /var/tmp/SHA256SUM \
    && dpkg -i /var/tmp/dumb-init_1.2.0_amd64.deb \
    && rm -f /var/tmp/dumb-init_1.2.0_amd64.deb \
    && :

# TODO: buildDeps may be futher cleaned up by `apt-get -y autoremove`

USER airflow

# One can't enforce ulimit on PID=1
ENTRYPOINT ["/usr/bin/dumb-init", "-v", "/entrypoint.sh"]
