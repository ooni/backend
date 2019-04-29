This document describes how to reprocess historical data ingesting new features while minimizing resources waste and negative effect on the on-going data processing.

This document is valid as of May 2019.

Reading [overall pipeline design document](./pipeline-16.10.md) is useful to understand the following text.

## Preface

There are a few problems that make reingestion and reprocessing a non-instant and non-trivial process:

- reprocessing **all** the data is slow: fresh data is ingested at ≈1.0 MByte/s. Throughput is measured per CPU core processing autoclaved files. So at least ≈46 CPU-days are needed to ingest 3.8 TB dataset + PostgreSQL [may double](https://github.com/ooni/pipeline/issues/140) that estimate.
- rewriting **all** feature tables on reprocessing produces unnecessary _PostgreSQL table bloat_. Features are deleted from feature tables on reprocessing and re-inserted back instead of the minimal possible update to avoid mistakes caused by incremental computation. Full-bucket _update_ is equivalent to _delete + insert_ as that's the way for PostgreSQL to implement MVCC.
- airflow 1.8 scheduler fails to schedule tasks properly when 2'300 DAGs are started at once to reprocess all the buckets. It starts hogging CPU, that negatively affects both reprocessing speed and ingestion of new data.

There are a few hacks that make reingestion and reprocessing more "instant" in various cases:

- minimal reprocessing "unit" is an autoclaved file that is 20 MB on average instead of 5.5 GB bucket.
- `code_ver` allows to reprocess files updating just a subset of feature-tables according to `min_compat_code_ver` instead of updating all of them.
- `body_sha256`, `body_simhash` and `body_text_simhash` allow to select a subset of autoclaved files for reprocessing when new blockpage fingerprint is discovered.
- GNU Make can be used to [run airflow tasks](https://github.com/ooni/sysadmin/blob/8224b4627dd2e16529b98f9907f0fbd280814035/scripts/pipeline-reprocess) with pre-defined concurrency level to limit pressure on Airflow's scheduler.
- `SimhashCache` fetches subset of `sha256(body)` to `simhash(text(body)), simhash(body)` mapping from the MetaDB before reingestion, that speeds reingestion up from 1.0 MB/s to 4.3 MB/s
- one-pass ingestion of streamed json input into _separate_ tables is not trivial. It's achieved maintaining [write buffer](https://github.com/ooni/pipeline/blob/1b2688d75a7abc09e446a7d965dd8011f5b5564d/af/shovel/oonipl/pg.py) for each table and flushing the buffer with `COPY` when few megabytes of data are accumulated.

Currently following fingerprints to _"confirm"_ cases of network interference are implemented: HTTP Body substring, HTTP Header prefix, HTTP Header value. NB: HTTP Bodies are _not_ stored in the MetaDB, so those are not feature-based fingerprints.

## Case: new HTML blockpage fingerprint

Identify new blockpage, e.g. one from [homeline.kg ISP](https://explorer.ooni.torproject.org/measurement/20180126T000430Z_AS8449_pk15Mr2LgOhNOk9NfI2EarhUAM64DZ3R85nh4Z3q2m56hflUGh?input=http:%2F%2Farchive.org) coming from [#122](https://github.com/ooni/pipeline/issues/122).

Identify corresponding measurement and `msm_no`, e.g. with `select * from report join measurement using (report_no) join input using (input_no) where report_id = '20180126T000430Z_AS8449_pk15Mr2LgOhNOk9NfI2EarhUAM64DZ3R85nh4Z3q2m56hflUGh' and input = 'http://archive.org'`.

Identify, if possible, if the blockpage is a _static_ or a _dynamic_ one. Static page usually does not include URL of blocked page in HTML body while dynamic does. For a static blockpage `body_sha256` can be reliably used to identify all the measurements referencing it. For a dynamic blockpage low hamming distance between the blockpage and `body_simhash` (or `body_text_simhash`) of the measurement can be used to reliably identify most of the candidates containing the blockpage. E.g. [Cloudflare blockpage cluster](https://gist.github.com/darkk/e2b2762c4fe053a3cf8a299520f0490e) (see `In[18]`) has diameter of 15 for 64-bit `body_simhash`. ISP blockpages are often static as it's significantly cheaper to serve them from computational perspective. CDN server-side blockpages are often dynamic as they include some small bits of tracking those are useful for customer support.

Sidenote: having a blockpage at hand is an opportunity to mine blocked URLs showing same blockpage and mine more blockpages, as different ISPs may show different blockpage for the same blocked URL.

Then _human intelligence task_ should be solved to extract a fingerprint for the blockpage. The fingerprint should be added to the set of fingerprints and `openobservatory/pipeline-shovel` should be rolled out before reprocessing of historical data.

If the blockpage is a static one, there is a fast-path alternative to reprocessing: it's possible to update MetaDB directly without actual reprocessing as SHA256 collision is very unlikely and `body_sha256` may be used as a feature _identifying_ the blockpage server (at the current stage of OONI Methodology development). See feature-based fingerprint case for more on the fast-path. Keep in mind that the HTTP Body substring fingerprint is still _derived_ from the body, so avoiding full-dataset reprocessing may lead to false negatives.

Overall steps needed to mark existing & future measurements are:

- pause ongoing ingestion and ensure that there are no `meta_pg` TaskInstances running
- update `fingerprint` table in [the database schema](https://github.com/ooni/pipeline/blob/065cccdfeb531e93a22d2aacc05ec05e990f99ee/af/oometa/) following [an example](https://github.com/ooni/pipeline/blob/065cccdfeb531e93a22d2aacc05ec05e990f99ee/af/oometa/003-fingerprints.install.sql#L31-L62) and [roll it out](https://github.com/ooni/sysadmin/blob/4defab8e92a2e53e2679a17214162ed058089e7f/ansible/deploy-pipeline-ddl.yml). The fingerprints are stored in the schema to generate `fingerprint_no serial`.
- create a temporary table having `msm_no` of the measurements matching the fingerprint _with confidence_ according to the _derived_ features existing in database (e.g. `select msm_no from http_request where body_sha256 = '\x833b2fb8887eed1c0d496670148efa8b6a6e65b89f8df42dbd716464e3cf47a6'` for static blockpages)
- insert those `msm_no` together with matching `fingerprint_no` into `http_request_fp` table as if those were actually ingested by `centrifugation.py`
- update `anomaly` and `confirmed` flags in `measurement` table for the affected measurement according to the logic codified in `calc_measurement_flags()`
- update `centrifugation.py`: 1) set up-to-date `fingerprint` table checksum in `HttpRequestFPFeeder.__init__()`, 2) bump global `CODE_VER` and `HttpRequestFPFeeder.min_compat_code_ver` (and only it, to avoid rewriting other tables)
- roll out `openobservatory/pipeline-shovel` and unpause data ingestion
- reprocess all the previous buckets under GNU Make control

It's possible to try to use `body_simhash` to reprocess _likely-affected_ buckets first to reduce time-to-publication latency, but that's out of the scope of the document.

## Case: new feature-based fingerprint

The goal of special handling of feature-based case is that the case does not depend on voluminous HTTP bodies. So the flags for the dataset can be updated within couple of hours given quite modest computing resources (4 vCPU, 16 GiB RAM, HDD) compared to ≈46 CPU-days needed ingest whole dataset from scratch.

Examples are `Location` redirects and DNS-based redirects to blockpage servers.

E.g. aforementioned [homeline.kg ISP](https://explorer.ooni.torproject.org/measurement/20180126T000430Z_AS8449_pk15Mr2LgOhNOk9NfI2EarhUAM64DZ3R85nh4Z3q2m56hflUGh?input=http:%2F%2Farchive.org) actually serves redirect for a blocked http URI with no `Date` and no `Server` headers that clearly looks like injected HTTP redirect.

This case is almost the same one as the case of a static blockpage: the MetaDB has all the data to follow fast-path updating measurement metadata (`http_request_fp` table, `confirmed` and `anomaly` flags, etc.) with direct DB queries. The downside of fast-path is that it'll lead to duplication of logic between the queries and `centrifugation.py` that may (by mistake) lead to inconsistencies if the logic is not perfectly equivalent.

Overall steps needed to mark existing & future measurements are the same as for HTML blockpage fingerprint with small alterations:

- _(same)_ pause ongoing ingestion and ensure that there are no `meta_pg` TaskInstances running
- _(same)_ update `fingerprint` table in [the database schema](https://github.com/ooni/pipeline/blob/065cccdfeb531e93a22d2aacc05ec05e990f99ee/af/oometa/) following [an example](https://github.com/ooni/pipeline/blob/065cccdfeb531e93a22d2aacc05ec05e990f99ee/af/oometa/003-fingerprints.install.sql#L31-L62) and [roll it out](https://github.com/ooni/sysadmin/blob/4defab8e92a2e53e2679a17214162ed058089e7f/ansible/deploy-pipeline-ddl.yml). The fingerprints are stored in the schema to generate `fingerprint_no serial`.
- create a temporary table having `msm_no` of the measurements matching the fingerprint _perfectly_ according to features existing in database (e.g. `select msm_no from http_request where headers->>'Location' = 'http://homeline.kg/access/blockpage.html'`, keep in mind that keys of headers are case-sensitive)
- _(same)_ insert those `msm_no` together with matching `fingerprint_no` into `http_request_fp` table as if those were actually ingested by `centrifugation.py`
- _(same)_ update `anomaly` and `confirmed` flags in `measurement` table for the affected measurement according to the logic codified in `calc_measurement_flags()`
- update `centrifugation.py`: set up-to-date `fingerprint` table checksum in `HttpRequestFPFeeder.__init__()`. There is no need to bump `CODE_VER` for feature-based fingerprints as we are 100% confident that reprocessing is not needed and ongoing data processing is paused.
- _(same)_ roll out `openobservatory/pipeline-shovel` and unpause data ingestion
- there is no need for reprocessing as there is no possibility for false negative here

_A temporary table_ is not necessary a result of `CREATE TEMPORARY TABLE`, it may also be a query executed on a read-only replica with faster disk drives with the output of the query directed to a local file that becomes `UNLOGGED` table on a master via out-of-band data transfer or via _Foreign Data Wrapper_.

Unfortunately, it's not trivial to give a concrete example of the queries as these examples have to be kept in-sync with the rest of the code and, what's more important, different cardinality of the tables may need different strategies for UPDATE. E.g. [CREATE TABLE + rename](https://github.com/ooni/pipeline/pull/144#issuecomment-483365330) strategy may be order of magnitude more performant than `UPDATE` when the UPDATE touches _many_ rows (it was touching ≈5% of rows in the case).

## Case: new feature table

The rule of thumb is: if you are not going to use the extracted features for search or aggregation, you should rather consider leaving JSON as-is without bloating the MetaDB. Maintained table should be an asset, not just a liability of maintenance for the sake of maintenance.

One may want to use [commit adding `vanilla_tor` stats](https://github.com/ooni/pipeline/commit/902e6751340dd515096214f74c739751c9ddca55) for inspiration, but the code evolved a bit since than.

- Add new feature table. Avoid foreign keys, those are very slow to verify during batch ingestion (as of PostgreSQL 9.6).
- Bump `CODE_VER`, set `min_compat_code_ver` for the new feeder
- `TheFeeder.row()` creates a string that is suitable for sending to the table via `COPY`
- `TheFeeder.pop()` removes fields from the JSON object those are completely ingested by the feeder and should NOT be considered a part of the _residual_
- test, deploy, reprocess all (or the affected) buckets under GNU Make control

One may save significant amount of CPU time marking old _autoclaved_ files as already processed by the new version of code bumping their corresponding `code_ver` in the database. It may be useful in a case when a feature has to be extracted **only(!)** from a known subset of reports, so the reports that have no data on the specific feature may be skipped safely. Example is extracting a feature of a "low-volume" test. E.g. `web_connectivity` test takes 99.4% of data volume of 2019Q1, so _any_ other test is a low-volume one. Another example is a extracting a feature that was shipped as a part of some specific `software` version, so `autoclaved` having no records coming from the new software may be manually labeled with a newer `code_ver` and skipped safely.

## Case: adding new feature to existing table

Let's use [commit adding `body_simhash` extraction](https://github.com/ooni/pipeline/commit/8e14b20ec368572c0bb831fb958bcc70eb9108a6) as an example. Things to do are the following:

- Add new feature as a nullable column. Adding a `NOT NULL` column will trigger an early table rewrite that is waste of CPU and Disk IO bandwidth.
- Bump `CODE_VER`
- Bump `min_compat_code_ver` to the new value of `CODE_VER` for affected "feeders" (`HttpRequestFeeder` and `HttpControlFeeder` in this case)
- Append new feature columns to `columns`
- Write code to extract the needed feature for `TheFeeder.row()`, drop those fields in `TheFeeder.pop()` (if needed), test it and deploy.
- Reprocess all (or the affected) buckets under GNU Make control.
- Alter the feature column to be `NOT NULL` if needed.

## Marking autoclaved files for reprocessing

The _autoclaved_ files are selected for reingestion and reprocessing based on their `code_ver`. If `autoclaved.code_ver` matches `centrifugation.py:CODE_VER` then the file is skipped altogether (file is not read and decompressed, json is not parsed). If `autoclaved.code_ver` is _compatible_ with `Feeder.min_compat_code_ver` (greater-equal-than) then the corresponding PostgreSQL table is not re-written during a centrifugation pass. So it can be used to reduce amount of burned CPU and database disk IO.

_autoclaved_ file may be marked with `code_ver` equal to 0 (`CODE_VER_REPROCESS`) to force reprocessing of all the feature-tables for this file. There should be no reasons for that besides, maybe, clean-up after a manual database modifications.

Reingestion is different from reprocessing as it may handle changes to autoclaved files themselves and update `autoclaved`, `report`, `measurement` tables accordingly. The easiest way to force reingestion manually is to set `autoclaved.file_sha1` to all-zeros of something like `digest('', 'sha1')`. One of the possible reasons for that is [report deletion](./delete-report.md).

## GNU Make crutch for Airflow

Airflow has an issue in a scheduler, it starts consuming unreasonable amount of resources if there are thousands of _running_ DAGs. So, reprocessing of ≈2300 daily buckets of OONI data has to be micro-managed. One of the usual Linux tools to execute parallel processes is GNU Make, so, it was taken for the [`pipeline-reprocess`](https://github.com/ooni/sysadmin/blob/4defab8e92a2e53e2679a17214162ed058089e7f/scripts/pipeline-reprocess) script.

The way to use the script is the following:

- download it to your $HOME at `datacollector.infra.ooni.io` running Airflow
- edit `PRJ` with a slug representing a reprocessing session
- choose a way to list buckets-to-reprocess with `TYPEOF_DEPS`
- edit `$(PRJ)/...-deps` to reflect the desired logic to select buckets to reprocess
- run `tmux` and `./pipeline-reprocess reprocess` within tmux session

The script will execute TaskInstances via `airflow run` one-by-one within predefined concurrency limits.
