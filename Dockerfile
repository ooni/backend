FROM debian:bullseye
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /app/
ENV DEBIAN_FRONTEND noninteractive

# Copy code and conf into the container
COPY newapi /app/
COPY newapi/api.conf.example /etc/ooni/api.conf
# Set our work directory to our app directory
WORKDIR /app/
# Run runner setup
RUN ./build_runner.sh
