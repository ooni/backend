FROM debian:bullseye
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /app/
ENV DEBIAN_FRONTEND noninteractive

RUN mkdir /scripts
COPY build_runner.sh /scripts
COPY debian/ooni_download_geoip.py /scripts
COPY api.conf.example /scripts
WORKDIR /scripts

# Run runner setup
RUN ./build_runner.sh

# Download geoip files
RUN ./ooni_download_geoip.py

RUN rm -rf /scripts

# The API codebase is mounted under /app using `docker compose` command

# Set our work directory to our app directory
WORKDIR /app/

EXPOSE 8000
