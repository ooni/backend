#!/usr/bin/env python3
"""
List objects in an S3 bucket using boto3.
Configuration is read from environment variables (see defaults below).
"""

import argparse
import boto3
import os
import requests

from pathlib import Path
from botocore.exceptions import ClientError, NoCredentialsError, EndpointConnectionError

# Configuration from environment (set these in your shell)
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")           # required if not using IAM role/profile
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")   # required if not using IAM role/profile
ROLE_ARN = os.getenv("ROLE_ARN")
ROLE_SESSION_NAME = os.getenv("ROLE_SESSION_NAME", "assume-role-session")
ROLE_DURATION_SECONDS = int(os.getenv("ROLE_DURATION_SECONDS", "3600"))  # optional
AWS_REGION = os.getenv("AWS_REGION", "eu-central-1")
BUCKET_NAME = os.getenv("S3_BUCKET_NAME")                    # required
PREFIX = os.getenv("S3_PREFIX", "")
FASTPATH_API = os.getenv("FASTPATH_API", "")

parser = argparse.ArgumentParser(description="List/process S3 objects")
parser.add_argument("--dry-run", action="store_true", help="List objects and print POSTs without downloading or sending them")
args = parser.parse_args()

def assume_role_and_get_credentials(role_arn, session_name, duration_seconds=3600):
    """
    Assume the given role and return temporary credentials dict:
    { aws_access_key_id, aws_secret_access_key, aws_session_token }
    """
    # Use provided long-term creds or default chain to call STS
    sts_kwargs = {"region_name": AWS_REGION,
                  "aws_access_key_id": AWS_ACCESS_KEY_ID,
                  "aws_secret_access_key": AWS_SECRET_ACCESS_KEY,
                  }
    sts_client = boto3.client("sts", **sts_kwargs)
    resp = sts_client.assume_role(
        RoleArn=role_arn,
        RoleSessionName=session_name,
        DurationSeconds=duration_seconds
    )
    creds = resp["Credentials"]
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
            print(f"Error assuming role: {e.response.get('Error', {}).get('Message')}")
            raise
    else:
        if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
            client_kwargs.update({
                "aws_access_key_id": AWS_ACCESS_KEY_ID,
                "aws_secret_access_key": AWS_SECRET_ACCESS_KEY,
            })
    return boto3.client("s3", **client_kwargs)

def walk(s3, client, bucket_name, start_prefix=''):
    """
    Generator like os.walk:
    yields (prefix, subprefixes, objects)
      - prefix: current prefix ('' or ending with '/')
      - subprefixes: list of child prefixes (each ends with '/')
      - objects: list of object keys directly under this prefix (no trailing '/')
    """
    paginator = s3.get_paginator("list_objects_v2")
    page_iter = paginator.paginate(Bucket=bucket_name, Prefix=start_prefix, Delimiter='/')
    subprefixes = []
    objects = []
    for page in page_iter:
        subprefixes.extend([cp["Prefix"] for cp in page.get("CommonPrefixes", [])])
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
        print(f"msmt_id: {p.stem}")
        endpoint = f"{FASTPATH_API}/{msmt_id}"

        if args.dry_run:
            print(f"DRY RUN: s3://{bucket}/{key} -> {endpoint}")
            return key, None

        print(f"SEND: s3://{bucket}/{key} -> {endpoint}")
        resp_obj = s3.get_object(Bucket=bucket, Key=key)
        body = resp_obj["Body"]
        headers = {"Content-Type": "application/octet-stream"}
        r = client.post(endpoint, data=body.iter_chunks(chunk_size=16 * 1024), headers=headers, timeout=60)
        with r:
            r.raise_for_status()
        # XXX: remove file from s3 if everything went OK
        return key, None
    except Exception as e:
        return key, str(e)

def main():
    if not BUCKET_NAME:
        print("S3_BUCKET_NAME environment variable is required.")
        return
    s3 = get_s3_client()
    with requests.Session() as client:
        for prefix, subs, objs in walk(s3, client, BUCKET_NAME, ""):
            print(f"PREFIX: {prefix}  subdirs={len(subs)} objects={len(objs)}")
            for key in objs:
                key, err = process_postcan(s3, client, BUCKET_NAME, key)
                if err:
                    print(f"Failed to process {key}: {err}")
                else:
                    print(f"Submitted {key} to fastpath")
            
if __name__ == "__main__":
    main()
