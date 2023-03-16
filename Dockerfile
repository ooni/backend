FROM debian:bullseye
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /app/
ENV DEBIAN_FRONTEND noninteractive

RUN mkdir /scripts
COPY newapi/build_runner.sh /scripts
COPY newapi/debian/ooni_download_geoip.py /scripts
COPY newapi/api.conf.example /scripts
WORKDIR /scripts

# Run runner setup
RUN ./build_runner.sh

# Download geoip files
RUN ./ooni_download_geoip.py

RUN rm -rf /scripts

# Copy code and conf into the container
COPY newapi /app/
# Set our work directory to our app directory
WORKDIR /app/

EXPOSE 8000
