from pathlib import Path
from typing import TypedDict, Optional, List, Union

from pytest import FixtureRequest


class ClickhouseConfigDict(TypedDict):
    """
    Typed Config Dictionary
    """

    image_name: str
    host: str
    port: Optional[str]
    dbname: str


def get_config(request: FixtureRequest) -> ClickhouseConfigDict:
    """
    Return a dictionary with config options
    """    

    def get_clickhouse_option(option: str) -> any:
        name = f"clickhouse_{option}"
        return request.config.getoption(name) or request.config.getini(name)

    return ClickhouseConfigDict(
        image_name=get_clickhouse_option("image"),
        host=get_clickhouse_option("host"),
        port=get_clickhouse_option("port"),
        dbname=get_clickhouse_option("dbname"),
    )
