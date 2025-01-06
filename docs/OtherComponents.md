## Other backend components

### Nginx

Nginx <https://www.nginx.com/> is used across various servers in the
backend, primarily as a reverse proxy. It's worth summarizing the main
different uses here:

- Reverse proxy for the [API](#api)&thinsp;⚙, also providing **caching**
  from many API methods

- Serving local measurements from disk from the backend hosts

- Serving Atom/RSS feeds from disk from the backend hosts

- Serving ACME challenge text files for [Dehydrated](#dehydrated)&thinsp;⚙

- Reverse proxy for the test helpers

- Reverse proxy for deb.ooni.org

- Reverse proxy for internal or ancillary services e.g.
  [Prometheus](#tool:prometheus) scraping, [Grafana](#grafana)&thinsp;🔧
  etc

Nginx configuration files are stored in
<https://github.com/ooni/sysadmin/tree/master/ansible>

Most of the proxying functionalities of Nginx can be replaced with
[HaProxy](#haproxy)&thinsp;⚙ to benefit from load balancing and active
checks.

Caching could be provided by Varnish <https://varnish-cache.org/> as it
provides the ability to explicitly purge caches. This would be useful
when testing the API.

#### Purging Nginx cache

While testing the API it can be useful to purge the cache provide by
Nginx.

This selectively removes the cache files used for the API:

    rm /var/cache/nginx/ooni-api/* -rf

> **note**
> This method is not natively supported by Nginx. It's recommended to use
> it only on the backend testbed.

### HaProxy

HaProxy runs on the [OONI bridges](#ooni-bridges)&thinsp;⚙ and works as a
load balancer for the test helpers and the APIs on
[backend-hel.ooni.org](#host:HEL), [ams-pg-test.ooni.org](#ams-pg-test.ooni.org)&thinsp;🖥
and the bridge on [bridge-greenhost.ooni.org](#bridge-greenhost.ooni.org)&thinsp;🖥.

Contrasted to [Nginx](#nginx)&thinsp;⚙ it's focused on load balancing rather
than serving files and provides:

- dashboards showing the current status of the web services and the
  load balancing targets

- flexible active healthchecks and failover

- more detailed metrics

- more flexible routing policies that allow implementing better
  incremental rollouts, A/B testing etc

HaProxy is currently deployed on:

- [ams-pg-test.ooni.org](#ams-pg-test.ooni.org)&thinsp;🖥
  <https://ams-pg-test.ooni.org:444/__haproxy_stats>

- [backend-hel.ooni.org](#backend-hel.ooni.org)&thinsp;🖥
  <https://backend-hel.ooni.org:444/__haproxy_stats>

- [bridge-greenhost.ooni.org](#bridge-greenhost.ooni.org)&thinsp;🖥
  <https://bridge-greenhost.ooni.org:444/__haproxy_stats>

An example of the built-in dashboard:

![haproxy](../../../assets/images-backend/haproxy.png)

Also see [HaProxy dashboard](#haproxy-dashboard)&thinsp;📊.

When providing load balancing for the [Test helpers](#test-helpers)&thinsp;⚙
it uses a stateful algorithm based on the source IP address to ensure
that every given probe reaches the same test helper. This is meant to
help troubleshooting. Yet, in case a test helper becomes unreachable
probe traffic is sent to the remaining test helpers. This affects
exclusively the probes that were using the unreachable test helper. The
probes that were reaching other test helpers are not shuffled around.

### Dehydrated

Dehydrated provides Let's Encrypt certificate handling using ACME. It
replaces certbot with a simpler and more reliable implementation.

Dehydrated is configured in [Ansible](#ansible)&thinsp;🔧, see
<https://github.com/ooni/sysadmin/tree/master/ansible/roles/dehydrated>

For monitoring see [TLS certificate dashboard](#tls-certificate-dashboard)&thinsp;📊. There are
alerts configured in [Grafana](#grafana)&thinsp;🔧 to alert on expiring
certificates, see [Alerting](#alerting)&thinsp;💡.

### Jupyter Notebook

There is an instance of Jupyter Notebook <https://jupyter.org/> deployed
on the [monitoring.ooni.org](#monitoring.ooni.org)&thinsp;🖥 available for internal
use at <https://jupyter.ooni.org/tree/notebooks>

It is used primarily for:

- Performing research and data analysis using data science tools like
  [Pandas](https://pandas.pydata.org/) and
  [Altair](https://altair-viz.github.io/).

- Generating automatic dashboards using [Jupycron](#jupycron)&thinsp;🔧 and
  sending alerts.

- Analyzing logs from the
  [ClickHouse instance for logs](#clickhouse-instance-for-logs)&thinsp;⚙

> **important**
> There in no user account support in Jupyter Notebook. The instance is
> protected by HTTP basic auth using team credentials. To clarify
> ownership of notebooks put your account name as part of the notebook
> name. To prevent data loss do not modify notebooks owned by other users.

#### Ooniutils microlibrary

The following notebook is often used as a library in other notebooks:
<https://jupyter.ooni.org/notebooks/notebooks/ooniutils.ipynb>

It can be imported in other notebooks by adding this at the top:

    %run ooniutils.ipynb

> **important**
> be careful when making changes to it because it could break many
> notebooks including the ones automatically run by
> [Jupycron](#jupycron)&thinsp;🔧

Running the notebook imports commonly used libraries, including Pandas
and Altair, configures Jupyter Notebook and provides some convenience
functions:

- `click_query_fsn(query, **params)` to run queries against ClickHouse
  on [backend-fsn.ooni.org](#backend-fsn.ooni.org)&thinsp;🖥. Returns a Pandas dataframe.

- `alertmanager_fire_alert(summary, alertname, job="", instance="", annotations={}, duration_min=1)`
  to send an alert through alertmanager ([Grafana](#grafana)&thinsp;🔧).

- `send_slack_msg(title, msg, color="3AA3E3")` to send messages
  directly to [Slack](#slack)&thinsp;🔧.

- `send_alert_through_ntfy(title, msg, priority="urgent", tags="warning")`
  to send alerts directly using <https://ntfy.sh/> - see
  [Redundant notifications](#redundant-notifications)&thinsp;🔧 for details.

Confusingly, `alertmanager_fire_alert` needs an alarm duration to be set
when called.

> **note** > `send_slack_msg` can be used in addition to provide more details and
> subsequent updates to an existing alert.

Additionally, `send_slack_msg` can deliver clickable links.

> **note**
> When creating new alerts it is helpful to include full links to the
> automated notebook generating the alert and its HTML output.

See [Jupycron](#jupycron)&thinsp;🔧 for details.

#### Jupycron

Jupycron is a Python script that runs Jupyter notebooks automatically.

Various notebooks are used to perform analysing, reporting and alarming
using data science tools that are more powerful than
[Grafana](#tool:grafana) and [Prometheus](#prometheus)&thinsp;🔧 internal
query language. An example is the use of
[scikit-learn](https://scikit-learn.org)\'s machine learning for
predicting incoming measurement flow.

It is internally developed and hosted on
[github](https://github.com/ooni/jupycron.git). It is deployed by
[Ansible](#tool:ansible) on [monitoring.ooni.org](#monitoring.ooni.org)&thinsp;🖥.

It runs every minute and scans the existing notebooks at
`/var/lib/jupyter/notebooks/`. It parses only notebooks that have the
word `autorun` in the filename. (see example below) It then scans the
content of the notebook looking for a code cell that contains a
commented line like:

    # jupycron: {"every": "30 minute"}

If such line is found it executes the notebook according to the required
time interval and stores the output as an HTML file at
`/var/lib/jupyter/notebooks/jupycron`

Execution intervals can be specified using keywords:

    "min", "hour", "day", "week", "month"

> **note**
> The `AUTORUN` environment variable is set when a notebook is run under
> jupycron. Also [Ooniutils microlibrary](#ooniutils-microlibrary)&thinsp;💡 sets the
> `autorun` Python variable to `True`. This can be useful to send alerts
> only when notebooks are being run automatically.

Jupycron also provides an HTML
[summary](https://jupyter.ooni.org/view/notebooks/jupycron/summary.html)
of the existing automated notebooks.

The status column indicates the outcome of the previous run, if any:

- 🟢: successful run

- 🔴: failed run

- ⌛: never executed before

- 🛇: disabled notebook: the `# jupycron: {…​}` line was not found

> **note**
> notebooks are executed by `jupyter-nbconvert` under `systemd-run` with
> memory limits to protect the [monitoring.ooni.org](#monitoring.ooni.org)&thinsp;🖥
> host. The limit can be changed by setting a `MaxMem` key in the
> configuration line, in megabytes.

Debugging tip: Jupycron stores the history of notebook executions in
`/var/lib/jupyter/notebooks/jupycron/.history.json`.

For an example of automated notebook that sends alarm see
[Test helper failure rate notebook](#test-helper-failure-rate-notebook)&thinsp;📔

> **note**
> When a notebook is run automatically by Jupycron only the HTML output is updated.
> The notebook itself is not.

#### Test helper failure rate notebook

This automated notebook performs a correlation of test failures and the
location of [Test helpers](#test-helpers)&thinsp;⚙.

It sends alerts directly to [Slack](#slack)&thinsp;🔧.

Notebook:
<https://jupyter.ooni.org/notebooks/notebooks/autorun_test_helper_failure_rate_alarm.ipynb>

Output:
<https://jupyter.ooni.org/view/notebooks/jupycron/autorun_test_helper_failure_rate_alarm.html>

Also see the [test helpers notebook](#test-helpers-notebook)&thinsp;📔,
the [test helper rotation runbook](legacybackend/incident-management/#test-helper-rotation-runbook)&thinsp;📒 and
the [test helpers failure runbook](legacybackend/incident-management/#test-helpers-failure-runbook)&thinsp;📒

#### Test helpers notebook

This notebook provides tables and charts to investigate the general
status of the [Test helpers](#test-helpers)&thinsp;⚙

It provides a summary of the live and rotated test helpers:

![notebook](../../../assets/images-backend/test_helpers_notebook.png)

See <https://jupyter.ooni.org/notebooks/notebooks/test%20helpers.ipynb>
for investigation

Also see the [test helper rotation runbook](legacybackend/incident-management/#test-helper-rotation-runbook)&thinsp;📒 and
the [test helpers failure runbook](legacybackend/incident-management/#test-helpers-failure-runbook)&thinsp;📒

#### Android probe release notebook

This automated notebook is used to compare changes in incoming
measurements across different versions of the Android probe.

It is used in the [Android probe release runbook](#android-probe-release-runbook)&thinsp;📒

Notebook:
<https://jupyter.ooni.org/notebooks/notebooks/autorun_android_probe_release.ipynb>

Output:
<https://jupyter.ooni.org/view/notebooks/jupycron/autorun_android_probe_release.html>

#### iOS probe release notebook

This automated notebook is used to compare changes in incoming
measurements across different versions of the iOS probe.

Notebook:
<https://jupyter.ooni.org/notebooks/notebooks/autorun_ios_probe_release.ipynb>

Output:
<https://jupyter.ooni.org/view/notebooks/jupycron/autorun_ios_probe_release.html>

#### CLI probe release notebook

This automated notebook performs Used to compare changes in incoming
measurements across different versions of the CLI probe.

It is used in the [CLI probe release runbook](#cli-probe-release-runbook)&thinsp;📒

Notebook:
<https://jupyter.ooni.org/notebooks/notebooks/autorun_cli_probe_release.ipynb>

Output:
<https://jupyter.ooni.org/view/notebooks/jupycron/autorun_cli_probe_release.html>

#### Duplicate test-list URLs notebook

This automated notebook shows duplicate URLs across global and
per-country test lists

Notebook:
<https://jupyter.ooni.org/notebooks/notebooks/autorun_duplicate_test_list_urls.ipynb>

Output:
<https://jupyter.ooni.org/view/notebooks/jupycron/autorun_duplicate_test_list_urls.html>

#### Monitor blocking event detections notebook

This automated notebook monitor the
[Social media blocking event detector](#social-media-blocking-event-detector)&thinsp;⚙ creating a summary table with clickable links
to events. It also sends notification messages on [Slack](#slack)&thinsp;🔧.

Notebook:
<https://jupyter.ooni.org/notebooks/notebooks/autorun_event_detector_alerts.ipynb>

Output:
<https://jupyter.ooni.org/view/notebooks/jupycron/autorun_event_detector_alerts.html>

#### Logs from FSN notebook

This automated notebook provides summaries and examples of log analysis.
See [ClickHouse instance for logs](#clickhouse-instance-for-logs)&thinsp;⚙ for an overview.

Notebook:
<https://jupyter.ooni.org/notebooks/notebooks/autorun_fsn_logs.ipynb>

Output:
<https://jupyter.ooni.org/view/notebooks/jupycron/autorun_fsn_logs.html>

#### Logs investigation notebook

This notebook provides various examples of log analysis. See
[ClickHouse instance for logs](#clickhouse-instance-for-logs)&thinsp;⚙ for an overview.

<https://jupyter.ooni.org/notebooks/notebooks/centralized_logs.ipynb>

#### Incoming measurements prediction and alarming notebook

This automated notebook uses Sklearn to implement predictions of the
incoming measurement flow using a linear regression. It generates alarms
if incoming traffic drops below a given threshold compared to the
predicted value.

The purpose of the notebook is to detect major outages or any event
affecting ooni's infrastructure that causes significant loss in incoming
traffic.

Predictions and runs work on a hourly basis and process different probe
types independently.

Notebook:
<https://jupyter.ooni.org/notebooks/notebooks/autorun_incoming_measurements_prediction_alarming.ipynb>

Output:
<https://jupyter.ooni.org/view/notebooks/jupycron/autorun_incoming_measurements_prediction_alarming.html>

An example of measurement flow prediction:

![prediction](../../../assets/images-backend/autorun_incoming_measurements_prediction_alarming.html.png)

#### Incoming measurements prediction-by-country notebook

This automated notebook is similar to the previous one but evaluates
each country independently.

The main purpose is to detect countries encountering significant
Internet access disruption or blocking of ooni's network traffic.

The notebook is currently work-in-progress and therefore monitoring few
countries.

Notebook:
<https://jupyter.ooni.org/notebooks/notebooks/autorun_incoming_measurements_prediction_alarming_per_country.ipynb>

Output:
<https://jupyter.ooni.org/view/notebooks/jupycron/autorun_incoming_measurements_prediction_alarming_per_country.html>

#### Long term measurements prediction notebook

This automated notebook runs long-term predictions of incoming
measurement flows and alarms on significant drops.

The purpose is to detect **slow** decreases in measurements over time
that have gone unnoticed in the past in similar situations.

Notebook:
<https://jupyter.ooni.org/notebooks/notebooks/autorun_incoming_measurements_prediction_long_term_alarming.ipynb>

Output:
<https://jupyter.ooni.org/view/notebooks/jupycron/autorun_incoming_measurements_prediction_long_term_alarming.html>

#### Incoming measurements notebook

This automated notebook provides a dashboard of incoming measurement
flows grouped by probe type, from a multiple-year point of view.

Its purpose is to provide charts to be reviewed by the team to discuss
long term trends.

Notebook:
<https://jupyter.ooni.org/notebooks/notebooks/autorun_incoming_msmts.ipynb>

Output:
<https://jupyter.ooni.org/view/notebooks/jupycron/autorun_incoming_msmts.html>

#### ClickHouse queries notebook

This is a non-automated notebook used to summarize heavy queries in
[ClickHouse](#clickhouse)&thinsp;⚙

<https://jupyter.ooni.org/notebooks/notebooks/2023%20%5Bfederico%5D%20clickhouse%20query%20log.ipynb>

> **note**
> The `system.query_log` table grows continuously and might be trimmed or
> emptied using `TRUNCATE` to free disk space.

#### Priorities and weights notebook

Notebooks to investigate prioritization. See
[Priorities and weights](#priorities-and-weights)&thinsp;💡

<https://jupyter.ooni.org/notebooks/notebooks/2022%20test-list%20URL%20input%20prioritization%20dashboard.ipynb>

<https://jupyter.ooni.org/notebooks/notebooks/2022%20test-list%20URL%20input%20prioritization%20experiments.ipynb>

#### Campaign investigation notebook

A test campaign has been monitored with the following notebook. It could
be tweaked and improved for other campaigns.
To reuse it copy it to a new notebook and update the queries. Rerun all cells.
The notebook will show how the measurement quantity and coverage increased.

<https://jupyter.ooni.org/notebooks/notebooks/2023-05-18%20TL%20campaign.ipynb>

#### Easy charting notebook

This notebook contains examples that can be used as building blocks for various
investigations and dashboards.

It provides the `easy_msm_count_chart` helper function.
Such functions shows measurement counts over time, grouped over a dimension.

By default it shows maximum 6 different values (color bands).
This means you are not seeing the total amount of measurements in the charts.

You can add the following parameters, all optional:

- `title`: free-form title
- `since`: when to start, defaults to "3 months". You can use day, week, month, year
- `until`: when to stop, defaults to now. You can use day, week, month, year
- `granularity`: how big is each time slice: day, week, month. Defaults to day
- `dimension`: what dimension to show as different color bands. Defaults to `software_version`
- `dimension_limit`: how many values to show as different color bands. **Defaults to 6.**

The following parameters add filtering. The names should be self explanatory.
The default value is no filter (count everything).

- `filter_software_name`: looks only at measurement for a given software name, e.g. "ooniprobe-android".
- `filter_domain`
- `filter_engine_name`
- `filter_input`
- `filter_probe_asn`
- `filter_probe_cc`
- `filter_test_name`

<https://jupyter.ooni.org/notebooks/notebooks/easy_charts.ipynb>

### Grafana

Grafana <https://grafana.com/> is a popular platform for monitoring and
alarming.

It is deployed on [monitoring.ooni.org](#monitoring.ooni.org)&thinsp;🖥 by
[Ansible](#ansible)&thinsp;🔧 and lives at <https://grafana.ooni.org/>

See [Grafana backup runbook](#grafana-backup-runbook)&thinsp;📒 and
[Grafana editing](#grafana-editing)&thinsp;📒

### ClickHouse instance for logs

There is an instance of ClickHouse deployed on
[monitoring.ooni.org](#monitoring.ooni.org)&thinsp;🖥 that receives logs. See
[Log management](#log-management)&thinsp;💡 for details on logging in general.

See [Logs from FSN notebook](#logs-from-fsn-notebook)&thinsp;📔 and
[Logs investigation notebook](#logs-investigation-notebook)&thinsp;📔 for examples on how to query the `logs` table to
extract logs and generate charts.

> **note**
> The `logs` table on [monitoring.ooni.org](#monitoring.ooni.org)&thinsp;🖥 is indexed
> by `__REALTIME_TIMESTAMP`. It can be used for fast ordering and
> filtering by time.

An example of a simple query to show recent logs:

```sql
SELECT timestamp, _SYSTEMD_UNIT, message
FROM logs
WHERE host = 'backend-fsn'
AND __REALTIME_TIMESTAMP > toUnixTimestamp(NOW('UTC') - INTERVAL 1 minute) * 1000000)
ORDER BY __REALTIME_TIMESTAMP DESC
LIMIT 10
```

### Vector

Vector <https://vector.dev> is a log (and metric) management tool. See
[Log management](#log-management)&thinsp;💡 for details.

> **important**
> Vector is not packaged in Debian yet. See
> <https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=1019316> Vector is
> currently installed using a 3rd party APT archive.

### ClickHouse

ClickHouse is main database that stores measurements and many other
tables. It accessed primarily by the [API](#api)&thinsp;⚙ and the
[Fastpath](#fastpath)&thinsp;⚙.

It is an OLAP, columnar database. For documentation see
<https://clickhouse.com/docs/en/intro>

The database schema required by the API is stored in:
<https://github.com/ooni/backend/blob/0ec9fba0eb9c4c440dcb7456f2aab529561104ae/api/tests/integ/clickhouse_1_schema.sql>

ClickHouse is deployed by [Ansible](#ansible)&thinsp;🔧 as part of the
deploy-backend.yml playbook. It is installed using an APT archive from
the developers and

Related: [Database backup tool](#database-backup-tool)&thinsp;⚙
