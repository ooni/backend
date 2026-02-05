# Python builder
FROM python:3.11-bookworm as builder
ARG BUILD_LABEL=docker

WORKDIR /build

RUN python -m pip install hatch

COPY . /build

# When you build stuff on macOS you end up with ._ files
# https://apple.stackexchange.com/questions/14980/why-are-dot-underscore-files-created-and-how-can-i-avoid-them
RUN find /build -type f -name '._*' -delete

RUN echo "$BUILD_LABEL" > /build/src/citizenlab/BUILD_LABEL

RUN hatch build

### Actual image running on the host
FROM python:3.11-bookworm as runner

WORKDIR /app

COPY --from=builder /build/README.md /app/
COPY --from=builder /build/dist/*.whl /app/
RUN pip install /app/*whl && rm /app/*whl

COPY --from=builder /build/src/citizenlab/common/alembic/ /app/alembic/
COPY --from=builder /build/src/citizenlab/common/alembic.ini /app/
RUN rm -rf /app/alembic/__pycache__

# Listen on 8000 so not to conflict with nginx
CMD ["uvicorn", "citizenlab.main:app", "--host", "0.0.0.0", "--port", "8000"]
EXPOSE 8000
