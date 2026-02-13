from typing import Annotated
from fastapi import Depends
import boto3
from mypy_boto3_s3 import S3Client

def get_s3_client() -> S3Client:
    s3 = boto3.client("s3")
    return s3


S3ClientDep = Annotated[S3Client, Depends(get_s3_client)]
