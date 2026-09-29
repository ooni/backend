# reuploader

`reuploader` retrieves measurements from an S3 bucket and submits them to a FastPath instance.

Measurements that were submitted to the OONI Probe API service but failed to submit to FastPath (for example due to an outage) are saved to an S3 bucket; this tool processes and re-uploads those failed measurements.

## Environment variables

Required:
- **BUCKET_NAME** — name of the failed-reports S3 bucket
- **FASTPATH_API** — FastPath API endpoint (measurements are POSTed here)

Required if not using an IAM role/profile:
- **AWS_ACCESS_KEY_ID**
- **AWS_SECRET_ACCESS_KEY**

Optional:
- **ROLE_ARN**
- **ROLE_SESSION_NAME** — default: `"assume-role-session"`
- **ROLE_DURATION_SECONDS** — default: `"3600"`
- **AWS_REGION** — default: `"eu-central-1"`
- **PREFIX** — S3 path prefix used to limit the paths scanned

## Usage

Set the required environment variables, optionally set any of the optional ones, then run `reuploader` to scan the specified S3 bucket/prefix and re-submit failed measurements to the FastPath API.
