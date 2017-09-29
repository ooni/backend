# Open Observatory Pipeline

This is the Open Observatory data processing pipeline. Actually, two of them.

The legacy one is based on the [luigi workflow engine](https://github.com/spotify/luigi)
and described below.

The modern one is based on the [Apache Airflow](https://airflow.incubator.apache.org/) and it's described in [docs](docs/pipeline-16.10.md).

## Setup

Edit the `client.cfg` based on `client.cfg.example`. See the
[configuration](#configuration) section for more information on how to
configure the data processing pipeline.

Install also all the python requirements in `requirements.txt`.

Install or build
[PyYAML](http://pyyaml.org/wiki/PyYAML#DownloadandInstallation) with C
bindings.

*Note*: You should not use more than 1 worker (luigi `--workers` option) per core
otherwise you could be wasting a bunch of CPU time in context switching.

## How to run the pipeline tasks

Ensure that the `pipeline` module is within your `sys.path`. This can be done
by exporting the `PYTHONPATH` environment variable to the directory where
ooni-pipeline is copied to.


### Daily workflow

This `daily_workflow` is the main workflow that consists of the following steps:

* Performs normalisation of the reports to adhere to the 0.2.0 data format and
  converts them to JSON (`NormaliseReport`).

* Performs sanitisation of the reports that contain private bridge addresses
  (`SanitiseReport`).

* Inserts the measurements inside of the postgresql `metrics-table`
  (`InsertMeasurementsIntoPostgres`).

The dependency graph is built from a master task called `ListReportsAndRun`
that takes as arguments:

* `date_interval` the range of dates that should be operated on

* `task` the name of the task that should be run (if you choose to run
  `SanitiseReport` only `NormaliseReport` will be run, while
  `InsertMeasurementsIntoPostgres` will run `NormaliseReport` that in turn runs
  also `SanitiseReport`). By default task is set to
  `InsertMeasurementsIntoPostgres`.

* `test_names` a space separated list of test names that the task should
  operate on.

It is possible to specify an optional boolean parameter with the
`--update-views true` command line argument to indicate that the materialised
views should also be updated. To learn how to generate the materialised views
see below.

Here is an example of how to run the daily workflow:

```
luigi --module pipeline.batch.daily_workflow ListReportsAndRun --task NoramliseReport --test-names 'http_requests dns_consistency' --date-interval 2016-01-01-2016-02-01 --workers 10
```

To generate the materialised views the `sql_tasks` module shall be used. In here there are two main tasks:

* `CreateMaterialisedViews` is used to create the materialised views used to
  count the number of blockpages detected and the number of identified vendors.

* `CreateIndexes` is used to create database indexes on certain keys.

To create indexes run:

```
luigi --module pipeline.batch.sql_tasks CreateIndexes
```

To create the materialised views run:

```
luigi --module pipeline.batch.sql_tasks CreateMaterialisedViews
```

## Domain intelligence

These tasks are used to update the tables related to the categories of domains being tested. Currently we support extracting the categories for the urls in the citizenlab repository.

Moreover there are also tasks in here related to updating information pertaining to ASNs.

To update the citizen-lab categories of URLs you shall run:

```
luigi --module pipeline.batch.domain_intelligence InsertCitizenLabURLS
```

To update the ASN information run:

```
luigi --module pipeline.batch.domain_intelligence UpdateASNPostgres
```

## Configuration

Before running the pipeline you should configure it by editing the
`client.cfg` file. An example configuration file is provided inside of
`client.cfg.example`.

The files you should probably be editing are the following:

### core

* **tmp_dir** What directory should be used to store temporary files.

* **ssh_private_key_file** What ssh private key shall be used by luigi for sshing into ssh:// machines.

* **ooni_pipeline_path** The location on the ec2 instance where to look for the ooni-pipeline repository.

### aws

* **access_key_id** This is your AWS access key ID for spinning up EC2 instances.

* **secret_access_key** This is your AWS secret token.

### postgres

* **host** The hostname of your postgres instance.

* **database** The database name.

* **username** The username to use when logging in.

* **password** The password to use when logging in.

* **table** The database table to use for writing measurements to.

### ooni

* **bridge-db-path** A path to where you have a bridge_db.json file that
    contains mappings between bridge IPs, their hashes and the ring they were
    taken for (this is required for the sanitisation of bridge_reachability
    reports).

* `raw-reports-dir` is the directory where the raw reports are stored. They
  should be placed inside of directories that contain the date of when the were
  gathered.
  An example of the layout of this directory is:

  ```
  yaml
  ├── 2016-01-31
  │   ├── 20121209T051845Z-MM-AS9988-dns_consistency-no_report_id-0.1.0-probe.yaml
  │   ├── 20121209T052108Z-MM-AS9988-dns_consistency-no_report_id-0.1.0-probe.yaml
  │   ├── 20121209T052248Z-MM-AS9988-dns_consistency-no_report_id-0.1.0-probe.yaml
  │   ├── 20121209T055811Z-MM-AS9988-dns_consistency-no_report_id-0.1.0-probe.yaml
  │   ├── 20121209T055945Z-MM-AS9988-dns_consistency-no_report_id-0.1.0-probe.yaml
  │   └── 20121209T060215Z-MM-AS9988-dns_consistency-no_report_id-0.1.0-probe.yaml
  ...
  ├── 2012-12-23
  │   ├── 20121222T221931Z-RU-AS57668-tcp_connect-no_report_id-0.1.0-probe.yaml
  │   ├── 20121223T155557Z-RU-AS57668-tcp_connect-no_report_id-0.1.0-probe.yaml
  │   └── 20121223T160913Z-RU-AS57668-tcp_connect-no_report_id-0.1.0-probe.yaml
  ```

  The structure of the filenames should be:
  `{timestamp}-{probe_cc}-{probe_asn}-{test_name}-{report_id}-{data_format_version}-probe.yaml`.

* `public-dir` is the directory where the sanitised reports will end up in
  nested inside of the sanitised directory.

* `private-dir` is the directory where the normalised and JSON converted report
  files will end up in.

## (Re)build ooni-pipeline

*Recommended*: Create a virtual Python instance:

`virtualenv venv`

### Start luigi server ([script](scripts/start-luigid.sh))

```
luigid --address 127.0.0.1 \
       --port 8082 --pidfile luigid.pid \
       --logdir luigid.log \
       --state-path luigi-state.pickle \
       --background
```

### Run the pipeline tasks

- Run the main (`daily_workflow`) pipeline batch tasks since 2012 in weekly
batches:

```
for year in `seq -w 12 $(date +%g)`; do
    for week in `seq -w 1 52`; do
        PYTHONPATH=${HOME}/ooni-pipeline/ luigi \
                --module pipeline.batch.daily_workflow ListReportsAndRun \
                --workers 16 \
                --ignore-asn 'AS2856 AS20712 AS5607' \
                --parallel-scheduling \
                --date-interval 20${year}-W${week}
        echo "[*] Finished processing 20${year}-W${week}"
    done
done
```

- Create the database indexes.

- Create the materialised views.

- Run the [Domain intelligence](#domain-intelligence) batch tasks.
