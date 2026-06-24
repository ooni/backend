#!/usr/bin/env python3
"""
List objects in an S3 bucket using boto3.
Configuration is read from environment variables (see defaults below).
"""

import boto3
import os
import requests
import logging
import sys
from pathlib import Path
from botocore.exceptions import ClientError, NoCredentialsError, EndpointConnectionError, LoginInsufficientPermissions

# Configuration from environment (set these in your shell)
ROLE_ARN = os.getenv("ROLE_ARN")
ROLE_SESSION_NAME = os.getenv("ROLE_SESSION_NAME", "assume-role-session")
ROLE_DURATION_SECONDS = int(os.getenv("ROLE_DURATION_SECONDS", "3600"))  # optional
AWS_REGION = os.getenv("AWS_REGION", "eu-central-1")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", 1000))              # number of hours of reports to process before exiting
BUCKET_NAME = os.getenv("S3_BUCKET_NAME")                    # required
DRY_RUN = os.getenv("DRY_RUN")
PREFIX = os.getenv("S3_PREFIX", "")
FASTPATH_API = os.getenv("FASTPATH_API", "")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()           # DEBUG, INFO, WARNING, ERROR, CRITICAL

def get_logger(name=__name__):
    """
    Configure and return a logger.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
        formatter = logging.Formatter(fmt, datefmt="%Y-%m-%dT%H:%M:%S%z")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(LOG_LEVEL)
    return logger

logger = get_logger("reuploader")

def assume_role_and_get_credentials(role_arn, session_name, duration_seconds=3600):
    """
    Assume the given role and return temporary credentials dict.
    """
    logger.debug("Assuming role %s (session=%s, duration=%s)", role_arn, session_name, duration_seconds)
    sts_client = boto3.client("sts", region_name=AWS_REGION)
    resp = sts_client.assume_role(
        RoleArn=role_arn,
        RoleSessionName=session_name,
        DurationSeconds=duration_seconds
    )
    creds = resp["Credentials"]
    logger.info("Assumed role %s successfully; expires at %s", role_arn, creds.get("Expiration"))
    return {
        "aws_access_key_id": creds["AccessKeyId"],
        "aws_secret_access_key": creds["SecretAccessKey"],
        "aws_session_token": creds["SessionToken"],
    }

def get_s3_client():
    """
    Returns an S3 client. If ROLE_ARN is set, assumes that role first and uses
    the temporary credentials. Otherwise uses provided credentials or default chain.
    """
    client_kwargs = {"region_name": AWS_REGION}
    if ROLE_ARN:
        try:
            temp = assume_role_and_get_credentials(ROLE_ARN, ROLE_SESSION_NAME, ROLE_DURATION_SECONDS)
            client_kwargs.update(temp)
        except ClientError as e:
            logger.error("Error assuming role: %s", e.response.get("Error", {}).get("Message"), exc_info=True)
            raise
    logger.debug("Creating S3 client with region %s", AWS_REGION)
    return boto3.client("s3", **client_kwargs)


def walk(s3, client, bucket_name, start_prefix=''):
    """
    Generator like os.walk:
    yields (prefix, subprefixes, objects)
      - prefix: current prefix ('' or ending with '/')
      - subprefixes: list of child prefixes (each ends with '/')
      - objects: list of object keys directly under this prefix (no trailing '/')
    """
    logger.debug("Walk called with prefix=%r", start_prefix)
    paginator = s3.get_paginator("list_objects_v2")
    page_iter = paginator.paginate(Bucket=bucket_name, Prefix=start_prefix, Delimiter='/')
    subprefixes = []
    objects = []
    for page in page_iter:
        subprefixes_page = [cp["Prefix"] for cp in page.get("CommonPrefixes", [])]
        subprefixes.extend(subprefixes_page)
        logger.debug("Found subprefixes: %s", subprefixes_page)
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key == start_prefix:
                continue
            objects.append(key)
    yield start_prefix, subprefixes, objects
    for sub in subprefixes:
        yield from walk(s3, client, bucket_name, sub)

def process_postcan(s3, client, bucket, key):
    try:
        p = Path(key)
        msmt_id = p.stem
        logger.debug("Processing key=%s msmt_id=%s", key, msmt_id)
        endpoint = f"{FASTPATH_API}/{msmt_id}"

        if DRY_RUN:
            logger.info("DRY RUN: s3://%s/%s -> %s", bucket, key, endpoint)
            return key, None

        logger.info("Sending s3://%s/%s -> %s", bucket, key, endpoint)
        resp_obj = s3.get_object(Bucket=bucket, Key=key)
        body = resp_obj["Body"]
        headers = {"Content-Type": "application/octet-stream"}
        # stream the body to the POST
        r = client.post(endpoint, data=body.iter_chunks(chunk_size=16 * 1024), headers=headers, timeout=60)
        with r:
            r.raise_for_status()
        # remove file from S3
        s3.delete_object(Bucket=bucket, Key=key)
        return key, None
    except Exception as e:
        return key, str(e)

def main():
    if not BUCKET_NAME:
        logger.error("S3_BUCKET_NAME environment variable is required.")
        return
    try:
        s3 = get_s3_client()
    except (NoCredentialsError, ClientError) as e:
        logger.error("Unable to create S3 client: %s", e, exc_info=True)
        return

    with requests.Session() as client:
        remaining = BATCH_SIZE
        try:
            for prefix, subs, objs in walk(s3, client, BUCKET_NAME, ""):
                logger.info("PREFIX: %s  subdirs=%d objects=%d", prefix, len(subs), len(objs))
                for key in objs:
                    key, err = process_postcan(s3, client, BUCKET_NAME, key)
                    if err:
                        logger.warning("Failed to process %s: %s", key, err)
                    else:
                        logger.info("Submitted %s to fastpath", key)

                # ignore paths without reports, e.g. parent dirs
                if len(objs) > 0:
                    remaining = remaining - 1
                    if remaining <= 0:
                        return
                    logger.debug(f"{remaining} entries left this batch")
        except EndpointConnectionError as e:
            logger.error("Endpoint connection error: %s", e, exc_info=True)
        except LoginInsufficientPermissions as e:
            logger.error("Invalid credentials error: %s", e, exc_info=True)
        except Exception as e:
            logger.exception("Unexpected error in main loop")

if __name__ == "__main__":
    main()
