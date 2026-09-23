from _pytest.config.argparsing import Parser

from pytest_clickhouse import factories

_help_image = "Docker image to use to run Clickhouse server"
_help_host = "Host at which Clickhouse will accept connections"
_help_port = "Port at which Clickhouse will accept connections"
_help_dbname = "Default database name"
_help_load = "Dotted-style or entrypoint-style path to callable or path to SQL File"


def pytest_addoption(parser: Parser) -> None:
    """
    Configure options for pytest-clickhouse
    """

    parser.addini(
        name="clickhouse_image", help=_help_image, default="clickhouse/clickhouse-server:24.3-alpine"
    )

    parser.addini(name="clickhouse_host", help=_help_host, default="localhost")

    parser.addini(name="clickhouse_port", help=_help_port, default=None)

    parser.addini(name="clickhouse_dbname", help=_help_dbname, default="tests")

    parser.addoption(
        "--clickhouse-image",
        action="store",
        dest="clickhouse_image",
        help=_help_image
    )

    parser.addoption(
        "--clickhouse-host",
        action="store",
        dest="clickhouse_host",
        help=_help_host
    )

    parser.addoption(
        "--clickhouse-port",
        action="store",
        dest="clickhouse_port",
        help=_help_port
    )

    parser.addoption(
        "--clickhouse-dbname",
        action="store",
        dest="clickhouse_dbname",
        help=_help_dbname
    )


clickhouse_proc = factories.clickhouse_proc()
clickhouse_noproc = factories.clickhouse_noproc()
clickhouse = factories.clickhouse("clickhouse_proc")