# Python builder
FROM python:3.12-bookworm AS builder
ARG BUILD_LABEL=docker

WORKDIR /build

RUN python -m pip install hatch

COPY . /build

RUN hatch build

### Actual image running on the host
FROM python:3.12-bookworm AS runner

WORKDIR /app

COPY --from=builder /build/README.md /app/
COPY --from=builder /build/dist/*.whl /app/

RUN pip install /app/*whl && rm /app/*whl

# required if not using IAM role/profile
ENV AWS_ACCESS_KEY_ID=
# required if not using IAM role/profile
ENV AWS_SECRET_ACCESS_KEY=
ENV ROLE_ARN=
ENV ROLE_SESSION_NAME="assume-role-session"
# optional
ENV ROLE_DURATION_SECONDS="3600"
ENV AWS_REGION = os.getenv("AWS_REGION", "eu-central-1")
# required
ENV BUCKET_NAME=
# s3 path prefix
ENV PREFIX = os.getenv("S3_PREFIX", "")
# fastpath API endpoint
ENV FASTPATH_API=

CMD ["reuploader"]
