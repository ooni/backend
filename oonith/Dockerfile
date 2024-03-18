FROM golang:1.20.12-bullseye as builder
ARG BRANCH_NAME=master

WORKDIR /build

RUN echo "cloning $BRANCH_NAME" && git clone --branch $BRANCH_NAME https://github.com/ooni/probe-cli

WORKDIR /build/probe-cli

RUN go run ./internal/cmd/buildtool oohelperd build

## Image running on the host
FROM golang:1.20.12-bullseye as runner

WORKDIR /app

COPY --from=builder /build/probe-cli/CLI/oohelperd-* /app
RUN mv oohelperd-* oohelperd

# oohelperd service
EXPOSE 8080

# prometheus metrics
EXPOSE 9091

# Run
CMD ["/app/oohelperd",  "-api-endpoint", "0.0.0.0:8080", "--prometheus-endpoint", "0.0.0.0:9091"]
