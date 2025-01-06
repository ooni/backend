# Systemd timers

Some backend components like the API and Fastpath run as daemons. Many
other run as Systemd timers at various intervals.

The latter approach ensures that a component will start again at the
next time interval even if the previous run crashed out. This provides a
moderate reliability benefit at the expense of having to perform
initialization and shutdown at every run.

To show the existing timers and their next start time run:

```bash
systemctl list-timers
```

## Summary of timers

Here is a summary of the most important timers used in the backend:

    UNIT                           ACTIVATES
    dehydrated.timer               dehydrated.service
    detector.timer                 detector.service
    ooni-api-uploader.timer        ooni-api-uploader.service
    ooni-db-backup.timer           ooni-db-backup.service
    ooni-download-geoip.timer      ooni-download-geoip.service
    ooni-rotation.timer            ooni-rotation.service
    ooni-update-asn-metadata.timer ooni-update-asn-metadata.service
    ooni-update-citizenlab.timer   ooni-update-citizenlab.service
    ooni-update-fingerprints.timer ooni-update-fingerprints.service

Ooni-developed timers have a matching unit file with .service extension.

To show the existing timers and their next start time run:

```bash
systemctl list-timers
```

This can be useful for debugging.

## Dehydrated timer

Runs the Dehydrated ACME tool, see [Dehydrated](#dehydrated)&thinsp;⚙

is a simple script that provides ACME support for Letsencrypt. It's
integrated with Nginx or HaProxy with custom configuration or a small
script as \"glue\".

[Source](https://github.com/ooni/sysadmin/blob/master/ansible/roles/dehydrated/templates/dehydrated.timer)

## Detector timer

Runs the [social media blocking event detector](#social-media-blocking-event-detector)&thinsp;⚙. It is
installed by the [detector package](#detector-package)&thinsp;📦.

## ooni-api-uploader timer

Runs the [Measurement uploader](#measurement-uploader)&thinsp;⚙. It is installed by the
[analysis package](legacybackend/operations/#analysis-package)&thinsp;📦. Runs `/usr/bin/ooni_api_uploader.py`

[Source](https://github.com/ooni/backend/blob/0ec9fba0eb9c4c440dcb7456f2aab529561104ae/api/debian/ooni-api-uploader.timer)

## ooni-db-backup timer

Runs the [Database backup tool](#database-backup-tool)&thinsp;⚙ as
`/usr/bin/ooni-db-backup` Also installed by the
[analysis package](legacybackend/operations/#analysis-package)&thinsp;📦.

[Source](https://github.com/ooni/backend/blob/0ec9fba0eb9c4c440dcb7456f2aab529561104ae/analysis/debian/ooni-db-backup.timer)

## ooni-download-geoip timer

Fetches GeoIP databases, installed by the [ooni-api](#api)&thinsp;⚙. Runs
`/usr/bin/ooni_download_geoip.py`

Monitored with the [GeoIP dashboard](#geoip-mmdb-database-dashboard)&thinsp;📊

See [GeoIP downloader](#geoip-downloader)&thinsp;⚙

[Source](https://github.com/ooni/backend/blob/0ec9fba0eb9c4c440dcb7456f2aab529561104ae/api/debian/ooni-download-geoip.timer)

## ooni-rotation timer

Runs the test helper rotation script, installed by the
[analysis package](legacybackend/operations/#analysis-package)&thinsp;📦. Runs `/usr/bin/rotation`

[Source](https://github.com/ooni/backend/blob/0ec9fba0eb9c4c440dcb7456f2aab529561104ae/analysis/debian/ooni-rotation.timer)

## ooni-update-asn-metadata timer

Fetches [ASN](#asn)&thinsp;💡 metadata, installed by the
[analysis package](legacybackend/operations/#analysis-package)&thinsp;📦. Runs `/usr/bin/analysis --update-asnmeta`

[Source](https://github.com/ooni/backend/blob/0ec9fba0eb9c4c440dcb7456f2aab529561104ae/analysis/debian/ooni-update-asn-metadata.timer)

## ooni-update-citizenlab

Fetches CitizenLab data from GitHub, installed by the
[analysis package](legacybackend/operations/#analysis-package)&thinsp;📦. Runs `/usr/bin/analysis --update-citizenlab`

[Source](https://github.com/ooni/backend/blob/0ec9fba0eb9c4c440dcb7456f2aab529561104ae/analysis/debian/ooni-update-citizenlab.timer)

## ooni-update-fingerprints

Fetches fingerprints from GitHub, installed by the
[analysis package](legacybackend/operations/#analysis-package)&thinsp;📦. Runs `/usr/bin/analysis --update-fingerprints`

[Source](https://github.com/ooni/backend/blob/0ec9fba0eb9c4c440dcb7456f2aab529561104ae/analysis/debian/ooni-update-fingerprints.timer)
