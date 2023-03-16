import os
import os.path
import pytest
import sys
import shutil
import subprocess
from datetime import date, timedelta
from textwrap import dedent
from subprocess import PIPE
from pathlib import Path

import flask
from clickhouse_driver import Client as Clickhouse

# Setup logging before doing anything with the Flask app
# See README.adoc

import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(relativeCreated)6d %(levelname).1s %(filename)s:%(lineno)s %(message)s",
)

from ooniapi.app import create_app


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


@pytest.fixture(autouse=True)
def disable_rate_limits(app):
    app.limiter._disabled = True
    yield
    app.limiter._disabled = False


def pytest_addoption(parser):
    parser.addoption("--ghpr", action="store_true", help="enable GitHub integ tests")
    parser.addoption("--proddb", action="store_true", help="uses data from prod DB")
    parser.addoption("--create-db", action="store_true", help="populate the DB")
    parser.addoption(
        "--inject-msmts", action="store_true", help="populate the DB with fresh data"
    )


def pytest_configure(config):
    pytest.run_ghpr = config.getoption("--ghpr")
    pytest.proddb = config.getoption("--proddb")
    assert pytest.proddb is False, "--proddb is disabled"
    pytest.create_db = config.getoption("--create-db")
    pytest.inject_msmts = config.getoption("--inject-msmts")


@pytest.fixture(scope="session")
def setup_database_part_1():
    # Create database and users.
    # Executed as a dependency of setup_database_part_2
    # Drop and recreate database if exists.
    if not pytest.create_db:
        return


@pytest.fixture(scope="session")
def checkout_pipeline(tmpdir_factory):
    """Clone pipeline repo to then run fastpath from S3 and citizenlab importer"""
    if not pytest.create_db and not pytest.inject_msmts:
        return
    d = tmpdir_factory.mktemp("pipeline")
    if d.isdir():
        shutil.rmtree(d)
    cmd = f"git clone --depth 1 https://github.com/ooni/pipeline -q {d}"
    # cmd = f"git clone --depth 1 https://github.com/ooni/pipeline --branch reprocessor-ch -q {d}"
    cmd = cmd.split()
    runcmd(cmd, Path('.'))
    return Path(d)


def run_clickhouse_sql_scripts(app):
    log = app.logger
    clickhouse_url = app.config["CLICKHOUSE_URL"]
    click = Clickhouse.from_url(clickhouse_url)
    tables = click.execute("SHOW TABLES")
    for row in tables:
        if row[0] == "fastpath":
            return

    for fn in ["1_schema", "2_fixtures"]:
        sql_f = Path(f"tests/integ/clickhouse_{fn}.sql")
        print(f"Running {sql_f} on Clickhouse")
        queries = sql_f.read_text().split(";")
        for q in queries:
            q = q.strip()
            if not q:
                continue
            click.execute(q)


def _run_fastpath(fpdir: Path, start: str, end: str, limit: int) -> None:
    fprun = fpdir / "run_fastpath"
    cmd = [fprun.as_posix(), "--noapi", "--devel"]
    cmd.extend(["--start-day", start, "--end-day", end, "--stop-after", str(limit)])
    runcmd(cmd, fpdir)


def runcmd(cmd: str,wd: Path) -> None:
    print("Running " + " ".join(cmd))
    p = subprocess.run(cmd, cwd=wd)
    if p.returncode != 0:
        print("=" * 60)
        print(p.stderr)
        print("=" * 60)
        print(p.stdout)
        print("=" * 60)
        sys.exit(1)

def run_fingerprint_update(log, pipeline_dir: Path, clickhouse_url: str) -> None:
    log.info("Importing fingerprints")
    rdir = pipeline_dir / "af" / "analysis"
    runner = rdir / "run_analysis"
    cmd = [
        runner.as_posix(),
        "--update-fingerprints",
        "--devel",
        "--db-uri",
        clickhouse_url,
    ]
    runcmd(cmd, rdir)


def run_fastpath(log, pipeline_dir: Path, clickhouse_url: str) -> None:
    """Run fastpath from S3"""
    fpdir = pipeline_dir / "af" / "fastpath"
    conffile = fpdir / "etc/ooni/fastpath.conf"
    conffile.parent.mkdir(parents=True)
    conf = f"""
        [DEFAULT]
        collectors = localhost
        db_uri =
        clickhouse_url = {clickhouse_url}
        s3_access_key =
        s3_secret_key =
    """
    conffile.write_text(dedent(conf))
    # Necessary to test the statistics in the private API
    # Makes the contents of the test DB non deterministic
    log.info("Running fastpath to populate 'yesterday'")
    _run_fastpath(
        fpdir,
        (date.today() - timedelta(days=1)).strftime("%Y-%m-%d"),
        date.today().strftime("%Y-%m-%d"),
        3000,
    )

    log.info("Running fastpath to populate 2021-07-9")
    _run_fastpath(fpdir, "2021-07-09", "2021-07-10", 10000)


@pytest.fixture(autouse=True, scope="session")
def setup_database_part_2(setup_database_part_1, app, checkout_pipeline):
    # Create tables, indexes and so on
    # This part needs the "app" object
    if not pytest.create_db:
        return

    clickhouse_url = app.config["CLICKHOUSE_URL"]
    assert any([x in clickhouse_url for x in ("localhost", "clickhouse")])
    log = app.logger
    run_clickhouse_sql_scripts(app)
    run_fingerprint_update(log, checkout_pipeline, clickhouse_url)
    run_fastpath(log, checkout_pipeline, clickhouse_url)


@pytest.fixture(autouse=True, scope="session")
def connect_to_clickhouse(app):
    clickhouse_url = app.config["CLICKHOUSE_URL"]
    if clickhouse_url:
        app.click = Clickhouse.from_url(clickhouse_url)


@pytest.fixture(autouse=True, scope="session")
def inject_msmts(app, checkout_pipeline):
    if not pytest.inject_msmts:
        return


# # Fixtures used by test files # #


@pytest.fixture()
def log(app):
    return app.logger


@pytest.fixture()
def citizenlab_tblready(client, app):
    # Ensure the citizenlab table is populated
    r = app.click.execute("SELECT count() FROM citizenlab")[0][0]
    assert r > 2


@pytest.fixture
def url_prio_tblready(app):
    log = app.logger
    # Ensure the url_priorities table is populated
    r = app.click.execute("SELECT count() FROM url_priorities")[0][0]
    if r > 5:
        return

    rules = [
        ("NEWS", 100),
        ("POLR", 100),
        ("HUMR", 100),
        ("LGBT", 100),
        ("ANON", 100),
        ("MMED", 80),
        ("SRCH", 80),
        ("PUBH", 80),
        ("REL", 60),
        ("XED", 60),
        ("HOST", 60),
        ("ENV", 60),
        ("FILE", 40),
        ("CULTR", 40),
        ("IGO", 40),
        ("GOVT", 40),
        ("DATE", 30),
        ("HATE", 30),
        ("MILX", 30),
        ("PROV", 30),
        ("PORN", 30),
        ("GMB", 30),
        ("ALDR", 30),
        ("GAME", 20),
        ("MISC", 20),
        ("HACK", 20),
        ("ECON", 20),
        ("COMM", 20),
        ("CTRL", 20),
        ("COMT", 100),
        ("GRP", 100),
    ]
    rows = [
        {
            "sign": 1,
            "category_code": ccode,
            "cc": "*",
            "domain": "*",
            "url": "*",
            "priority": prio,
        }
        for ccode, prio in rules
    ]
    # The url_priorities table is CollapsingMergeTree
    query = """INSERT INTO url_priorities
        (sign, category_code, cc, domain, url, priority) VALUES
    """
    log.info("Populating url_priorities")
    app.click.execute(query, rows)
    app.click.execute("OPTIMIZE TABLE url_priorities FINAL")
