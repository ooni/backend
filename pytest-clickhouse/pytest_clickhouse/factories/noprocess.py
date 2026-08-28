from typing import Callable, Optional

import pytest
from pytest import FixtureRequest

from pytest_clickhouse.config import get_config
from pytest_clickhouse.executor_noop import ClickhouseNoopExecutor
from pytest_clickhouse.janitor import ClickhouseJanitor

def clickhouse_noproc(
    host: Optional[str] = None,
    port: Optional[str] = None,
    dbname: Optional[str] = None,
) -> Callable[[FixtureRequest], ClickhouseNoopExecutor]:

    @pytest.fixture(scope="session")
    def clickhouse_noproc_fixture(
        request: FixtureRequest
    ) -> ClickhouseNoopExecutor:
        config = get_config(request)
        clickhouse_noop_exec = ClickhouseNoopExecutor(
            host=host or config["host"],
            port=port or config["port"],
            dbname=dbname or config["dbname"],
        )

        with clickhouse_noop_exec:
            with ClickhouseJanitor(
                dbname=clickhouse_noop_exec.dbname,
                clickhouse_url=clickhouse_noop_exec.clickhouse_url
            ):
                yield clickhouse_noop_exec

    return clickhouse_noproc_fixture