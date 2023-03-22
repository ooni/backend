
# The blocking event detector is meant to run frequently in order to
# provide fast response to events.
# As the amount of probes and measuraments increases, extracting all the
# required data for multiple inputs/CCs/ASNs and past weeks/months could
# become too CPU and memory-intensive for the database and the detector.
# Therefore we run the detection on the database side as much as possible.
# The current version uses moving averages stored in a status table
# `blocking_status`.
# Detection is performed on test_name+probe_cc+probe_asn+input aka "TCAI"
# following query. It's easier to read the query from the bottom up:
#  - Select data from the fastpath table for the last time window, counting
#    the percentages of confirmed, anomaly-but-not-confirmed etc. --> As "new"
#  - Select stored related moving averages etc. from blocking_status.
#    FINAL is required to avoid duplicates due to table updates.
#  - Join the two queries on TCAI
#  - Run SELECT to compute new values:
#    - The empty(blocking_status... parts are simply picking the right
#      value in case the entry is missing from blocking_status (TCAI never
#      seen before) or not in fastpath (no recent msmts for a given TCAI)
#    - Weighted percentages e.g.
#      (new_confirmed_perc * msmt count * μ + stored_perc * blocking_status.cnt * 𝜏) / totcnt
#      Where: 𝜏 < 1, μ = 1 - t  are used to combine old vs new values,
#       blocking_status.cnt is an averaged count of seen msmts representing how
#       "meaningful" the confirmed percentage in the blocking_status table is.
#    - Stability: compares the current and stored accessible/ confirmed/etc
#        percentage. 1 if there is no change, 0 for maximally fast change.
#        (Initialized as 0 for new TCAI)
#  - Then run another SELECT to:
#    - Set `status` based on accessible thresholds and stability
#      We don't want to trigger a spurius change if accessibility rates
#      floating a lot.
#    - Set `change` if the detected status is different from the past
#  - INSERT: Finally store the TCAI, the moving averages, msmt count, change,
#    stability in blocking_status to use it in the next cycle.
#
#  As the INSERT does not returns the rows, we select them in extract_changes
#  (with FINAL) to record them into `blocking_events`.
#  If there are changes we then extract the whole history for each changed
#  TCAI in rebuild_feeds.


# Unused
def run_detection_sql(start_date, end_date, services) -> None:
    if not conf.reprocess:
        log.info(f"Running detection from {start_date} to {end_date}")

    if 0 and conf.reprocess:
        # Used for debugging
        sql = """SELECT count() AS cnt FROM fastpath
    WHERE test_name IN ['web_connectivity']
    AND msm_failure = 'f'
    AND measurement_start_time >= %(start_date)s
    AND measurement_start_time < %(end_date)s
    AND probe_asn = 135300 and probe_cc = 'MM' AND input = 'https://twitter.com/'
        """
        d = dict(start_date=start_date, end_date=end_date)
        log_example = bool(query(sql, d)[0][0])

    # FIXME:   new.cnt * %(mu)f + blocking_status.cnt * %(tau)f AS totcnt
    sql = """
INSERT INTO blocking_status (test_name, input, probe_cc, probe_asn,
  confirmed_perc, pure_anomaly_perc, accessible_perc, cnt, status, old_status, change, stability)
SELECT test_name, input, probe_cc, probe_asn,
  confirmed_perc, pure_anomaly_perc, accessible_perc, movingcnt AS cnt,
  multiIf(
    accessible_perc < 80 AND stability > 0.95, 'BLOCKED',
    accessible_perc > 95 AND stability > 0.97, 'OK',
    x.status)
  AS status,
  x.status AS old_status,
  if(status = x.status, x.change * %(tau)f, 1) AS change,
  stability
FROM
(
SELECT
 empty(blocking_status.test_name) ? new.test_name : blocking_status.test_name AS test_name,
 empty(blocking_status.input) ? new.input : blocking_status.input AS input,
 empty(blocking_status.probe_cc) ? new.probe_cc : blocking_status.probe_cc AS probe_cc,
 (blocking_status.probe_asn = 0) ? new.probe_asn : blocking_status.probe_asn AS probe_asn,
 new.cnt * %(mu)f + blocking_status.cnt * %(tau)f AS movingcnt,
 blocking_status.status,
 blocking_status.change,
 new.cnt + blocking_status.cnt AS totcnt,
 new.confirmed_perc    * new.cnt/totcnt * %(mu)f + blocking_status.confirmed_perc    * blocking_status.cnt/totcnt * %(tau)f AS confirmed_perc,
 new.pure_anomaly_perc * new.cnt/totcnt * %(mu)f + blocking_status.pure_anomaly_perc * blocking_status.cnt/totcnt * %(tau)f AS pure_anomaly_perc,
 new.accessible_perc   * new.cnt/totcnt * %(mu)f + blocking_status.accessible_perc   * blocking_status.cnt/totcnt * %(tau)f AS accessible_perc,
 if(new.cnt > 0,
  cos(3.14/2*(new.accessible_perc - blocking_status.accessible_perc)/100) * 0.7 + blocking_status.stability * 0.3,
  blocking_status.stability) AS stability

FROM blocking_status FINAL

FULL OUTER JOIN
(
 SELECT test_name, input, probe_cc, probe_asn,
  countIf(confirmed = 't') * 100 / cnt AS confirmed_perc,
  countIf(anomaly = 't') * 100 / cnt - confirmed_perc AS pure_anomaly_perc,
  countIf(anomaly = 'f') * 100 / cnt AS accessible_perc,
  count() AS cnt,
  0 AS stability
 FROM fastpath
 WHERE test_name IN ['web_connectivity']
 AND msm_failure = 'f'
 AND measurement_start_time >= %(start_date)s
 AND measurement_start_time < %(end_date)s
 AND input IN %(urls)s

 AND input IN 'https://twitter.com/'
 AND probe_cc = 'RU'
 AND probe_asn = 12389

 GROUP BY test_name, input, probe_cc, probe_asn
) AS new

ON
 new.input = blocking_status.input
 AND new.probe_cc = blocking_status.probe_cc
 AND new.probe_asn = blocking_status.probe_asn
 AND new.test_name = blocking_status.test_name
) AS x
"""
    tau = 0.985
    mu = 1 - tau
    urls = sorted(set(u for urls in services.values() for u in urls))
    d = dict(start_date=start_date, end_date=end_date, tau=tau, mu=mu, urls=urls)
    query(sql, d)

    if 0 and conf.reprocess and log_example:
        sql = """SELECT accessible_perc, cnt, status, stability FROM blocking_status FINAL
        WHERE probe_asn = 135300 and probe_cc = 'MM' AND input = 'https://twitter.com/'
        """
        it = list(query(sql)[0])
        it.append(str(start_date))
        print(repr(it) + ",")

# unused
def process_historical_data_nopandas(start_date, end_date, interval, services):
    """Process past data"""
    run_date = start_date + interval
    rebuild_status(click, start_date, run_date, services)

    dates = []
    while run_date < end_date:
        dates.append(run_date)
        run_date += interval

    for run_date in tqdm(dates):
        run_detection_sql(run_date, run_date + interval, services)
        changes = extract_changes(run_date)
        if changes:
            rebuild_feeds(changes)

    log.debug("Done")
    log.info(
        (
            "blocking_status row count",
            query("SELECT count() FROM blocking_status FINAL")[0],
        )
    )

@metrics.timer("rebuild_status")
def rebuild_status(click, start_date, end_date, services) -> None:
    log.info("Truncate blocking_status")
    sql = "TRUNCATE TABLE blocking_status"
    query(sql)

    log.info("Truncate blocking_events")
    sql = "TRUNCATE TABLE blocking_events"
    query(sql)

    log.info("Fill status")
    sql = """
INSERT INTO blocking_status (test_name, input, probe_cc, probe_asn,
  confirmed_perc, pure_anomaly_perc, accessible_perc, cnt, status)
  SELECT
    test_name,
    input,
    probe_cc,
    probe_asn,
    (countIf(confirmed = 't') * 100) / cnt AS confirmed_perc,
    ((countIf(anomaly = 't') * 100) / cnt) - confirmed_perc AS pure_anomaly_perc,
    (countIf(anomaly = 'f') * 100) / cnt AS accessible_perc,
    count() AS cnt,
    multiIf(
        accessible_perc < 70, 'BLOCKED',
        accessible_perc > 90, 'OK',
        'UNKNOWN')
    AS status
FROM fastpath
WHERE test_name IN ['web_connectivity']
AND msm_failure = 'f'
AND input IN %(urls)s
AND measurement_start_time >= %(start_date)s
AND measurement_start_time < %(end_date)s

 AND input IN 'https://twitter.com/'
 AND probe_cc = 'RU'
 AND probe_asn = 12389

GROUP BY test_name, input, probe_cc, probe_asn;
"""
    urls = sorted(set(u for urls in services.values() for u in urls))
    query(sql, dict(start_date=start_date, end_date=end_date, urls=urls))
    log.info("Fill done")


@metrics.timer("extract_changes")
def extract_changes(run_date):
    """Scan the blocking_status table for changes and insert them into
    the blocking_events table.
    """
    sql = """
    INSERT INTO blocking_events (test_name, input, probe_cc, probe_asn, status,
    time)
    SELECT test_name, input, probe_cc, probe_asn, status, %(t)s AS time
    FROM blocking_status FINAL
    WHERE status != old_status
    AND old_status != ''
    """
    query(sql, dict(t=run_date))

    # TODO: simplify?
    # https://github.com/mymarilyn/clickhouse-driver/issues/221
    sql = """
    SELECT test_name, input, probe_cc, probe_asn
    FROM blocking_status FINAL
    WHERE status != old_status
    AND old_status != ''
    """
    changes = query(sql, dict(t=run_date))

    # Debugging
    sql = """SELECT test_name, input, probe_cc, probe_asn, old_status, status
    FROM blocking_status FINAL
    WHERE status != old_status
    AND old_status != ''
    AND probe_asn = 135300 and probe_cc = 'MM' AND input = 'https://twitter.com/'
    """
    if conf.reprocess:
        li = query(sql)
        for tn, inp, cc, asn, old_status, status in li:
            log.info(f"{run_date} {old_status} -> {status} in {cc} {asn} {inp}")

    return changes


