# Builds a containerized miniooni (github.com/ooni/probe-cli/v3/internal/cmd/miniooni)
# pinned to a configurable ref, for use as the "real client" in the ooniapi
# e2e test harness.
#
# PROBE_CLI_REPO/PROBE_CLI_REF let CI build against multiple probe-cli
# versions (see the test matrix in .github/workflows/test_e2e_miniooni.yml),
# which is the "test against a matrix of client versions" idea from
# https://github.com/ooni/backend/pull/1145.
#
# The multi-stage Rust+Go build below follows the pattern from
# https://github.com/ooni/probe-cli/pull/1782 (Dockerfile.miniooni, not yet
# merged at the time of writing, authored by the same person - aagbsn - who
# opened backend#1145). We don't depend on that PR directly (building against
# an unmerged, mutable branch would be fragile); the `make userauth` /
# buildtool machinery it packages already exists on probe-cli's master, so
# this Dockerfile reimplements the same steps against whatever
# PROBE_CLI_REF is checked out. Once #1782 merges, this could be simplified
# to just `COPY --from=<probe-cli checkout> Dockerfile.miniooni` instead.
#
# Building the real userauth staticlib (a Rust crate, ooniprobe-ffi, vendored
# via ooni/probe-cli's own buildtool) gives us the actual anonymous-credentials
# implementation rather than the pure-Go stub CGO_ENABLED=0 would silently
# fall back to. We still don't configure ANONC_MANIFEST_BUCKET/etc in
# docker-compose.yml (see README's "Known gaps"), so probe-cli's own
# graceful fallback to uncredentialed submission still applies either way -
# but building the real thing means a future MinIO-backed credentialed-path
# test doesn't also require rewriting this Dockerfile.

FROM rust:1.88-bookworm AS ruststage
FROM golang:1.26-bookworm AS builder

COPY --from=ruststage /usr/local/cargo /usr/local/cargo
COPY --from=ruststage /usr/local/rustup /usr/local/rustup
ENV PATH="/usr/local/cargo/bin:${PATH}"
RUN rustup default stable
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    cmake \
    clang \
    libclang-dev \
    pkg-config \
    git \
    && rm -rf /var/lib/apt/lists/*

ARG PROBE_CLI_REPO=https://github.com/ooni/probe-cli.git
ARG PROBE_CLI_REF=master

WORKDIR /app

# Shallow-clone the requested ref rather than vendoring probe-cli into this
# repo, so bumping the version tested is a one-line change in CI.
RUN git clone --depth 1 --branch "${PROBE_CLI_REF}" "${PROBE_CLI_REPO}" . \
    || (git clone "${PROBE_CLI_REPO}" . && git checkout "${PROBE_CLI_REF}")

# Builds internal/userauth's staticlib from source (a Rust crate pulled in by
# probe-cli's own ./internal/cmd/buildtool via `make userauth`) rather than
# downloading a prebuilt bundle, so this doesn't depend on prebuilt-artifact
# availability for whatever ref/architecture we're testing.
ENV USERAUTH_FROM_SOURCE=1
RUN make userauth

RUN go build -trimpath -ldflags '-s -w' -o /out/miniooni ./internal/cmd/miniooni

# --- runtime image -----------------------------------------------------
FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /out/miniooni /usr/local/bin/miniooni

# miniooni writes state under $HOME/.miniooni; give it a writable home.
ENV HOME=/home/miniooni
RUN useradd -m -d /home/miniooni -s /usr/sbin/nologin miniooni
USER miniooni
WORKDIR /home/miniooni

ENTRYPOINT ["/usr/local/bin/miniooni"]
