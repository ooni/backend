import io
from pathlib import Path
from typing import Annotated, Dict, Any

import boto3
import ujson
import geoip2.database
from fastapi import Depends

from mypy_boto3_s3 import S3Client

from ooniprobe.common.dependencies import SettingsDep


def get_cc_reader(settings: SettingsDep):
    db_path = Path(settings.geoip_db_dir, "cc.mmdb")
    return geoip2.database.Reader(db_path)


CCReaderDep = Annotated[geoip2.database.Reader, Depends(get_cc_reader)]


def get_asn_reader(settings: SettingsDep):
    db_path = Path(settings.geoip_db_dir, "asn.mmdb")
    return geoip2.database.Reader(db_path)


ASNReaderDep = Annotated[geoip2.database.Reader, Depends(get_asn_reader)]


def get_s3_client() -> S3Client:
    s3 = boto3.client("s3")
    return s3


S3ClientDep = Annotated[S3Client, Depends(get_s3_client)]

__cache__ = dict()

def get_cache(): return __cache__

CacheDep = Annotated[Dict[str, Any], Depends(get_cache)]

def read_file(s3_client : S3ClientDep, bucket: str, file : str) -> str:
    """
    Reads the content of `file` within `bucket` into a  string

    Useful for reading config files from the s3 bucket
    """
    buff = io.BytesIO()
    s3_client.download_fileobj(bucket, file, buff)
    return buff.getvalue().decode()


async def get_tor_targets_from_s3(settings: SettingsDep, s3client: S3ClientDep, cache: CacheDep) -> Dict[str, Any]:
    cacheKey = str(Path(settings.config_bucket, settings.tor_targets))
    resp = cache.get(cacheKey)
    if resp is None:
        targetstr = read_file(s3client, settings.config_bucket, settings.tor_targets)
        resp = ujson.loads(targetstr)
        cache[cacheKey] = resp
    yield resp

TorTargetsDep = Annotated[Dict, Depends(get_tor_targets_from_s3)]
