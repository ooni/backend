import io
from typing import Annotated, Tuple, TypeAlias, Any, Dict, List
from datetime import datetime
import time
from pathlib import Path

import boto3
import ooniauth_py
import ujson
import maxminddb
from fastapi import Depends

from mypy_boto3_s3 import S3Client

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from .common.config import Settings
from .common.dependencies import get_settings


SettingsDep: TypeAlias = Annotated[Settings, Depends(get_settings)]


def get_postgresql_session(settings: SettingsDep):
    engine = create_engine(settings.postgresql_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


PostgresSessionDep = Annotated[Session, Depends(get_postgresql_session)]


def get_asn_cc_reader(settings: SettingsDep):
    db_path = Path(settings.geoip_db_dir, "asn_cc.mmdb")
    return maxminddb.open_database(db_path)


ASNCCReaderDep = Annotated[maxminddb.Reader, Depends(get_asn_cc_reader)]


def get_s3_client() -> S3Client:
    s3 = boto3.client("s3")
    return s3


S3ClientDep = Annotated[S3Client, Depends(get_s3_client)]

__cache__ = dict()


def get_cache():
    return __cache__


CacheDep = Annotated[Dict[str, Any], Depends(get_cache)]

class Policy(BaseModel):
    age: Tuple[int, int] = Field(
        description="Inclusive lower/upper bounds for the probe age accepted by this rule."
    )
    measurement_count: int = Field(
        description="Minimum lower bound for the probe measurement count accepted by this rule."
    )

class Match(BaseModel):
    probe_cc: str = Field(
        description="Two-letter probe country code. Use '*' to match any country."
    )
    probe_asn: str = Field(
        description="Probe ASN in 'ASNNNN' format. Use '*' to match any ASN."
    )

class PolicyEntry(BaseModel):
    """
    Single `submission_policy` rule in the manifest.
    Defines which probes match this entry and which verification ranges apply.
    """
    policy: Policy
    match: Match

class Manifest(BaseModel):
    """
    Manifest used for ZKP verification
    """

    nym_scope: str = "ooni.org/{probe_cc}/{probe_asn}"
    submission_policy: List[PolicyEntry]
    public_parameters: str

    @model_validator(mode="after")
    def _validate_catch_all(self):

        # ensure the last entry in the submission_policy is the catch_all rule
        if len(self.submission_policy) == 0:
            raise ValueError(
                "submission_policy must include a catch-all rule with "
                "match.probe_cc='*' and match.probe_asn='*'"
            )

        catch_all = self.submission_policy[-1]
        if catch_all.match.probe_asn != "*" or catch_all.match.probe_cc != "*":
            raise ValueError(
                "Last rule in submission policy should be a catch-all. "
            )

        return self


class ManifestMeta(BaseModel):
    """
    Manifest metadata
    """

    version: str
    last_modification_date: datetime
    manifest_url: str = Field(
        description="URL pointing to the AWS public record of this manifest"
    )
    library_version: str = Field(
        description="Version of the Python library implementing the anonymous credentials protocol"
    )
    protocol_version: str = Field(
        description="Anonymous credentials protocol implementation version"
    )


class ManifestResponse(BaseModel):
    manifest: Manifest
    meta: ManifestMeta


def get_manifest(s3: S3ClientDep, bucket: str, file: str) -> ManifestResponse:
    # Get version & metadata
    resp = s3.list_object_versions(
        Bucket=bucket, Prefix=file  # Only get versions of the specified file
    )

    versions = resp.get("Versions")
    assert versions, "Couldn't find versions for the specified manifest"

    latest = next((x for x in versions if x.get("IsLatest")), None)

    assert latest, "Couldn't find latest manifest version. Is versioning activated?"
    assert "VersionId" in latest, "Manifest version not provided"
    assert "LastModified" in latest, "Last modification date not provided"

    meta = ManifestMeta(
        version=latest["VersionId"],
        last_modification_date=latest["LastModified"],
        manifest_url=f"https://{bucket}.s3.amazonaws.com/{file}",
        library_version=ooniauth_py.__version__,
        protocol_version=ooniauth_py.get_protocol_version()
    )

    # Get Object
    manifest_resp = s3.get_object(Bucket=bucket, Key=file)
    manifest_json = ujson.load(manifest_resp["Body"])
    manifest = Manifest(**manifest_json)
    return ManifestResponse(manifest=manifest, meta=meta)


def get_manifest_cached(
    s3: S3ClientDep,
    bucket: str,
    file: str,
    cache: CacheDep,
    cache_time_seconds: float = 60,
) -> ManifestResponse:
    """
    Fetch the manifest and cache the result for `cache_time_seconds`

    Following calls will try to fetch the result from cache
    """
    key = str((bucket, file))
    val = cache.get(key)
    now = time.time()

    if val is None or (now - val[1]) > cache_time_seconds:
        val = __cache__[key] = (get_manifest(s3, bucket, file), now)

    return val[0]


def _get_manifest(
    s3: S3ClientDep, settings: SettingsDep, cache: CacheDep
) -> ManifestResponse:
    return get_manifest_cached(
        s3, settings.anonc_manifest_bucket, settings.anonc_manifest_file, cache
    )

ManifestDep = Annotated[ManifestResponse, Depends(_get_manifest)]


def read_file(s3_client: S3ClientDep, bucket: str, file: str) -> str:
    """
    Reads the content of `file` within `bucket` into a  string

    Useful for reading config files from the s3 bucket
    """
    buff = io.BytesIO()
    s3_client.download_fileobj(bucket, file, buff)
    return buff.getvalue().decode()


def get_tor_targets_from_s3(
    settings: SettingsDep, s3client: S3ClientDep, cache: CacheDep
) -> Dict[str, Any]:
    cacheKey = str(Path(settings.config_bucket, settings.tor_targets))
    resp = cache.get(cacheKey)
    if resp is None:
        targetstr = read_file(s3client, settings.config_bucket, settings.tor_targets)
        resp = ujson.loads(targetstr)
        cache[cacheKey] = resp
    return resp


TorTargetsDep = Annotated[Dict, Depends(get_tor_targets_from_s3)]

def get_psiphon_config_from_s3(
    settings: SettingsDep, s3client: S3ClientDep, cache: CacheDep
) -> Dict[str, Any]:
    cacheKey = str(Path(settings.config_bucket, settings.psiphon_config))
    resp = cache.get(cacheKey)
    if resp is None:
        psiphon_config_str = read_file(s3client, settings.config_bucket, settings.psiphon_config)
        resp = ujson.loads(psiphon_config_str)
        cache[cacheKey] = resp
    return resp


PsiphonConfigDep = Annotated[Dict | None, Depends(get_psiphon_config_from_s3)]
