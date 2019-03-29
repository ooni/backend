# OONI API

Source for https://api.ooni.io/

## Local development

### Requirements

* Docker
* Make
* Python >= 3.5
* Postgresql

### Quickstart

**Note**: the default database configuration is `postgres@localhost:5432/ooni_measurements`,
you only need to run the second step below (`export DATABASE_URL`) in case you want to use a different one.

```bash
pip install -r requirements.txt # Install all the python dependencies
export DATABASE_URL=postgresql://my_db_user:my_db_password@localhost:5432/ooni_measurements
make create-tables # Create the database and tables
make serve # Run the server
```

The last step will start the docker containers needed to run the application locally,
 building also all the required web assets.

### Running the tests

First, install the tests requirements, by running:

```bash
pip install -r requirements/test.txt
```

And then you can run the tests:

```bash
make test
```

## Deployment

Deployment to staging is managed automatically when something is merged into
 the `master` branch.

This means that `master` **must** always be buildable and working.

Rollover to production is currently handled manually by running the same
deploy script used for staging deployments.

It requires `docker-machine`. Once that is installed to deploy to production
 you can do:

```
DEPLOY_HOST="1.1.1.1" scripts/deploy.sh production path/to/id_rsa
```

You can fill the database with some report files by creating a listing of
report files and importing this listing from a text file with:

```
python -m measurements updatefiles -f listing.txt
```

An example of `listing.txt` can be found in `dev/fixtures.txt`

## Environments

This application is designed to be run inside of 4 possible environments:
**development**, **testing**, **staging** and **production**.

The meaning of these three environments is:

* **development** this is the environment used when you are actively
developing the application. When in this mode we favour ease of development
over similarity of the environment when it's in production or staging.

* **testing:** this is the environment used for running unit, functional and
 integration tests automatically on our CI platform. This environment is as
 close as possible to the real production or staging environment. When
 running under testing we only expose it locally.

* **staging** this is the environment used for triggering automatic
redeployment of the application when merging into the master branch. When
deploying on staging the application will be live on the staging endpoint
and should functionally be equivalent to production.

* **production** this is the environment used when it's ready to be deployed
. Production deployments are currently triggerred manually, but some day may
 be automatic based on tagging a certain git tag.

## Configuration

Configuration management is handled by overriding environment variables and
other parameters inside of `config/production.yml`, `config/staging.yml`,
`config/testing.yml`. Read the [Environments section](#environments) to
learn the meaning of these.

## Deployment notes

The database for the measurement files needs to be kept up to date as such it's
recommended that the following things are done:

On first run you ensure the database is initialized with the correct
report files.
You can do so in the following way:
```
python -m measurements updatefiles -t TARGET_DIR
```
Where `TARGET_DIR` is generally going to be the same path as
`REPORTS_DIRECTORY` in the configuration file.

Then in the cronjob that runs periodically to sync reports with the
measurements server you should generate a listing of all the new reports file
(it's sufficient to put their filepaths inside of a text file) and then
run:

```
python -m measurements updatefiles -f update-file.txt
```

`updatefiles` will check to see if the files are already in the database, but
it's much more performant to not run the update with files that are already in
the database.
