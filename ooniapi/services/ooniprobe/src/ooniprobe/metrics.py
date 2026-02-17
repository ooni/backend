from prometheus_client import Counter, Info, Gauge


class Metrics:
    # -- < Measurement submission > ------------------------------------
    MSMNT_DISCARD_ASN0 = Counter(
        "receive_measurement_discard_asn_0",
        "How many measurements were discarded due to probe_asn == ASN0",
    )

    MSMNT_DISCARD_CC_ZZ = Counter(
        "receive_measurement_discard_cc_zz",
        "How many measurements were discarded due to probe_cc == ZZ",
    )

    MSMNT_RECEIVED_CNT = Counter(
        "receive_measurement_count",
        "Count of incomming measurements",
    )

    PROBE_CC_ASN_MATCH = Counter(
        "probe_cc_asn_match",
        "How many matches between reported and observed probe_cc and asn",
    )

    PROBE_CC_ASN_NO_MATCH = Counter(
        "probe_cc_asn_nomatch",
        "How many mismatches between reported and observed probe_cc and asn",
        labelnames=["mismatch"],
    )

    MISSED_MSMNTS = Counter(
        "missed_msmnts", "Measurements that failed to be sent to the fast path."
    )

    SEND_FASTPATH_FAILURE = Counter(
        "measurement_fastpath_send_failure_count",
        "How many times ooniprobe failed to send a measurement to fastpath",
    )

    SEND_S3_FAILURE = Counter(
        "measurement_s3_upload_failure_count",
        "How many times ooniprobe failed to send a measurement to s3. "
        "Measurements are sent to s3 when they can't be sent to the fastpath",
    )

    # -- < Probe services > ----------------------------------------------------
    PROBE_LOGIN = Counter(
        "probe_login_requests",
        "Requests made to the probe login endpoint",
        labelnames=["state", "detail", "login"],
    )

    PROBE_UPDATE_INFO = Info(
        "probe_update_info",
        "Information reported in the probe update endpoint",
    )

    CHECK_IN_TEST_LIST_COUNT = Gauge(
        "check_in_test_list_count", "Amount of test lists present in each experiment"
    )

    GEOIP_ADDR_FOUND = Counter(
        "geoip_ipaddr_found",
        "If the ip address was found by geoip",
        labelnames=["probe_cc", "asn"],
    )

    GEOIP_ADDR_NOT_FOUND = Counter(
        "geoip_ipaddr_not_found", "We couldn't look up the IP address in the database"
    )

    GEOIP_CC_DIFFERS = Counter(
        "geoip_cc_differs", "There's a mismatch between reported CC and observed CC"
    )

    GEOIP_ASN_DIFFERS = Counter(
        "geoip_asn_differs", "There's a mismatch between reported ASN and observed ASN"
    )

    TEST_LIST_URLS_COUNT = Gauge(
        "test_list_urls_count", "Size of reported test list"
    )