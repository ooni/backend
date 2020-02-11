# OONI API

Source for https://api.ooni.io/

## Local development

### Requirements

* Docker
* Make
* Python >= 3.5
* Postgresql

### Quickstart

**Note**: the default database configuration is `postgres@localhost:15432/ooni_measurements`,
you only need to run the second step below (`export DATABASE_URL`) in case you want to use a different one.

### Running the API locally

```bash
tox -e run

# Monitor the generated metrics
watch -n1 -d 'curl -s http://127.0.0.1:5000/metrics'

# Call the API
curl http://127.0.0.1:5000/api/v1/measurements?since=2019-01-01&until=2019-02-01&limit=1
```

### Running the tests

Run the integration tests:

```bash
tox -q -e integ

# Run only test_list_measurements* tests, stop on first failure, monitor file changes and rerun failed tests
tox -q -e integ -k test_list_measurements -x -f
```
