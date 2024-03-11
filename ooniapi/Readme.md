# OONI API

Welcome to the new OONI API!

This is still work in progress, but the end goal is to eventually reach feature
parity with backend/api/ (aka legacy flask based API).

The general idea is to break OONI API components into smaller pieces that can
be more easily deployed and managed without worrying too much about the blast
radius caused by the deployment of a larger component.

To this end, we divide the OONI API sub-components into what we call
"services".

Each service (found in the `ooniapi/services` folder) should have a narrowly
defined scope. It's optimal to slice services up depending on how critical they
are (tier0, tier1, tier2) and what kinds of resources they need to access
(databases, object store, specific hosts, etc.).

There is also a `common` folder for all shared logic common to every component.

## List of OONI API Services

### Tier0
* `ooniprobe`, (aka `probe_services`), where probes send their measurements and
  get metadata to run experiments.
* `oonirun`, CRUD for editing OONI Run links, but also for probes to get the
  descriptors and run tests (this fact is what makes it tier0)

### Tier1
* `data`, (aka OONI Data Kraken), where Explorer and other clients access the
  observations data and experiment results.
* `findings`, (aka `incidents`) backend for findings pages on explorer
* `measurements`, backend for aggregation and list measurement endpoints (note
  also probe uses this, so it's maybe on the high end of tier1)

### Tier2
* `testlists`, backend for test-lists.ooni.org

## Developer setup

We use `hatch` for managing development environments. Once you have [installed
hatch](https://hatch.pypa.io/1.9/install/), check the `Makefile` for service
specific commands.

Generally it should work something like:
```
make test
make run
```
