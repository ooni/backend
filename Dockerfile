
FROM debian:buster
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /app/
COPY build_docker.sh /tmp/
RUN /tmp/build_docker.sh

# Copy the directory into the container
COPY newapi /app/

COPY newapi/debian/etc/ooni/api.conf /etc/ooni/api.conf

# Set our work directory to our app directory
WORKDIR /app/
