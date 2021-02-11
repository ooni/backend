# OONI API

Source for https://api.ooni.io/

File bugs with the API inside of: https://github.com/ooni/backend/issues/new

## Local development

### Quickstart

**Note**: the default database configuration is `postgres@localhost:15432/ooni_measurements`,
you only need to run the second step below (`export DATABASE_URL`) in case you want to use a different one.

### Running the API on Debian Buster

Option 1: Build a package with dpkg-buildpackage -us -uc and install it with sudo debi

Option 2: Install the dependencies from newapi/debian/control or using the commands in build_docker.sh

```bash

# Monitor the generated metrics
watch -n1 -d 'curl -s http://127.0.0.1:5000/metrics'

# Call the API
curl http://127.0.0.1:5000/api/v1/measurements?since=2019-01-01&until=2019-02-01&limit=1
```

### Running the API using Docker

```bash
docker build -t ooniapi .

docker run --name ooniapirun --rm -i -t ooniapi gunicorn3 --reuse-port ooniapi.wsgi --statsd-host 127.0.0.1:8125 --reuse-port
```

### Running the tests

Run the integration tests:

```bash
tox -q -e integ

# Run only test_list_measurements* tests, stop on first failure, monitor file changes and rerun failed tests
tox -q -e integ -k test_list_measurements -x -f
```

### Bug fix micro-tutorial

Clone the API repository.

Set up a local database or a port forwarding.

```bash
ssh amsmetadb.ooni.nu  -L 0.0.0.0:15432:127.0.0.1:5432 -Snone -g -C
```

Create a new test in tests/integ/test_integration.py and run it with:

```bash
tox -e integ -- -s --show-capture=no -k test_bug_12345_blah
```

Fix the bug and send a pull request for the bugfix and test together.

Thanks!
