FROM nginx:1.27.1
ENV TARGET_URL="https://backend-hel.ooni.org"
ENV CLICKHOUSE_STREAM_TARGET="clickhouse1.prod.ooni.io:9000"

COPY templates/backend-proxy.conf.template /etc/nginx/templates/

# Install prometheus exporter
RUN mkdir nginx-prom-exporter
RUN curl -L -o nginx-prom-exporter/prom-exporter.tar.gz https://github.com/nginx/nginx-prometheus-exporter/releases/download/v1.4.1/nginx-prometheus-exporter_1.4.1_linux_386.tar.gz
RUN tar -xzvf ./nginx-prom-exporter/prom-exporter.tar.gz -C ./nginx-prom-exporter
RUN mv ./nginx-prom-exporter/nginx-prometheus-exporter /bin
RUN rm -r nginx-prom-exporter

# Install supervisord to run both processes in the same docker
# See: https://docs.docker.com/engine/containers/multi-service_container/#use-a-process-manager
RUN apt-get update && apt-get install -y supervisor
RUN mkdir -p /var/log/supervisor
COPY config/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
RUN touch /var/run/supervisord.pid


# We need this script because overriding the CMD was preventing
# nginx from running the templates setup, see:
# https://github.com/nginxinc/docker-nginx/blob/b430becb8f0f6b8d69e68cc73a82ea2873c38639/entrypoint/docker-entrypoint.sh#L12
COPY scripts/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x docker-entrypoint.sh

CMD [ "/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf", "-n"]