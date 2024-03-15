from typing import Annotated

from clickhouse_driver import Client as ClickhouseClient
import boto3

from fastapi import Depends

from .common.dependencies import get_settings
from .common.config import Settings


def get_clickhouse_client(
    settings: Annotated[Settings, Depends(get_settings)]
) -> ClickhouseClient:
    return ClickhouseClient.from_url(settings.clickhouse_url)


def get_ses_client(settings: Annotated[Settings, Depends(get_settings)]):
    return boto3.client(
        "ses",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )
