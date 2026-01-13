from typing import Callable, Union, Optional, List

import pytest
from pytest import FixtureRequest
from clickhouse_driver import Client as Clickhouse

from pytest_clickhouse.executor import ClickhouseExecutor
from pytest_clickhouse.executor_noop import ClickhouseNoopExecutor
from pytest_clickhouse.janitor import ClickhouseJanitor

def clickhouse(
    process_fixture_name: str,
    dbname: Optional[str] = None,
    url: Optional[str] = None,
) -> Callable[[FixtureRequest], Clickhouse]:

    @pytest.fixture
    def clickhouse_factory(request: FixtureRequest) -> Clickhouse:
        proc_fixture: Union[ClickhouseExecutor, ClickhouseNoopExecutor] = request.getfixturevalue(
            process_fixture_name
        )
        
        clickhouse_url = url or proc_fixture.clickhouse_url

        client = Clickhouse.from_url(clickhouse_url)
        yield client

    return clickhouse_factory