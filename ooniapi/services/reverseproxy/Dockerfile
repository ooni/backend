FROM nginx:1.27.1
ENV TARGET_URL="https://backend-hel.ooni.org"
ENV CLICKHOUSE_STREAM_TARGET="clickhouse1.prod.ooni.io:9000"

# Install prometheus exporter
RUN mkdir nginx-prom-exporter
RUN curl -L -o nginx-prom-exporter/prom-exporter.tar.gz https://github.com/nginx/nginx-prometheus-exporter/releases/download/v1.4.1/nginx-prometheus-exporter_1.4.1_linux_386.tar.gz
RUN tar -xzvf ./nginx-prom-exporter/prom-exporter.tar.gz -C ./nginx-prom-exporter
RUN mv ./nginx-prom-exporter/nginx-prometheus-exporter /bin
RUN rm -r nginx-prom-exporter

COPY templates/backend-proxy.conf.template /etc/nginx/templates/
