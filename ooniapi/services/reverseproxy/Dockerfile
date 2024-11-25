FROM nginx:1.27.1
ENV TARGET_URL="https://backend-hel.ooni.org"
ENV CLICKHOUSE_STREAM_TARGET="clickhouse1.prod.ooni.io:9000"

COPY templates/backend-proxy.conf.template /etc/nginx/templates/
COPY templates/clickhouse-proxy.conf.stream-template /etc/nginx/templates/