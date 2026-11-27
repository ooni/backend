from typing import Callable, Iterator, Optional

import pytest
from pytest import FixtureRequest

from pytest_clickhouse.executor import ClickhouseExecutor
from pytest_clickhouse.config import get_config
from pytest_clickhouse.janitor import ClickhouseJanitor

def clickhouse_proc(
    image_name: Optional[str] = None,
    dbname: Optional[str] = None,
) -> Callable[[FixtureRequest], ClickhouseExecutor]:
    
    @pytest.fixture(scope="session")
    def clickhouse_proc_fixture(
        request: FixtureRequest
    ) -> ClickhouseExecutor:
        config = get_config(request)
        clickhouse_executor = ClickhouseExecutor(
            image_name=image_name or config["image_name"],
            dbname=dbname or config["dbname"]
        )

        with clickhouse_executor:
            clickhouse_executor.wait_for_clickhouse()
            with ClickhouseJanitor(
                dbname=clickhouse_executor.dbname,
                clickhouse_url=clickhouse_executor.clickhouse_url
            ):
                yield clickhouse_executor
        
    return clickhouse_proc_fixture