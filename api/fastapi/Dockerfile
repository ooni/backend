# Python builder
# Produced a virtualenv with all the deps good to go

# TODO(art): upgrade to bookworm (blocked by this
# https://github.com/actions/setup-python/issues/721) or stop using debian to
# have more recent base OS
FROM python:3.11-bullseye as py-build

RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
     && apt-get -y install --no-install-recommends python3 python3-dev

RUN curl -sSL https://install.python-poetry.org | POETRY_HOME=/opt/poetry python3 -

COPY . /app
WORKDIR /app
ENV PATH=/opt/poetry/bin:$PATH
RUN echo "${TAG_VERSION:-docker}" > /app/dataapi/TAG_VERSION
RUN poetry config virtualenvs.in-project true && poetry install --no-interaction --no-ansi

### Actual image running on the host
FROM python:3.11-bullseye

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

COPY --from=py-build /app /app
WORKDIR /app
CMD ["/app/.venv/bin/uvicorn", "dataapi.main:app", "--host", "0.0.0.0", "--port", "80"]
EXPOSE 80
