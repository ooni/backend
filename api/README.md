# OONI API

Source for https://api.ooni.io/

File bugs with the API inside of: https://github.com/ooni/backend/issues/new

## Local development

You can run the OONI API locally in a development environment using `docker`
and `docker-compose`. Follow the instructions below to set it up.

### Quickstart

First you should build the docker image for the API:
```
make build
```

This only needs to be run once, or any time you make changes to the
dependencies in the `newapi/build_runnner.sh` script.

To populate the database with some sample data (this is needed for running many
of the tests), you should run:
```
make initdb
```

This also needs to only be run once.

At this point you have a fully setup development environment.

You can run the full test suite via:
```
make tests
```

If you care to only run a specific test, that can be done using the `pytest`
`-k` option, passed in as a T env var to `make`:
```
T="-k test_my_test_name" make tests
```

If you want to run a local instance of the OONI API, this can be done via:
```
make serve
```
