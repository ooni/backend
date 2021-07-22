import os
import os.path
import pytest
import sys
import shutil
import subprocess
from textwrap import dedent
from subprocess import PIPE
from pathlib import Path

import flask

# Setup logging before doing anything with the Flask app
# See README.adoc

import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(relativeCreated)6d %(levelname).1s %(filename)s:%(lineno)s %(message)s",
)

from ooniapi.app import create_app


def pytest_collection_modifyitems(items):
    for item in items:
        module_dir = os.path.dirname(item.location[0])
        if module_dir.endswith("functional"):
            item.add_marker(pytest.mark.functional)
        elif module_dir.endswith("unit"):
            item.add_marker(pytest.mark.unit)


@pytest.fixture(scope="session")
def app():
    app = create_app(testmode=True)
    app.debug = True
    assert app.logger.handlers == []
    return app


@pytest.yield_fixture
def client(app):
    """
    Overriding the `client` fixture from pytest_flask to fix this bug:
    https://github.com/pytest-dev/pytest-flask/issues/42
    """
    with app.test_client() as client:
        yield client

    while True:
        top = flask._request_ctx_stack.top
        if top is not None and top.preserved:
            top.pop()
        else:
            break


def pytest_addoption(parser):
    parser.addoption("--ghpr", action="store_true", help="enable GitHub integ tests")
    parser.addoption("--proddb", action="store_true", help="uses data from prod DB")
    parser.addoption("--create-db", action="store_true", help="populate a dedicated DB")


def pytest_configure(config):
    pytest.run_ghpr = config.getoption("--ghpr")
    pytest.proddb = config.getoption("--proddb")
    assert pytest.proddb is False, "--proddb is disabled"
    pytest.create_db = config.getoption("--create-db")


def sudopg(cmd, check=True):
    cmd = ["/usr/bin/sudo", "-u", "postgres", "psql", "-c", cmd]
    print(cmd)
    out = subprocess.run(cmd, check=check, stdout=PIPE, stderr=PIPE).stdout
    out = out.decode().strip()
    if out:
        print(out)


@pytest.fixture(scope="session")
def setup_database_part_1():
    # Create database and users.
    # Drop and recreate database if exists.
    if not pytest.create_db:
        return

    if os.path.exists("/usr/bin/sudo"):
        print("Creating PostgreSQL user and database")
        sudopg("DROP DATABASE IF EXISTS oonitestdb", check=True)
        sudopg("DROP ROLE IF EXISTS oonitest", check=True)
        sudopg("CREATE USER oonitest WITH ENCRYPTED PASSWORD 'test'", check=False)
        sudopg("CREATE DATABASE oonitestdb WITH OWNER 'oonitest'", check=False)
        sudopg("GRANT ALL PRIVILEGES ON DATABASE oonitestdb TO oonitest")

    else:
        # On github sudo is missing and the database is already created
        print("Sudo not found - not creating PostgreSQL database")


@pytest.fixture(scope="session")
def checkout_pipeline(tmpdir_factory):
    if not pytest.create_db:
        return
    d = tmpdir_factory.mktemp("pipeline")
    if d.isdir():
        shutil.rmtree(d)
    # cmd = f"git clone --depth 1 https://github.com/ooni/pipeline -q {d}"
    cmd = f"git clone --depth 1 https://github.com/ooni/pipeline --branch stop-after -q {d}"
    print(cmd)
    cmd = cmd.split()
    subprocess.run(cmd, check=True, stdout=PIPE, stderr=PIPE).stdout
    return Path(d)


def run_sql_scripts(app):
    log = app.logger
    # for i in ["1_metadb_users.sql", "2_metadb_schema.sql", "3_test_fixtures.sql"]:
    query = ""
    for i in ["2_metadb_schema.sql", "3_test_fixtures.sql"]:
        # for i in ["2_metadb_schema.sql",]:
        p = Path("tests/integ") / i
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("--"):
                continue
            query += line + " "
            if line.endswith(";"):
                try:
                    with app.db_engine.begin():
                        app.db_engine.execute(query)
                except Exception as e:
                    log.error(f"failed {query} {e}")
                query = ""


def run_fastpath(log, pipeline_dir, dburi):
    fpdir = pipeline_dir / "af" / "fastpath"
    fprun = fpdir / "run_fastpath"
    conffile = fpdir / "etc/ooni/fastpath.conf"
    conffile.parent.mkdir(parents=True)
    conf = f"""
        [DEFAULT]
        collectors = localhost
        db_uri = {dburi}
        s3_access_key =
        s3_secret_key =
    """
    conffile.write_text(dedent(conf))
    cmd = [
        fprun.as_posix(),
        "--noapi",
        "--devel",
        "--db-uri",
        dburi,
        "--start-day",
        "2021-07-9",
        "--end-day",
        "2021-07-10",
        "--stop-after",
        "10000",
    ]
    log.info("Running fastpath")
    log.info(cmd)
    subprocess.run(cmd, check=True, cwd=fpdir)


@pytest.fixture(autouse=True, scope="session")
def setup_database_part_2(setup_database_part_1, app, checkout_pipeline):
    # Create tables, indexes and so on
    # This part needs the "app" object
    if not pytest.create_db:
        return

    dburi = app.config["DATABASE_URI_RO"]
    if dburi and "metadb" in dburi:
        print("Refusing to make changes on metadb!")
        sys.exit(1)

    log = app.logger
    run_sql_scripts(app)
    run_fastpath(log, checkout_pipeline, dburi)


# # Fixtures used by test files # #


@pytest.fixture()
def log(app):
    return app.logger
