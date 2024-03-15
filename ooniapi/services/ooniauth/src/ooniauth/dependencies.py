from typing import Annotated

import boto3

from fastapi import Depends

from .common.dependencies import get_settings
from .common.config import Settings


def get_ses_client(settings: Annotated[Settings, Depends(get_settings)]):
    # TODO(art): add support for running integration tests of boto
    return boto3.client(  # no cov
        "ses",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )
