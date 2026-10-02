# Builds a containerized miniooni (github.com/ooni/probe-cli/v3/internal/cmd/miniooni)
# pinned to a configurable ref, for use as the "real client" in the ooniapi
# e2e test harness.
#
# PROBE_CLI_REPO/PROBE_CLI_REF let CI build against multiple probe-cli
# versions (see the test matrix in .github/workflows/test_e2e_miniooni.yml),
# which is the "test against a matrix of client versions" idea from
# https://github.com/ooni/backend/pull/1145.
#
# `make userauth` (probe-cli's own target, see its Makefile and
# ./internal/cmd/buildtool) fetches the internal/userauth staticlib - a
# Rust crate (ooniprobe-ffi) that gives miniooni the real anonymous-
# credentials implementation rather than the pure-Go stub CGO_ENABLED=0
# would silently fall back to. It can get that staticlib two ways, chosen
# here via the USERAUTH_MODE build arg:
#
#   USERAUTH_MODE=source (the default)
#     Builds the staticlib from source with USERAUTH_FROM_SOURCE=1. This is
#     the trusted path - we don't want this harness's notion of "miniooni
#     works" to depend on trusting a prebuilt binary blob pulled from
#     GitHub Releases. Needs a Rust toolchain (see the ruststage/
#     builder-source stages below).
#
#   USERAUTH_MODE=prebuilt
#     Downloads probe-cli's prebuilt userauth staticlib bundle instead (no
#     Rust toolchain needed). We don't build the default image this way,
#     but .github/workflows/test_e2e_miniooni.yml runs both modes in its
#     matrix specifically so a regression in either path - like the stale
#     userauthSourceSHA256 pin that broke USERAUTH_FROM_SOURCE=1 builds
#     against probe-cli master as of this writing (fix sent upstream, but
#     this harness shouldn't have to wait on it merging to catch the next
#     one of these) - shows up in CI instead of silently.
#
# We still don't configure ANONC_MANIFEST_BUCKET/etc in docker-compose.yml
# (see README's "Known gaps"), so probe-cli's own graceful fallback to
# uncredentialed submission still applies either way.

ARG USERAUTH_MODE=source

FROM golang:1.26-bookworm AS base

ARG PROBE_CLI_REPO=https://github.com/ooni/probe-cli.git
ARG PROBE_CLI_REF=master

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    git \
    make \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Shallow-clone the requested ref rather than vendoring probe-cli into this
# repo, so bumping the version tested is a one-line change in CI.
RUN git clone --depth 1 --branch "${PROBE_CLI_REF}" "${PROBE_CLI_REPO}" . \
    || (git clone "${PROBE_CLI_REPO}" . && git checkout "${PROBE_CLI_REF}")

# --- userauth staticlib: prebuilt bundle -------------------------------
FROM base AS builder-prebuilt

RUN make userauth

# --- userauth staticlib: built from source ------------------------------
FROM rust:1.88-bookworm AS ruststage

FROM base AS builder-source

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
    && rm -rf /var/lib/apt/lists/*

ENV USERAUTH_FROM_SOURCE=1
RUN make userauth

# --- pick the stage matching USERAUTH_MODE, build miniooni -------------
FROM builder-${USERAUTH_MODE} AS builder

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
