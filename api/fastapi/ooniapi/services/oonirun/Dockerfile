# Python builder
FROM python:3.11-bookworm as builder
ARG BUILD_LABEL=docker

WORKDIR /build

RUN python -m pip install hatch

COPY . /build

RUN echo "$BUILD_LABEL" > /build/src/oonirun/BUILD_LABEL

RUN hatch build

### Actual image running on the host
FROM python:3.11-bookworm as runner

WORKDIR /app

COPY --from=builder /build /build/dist/*.whl /app/

RUN pip install /app/*whl && rm /app/*whl

CMD ["uvicorn", "oonirun.main:app", "--host", "0.0.0.0", "--port", "80"]
EXPOSE 80
