
FROM debian:bullseye
ENV PYTHONUNBUFFERED 1
# ENV PYTHONPATH /opt/detector
ENV DEBIAN_FRONTEND noninteractive

RUN mkdir /scripts
COPY build_runner.sh /scripts
# COPY debian/ooni_download_geoip.py /scripts
# COPY api.conf.example /scripts
WORKDIR /scripts

# Run runner setup
RUN ./build_runner.sh

# # Download geoip files
# RUN ./ooni_download_geoip.py

RUN rm -rf /scripts

WORKDIR /opt/detector
