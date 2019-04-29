This document describes how to reprocess historical data ingesting new features while minimizing resources waste and negative effect on the on-going data processing.

This document is valid as of March 2019.

Reading [overall pipeline design document](./pipeline-16.10.md) is useful to understand the following text.

## Preface

There are a few problems that make reingestion and reprocessing a non-instant and non-trivial process:

- reprocessing **all** the data is slow: fresh data is ingested at ~1.0 MByte/s. Throughput is measured per CPU core processing autoclaved files. So at least ~46 CPU-days are needed to ingest 3.8 TB dataset + PostgreSQL [may double](https://github.com/ooni/pipeline/issues/140) that estimate.
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

Then HIT should be solved to extract a fingerprint for the blockpage. The fingerprint should be added to the set of fingerprints and `openobservatory/pipeline-shovel` should be rolled out before reprocessing of historical data.

If the blockpage is a static one, there is a fast-path alternative to reprocessing: it's possible to update MetaDB directly without actual reprocessing as SHA256 collision is very unlikely and `body_sha256` may be used as a feature _identifying_ the blockpage server (at the current stage of OONI Methodology development). See feature-based fingerprint case for more on the fast-path.

In case of dynamic blockpage, there is a possibility to *estimate* the set of affected measurements limiting the number of autoclaved files to reprocess.

TBD: case with -- body_sha256 = '\x833b2fb8887eed1c0d496670148efa8b6a6e65b89f8df42dbd716464e3cf47a6'

## Case: new feature-based fingerprint

The goal of special handling of feature-based case is that the case does not depend on voluminous HTTP bodies. So the flags for the dataset can be updated within couple of hours given quite modest computing resources (4 vCPU, 16 GiB RAM, HDD) compared to ≈46 CPU-days needed ingest whole dataset from scratch.

Examples are `Location` redirects and DNS-based redirects to blockpage servers.

E.g. aforementioned [homeline.kg ISP](https://explorer.ooni.torproject.org/measurement/20180126T000430Z_AS8449_pk15Mr2LgOhNOk9NfI2EarhUAM64DZ3R85nh4Z3q2m56hflUGh?input=http:%2F%2Farchive.org) actually serves redirect for a blocked http URI with no `Date` and no `Server` headers that clearly looks like injected HTTP redirect.

This case is almost the same one as the case of a static blockpage: the MetaDB has all the data to follow fast-path updating measurement metadata (`http_request_fp` table, `confirmed` and `anomaly` flags, etc.) with direct DB queries. The downside of fast-path is that it'll lead to duplication of logic between the queries and `centrifugation.py` that may (by mistake) lead to inconsistencies if the logic is not perfectly equivalent.

Overall steps needed to mark existing & future measurements are:

- pause ongoing ingestion and ensure that there are no `meta_pg` TaskInstances running
- update `fingerprint` table in [the database schema](https://github.com/ooni/pipeline/blob/master/af/oometa/) following [an example](https://github.com/ooni/pipeline/blob/master/af/oometa/003-fingerprints.install.sql#L31-L62) and [roll it out](https://github.com/ooni/sysadmin/blob/master/ansible/deploy-pipeline-ddl.yml). The fingerprints are stored in the schema to generate `fingerprint_no serial`.
- create a temporary table having `msm_no` of the measurements matching the fingerprint _perfectly_ according to features existing in database (e.g. `select msm_no from http_request where headers->>'Location' = 'http://homeline.kg/access/blockpage.html'`, keep in mind that keys of headers are case-sensitive)
- insert those `msm_no` together with matching `fingerprint_no` into `http_request_fp` table as if those were actually ingested by `centrifugation.py`
- update `anomaly` and `confirmed` flags in `measurement` table for the affected measurement according to the logic codified in `calc_measurement_flags()`
- update `fingerprint` table checksum in `HttpRequestFPFeeder.__init__()` in `centrifugation.py` and roll out `openobservatory/pipeline-shovel` (there is no need to bump `CODE_VER` for feature-based fingerprints as we are 100% confident that reprocessing is not needed and ongoing data processing is paused)
- unpause data ingestion

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

TBD.

## GNU Make crutch for Airflow

TBD.
