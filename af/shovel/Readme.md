# Pipeline Shovel

The purpose of this document is to explain how the various scripts inside of
this directory tree work.

The pipeline shovel is the base image used to run all the various stages of the
OONI Pipeline workflow.

The actual DAG that runs on top of the pipeline shovel is part of
`ooni/sysadmin` ansible role called `airflow` inside:
https://github.com/ooni/sysadmin/blob/master/ansible/roles/airflow/files/airflow-dags/canning.py

The various scripts inside of this directory tree are run by means of something
called the `docker-trampoline` that is also versioned in ooni/sysadmin:
https://github.com/ooni/sysadmin/blob/master/ansible/roles/airflow/files/docker-trampoline

`autoclaving.py`

docker run $docksafe --network none -v=$public/autoclaved:$public/autoclaved debian:jessie /bin/bash -c "mkdir -p $public/autoclaved/${bucket} && chown $uidno $public/autoclaved/${bucket}"
volargs="${volargs} --volume=$private/bridge_db:$private/bridge_db:ro"
volargs="${volargs} --volume=$private/canned/${bucket}:$private/canned/${bucket}:ro"
volargs="${volargs} --volume=$public/autoclaved/${bucket}:$public/autoclaved/${bucket}:rw"
set -- /usr/local/bin/autoclaving.py --start "$isofrom" --end "$isotill" \
    --canned-root $private/canned \
    --bridge-db $private/bridge_db/bridge_db.json \
    --autoclaved-root $public/autoclaved
;;

## Questions

* What is the purpose of `canned_repeated.py`, `canned_gzip_index.py`?

 I cannot seem to find any reference to this file in either `ooni/sysadmin` or
 `ooni/pipeline`, except in the pipeline Dockerfile, where it's only copied over
 the image.


* How should the http_request_fp be merged into http_request and http_control
 tables?

 class HttpRequestFPFeeder(HttpRequestFeeder):
    # It should probably become part of `http_request` and `http_control`
    # tables, but I'm too lazy to alter 40 Gb of tables right now...


* In relation to the residual cleanup. How should we be handling keys such as:
- `annotations`
- `data_format_version`
- `backend_version`
- `bucket_date`
- `probe_city`

* PostgresDict can easily be extended to support the above

* What's the story behind the benchmark user? Moved to: https://github.com/ooni/sysadmin/issues/289

Rewriting the table in batches seemed reasonable prior, but maybe it's better to
do it per-bucket.

### issues

Update the confirmed and anomaly columns as part of centrifugation
centrifugation performance on `insert into measurements`
Document what the next steps are for the OONI Pipeline development documentation question
Define metrics and alarms regarding "failed" measurements
Write tooling and docs on how to add blockpage fingerprints documentation fingerprintdb
Document how to partially reprocess measurements documentation
Document re-ingestion of data in pipeline documentation
Document writing feature extractors for new tests documentation


### Notes

We should update the software table to include metadata extracted from

To get all the possible values for the annotations keys:

```
SELECT
COUNT(*),
jsonb_object_keys(residual->'annotations')
FROM residual
WHERE residual->'annotations' IS NOT NULL AND residual->'annotations' != 'null'
GROUP BY 2;
```

All the possible annotations seem in date 2019-03-27:

```
404772	platform
204235	engine_name
204235	engine_version
204235	engine_version_full
18462	network_type
13720	flavor
6891	automated_testing
901	failure_network_name_lookup
836	failure_asn_lookup
712	failure_cc_lookup
462	failure_ip_lookup
201	probe
95	network
91	origin
10	manual
9	probeid
6	isp
6	vpn
5	foo
4	9990,hola
4	bar
4	discard
4	ISP
4	prove
4	scope
4	test
3	test_class
3	yossarian
2	example-ndt
2	integration-example
1	engine
1	ipurls
1	netloc
1	"probe"
```
