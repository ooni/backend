from typing import Dict


def format_aggregate_query(extra_cols: Dict[str, str], where: str):
    return f"""
    SELECT
    {",".join(extra_cols.keys())},
    probe_analysis,
    count,

    dns_isp_blocked_q99 as dns_isp_blocked,
    dns_isp_down_q99 as dns_isp_down,
    dns_isp_ok_q99 as dns_isp_ok,

    dns_other_blocked_q99 as dns_other_blocked,
    dns_other_down_q99 as dns_other_down,
    dns_other_ok_q99 as dns_other_ok,

    tcp_blocked_q99 as tcp_blocked,
    tcp_down_q99 as tcp_down,
    tcp_ok_q99 as tcp_ok,

    tls_blocked_q99 as tls_blocked,
    tls_down_q99 as tls_down,
    tls_ok_q99 as tls_ok,

    arrayFirst(x -> TRUE, top_dns_isp_failures_by_impact).1 as dns_isp_blocked_outcome,

    arrayFirst(x -> TRUE, top_dns_other_failures_by_impact).1 as dns_other_blocked_outcome,

    arrayFirst(x -> TRUE, top_tcp_failures_by_impact).1 as tcp_blocked_outcome,

    arrayFirst(x -> TRUE, top_tls_failures_by_impact).1 as tls_blocked_outcome,

    arrayMap(
        x -> multiIf(
            x.2 = 'dns_isp',
            (CONCAT(x.2, '.', dns_isp_blocked_outcome), dns_isp_blocked),
            x.2 = 'dns_other',
            (CONCAT(x.2, '.', dns_other_blocked_outcome), dns_other_blocked),
            x.2 = 'tcp',
            (CONCAT(x.2, '.', tcp_blocked_outcome), tcp_blocked),
            x.2 = 'tls',
            (CONCAT(x.2, '.', tls_blocked_outcome), tls_blocked),
            'none'
        ),
        arraySort(
            x -> -x.1,
            arrayFilter(
                x -> x.1 > 0.5,
                [
                    (dns_isp_blocked, 'dns_isp'),
                    (dns_other_blocked, 'dns_other'),
                    (tcp_blocked, 'tcp'),
                    (tls_blocked, 'tls')
                ]
            )
        )
    ) as likely_blocked_protocols,

    arrayElementOrNull(likely_blocked_protocols, 1) as blocked_max_protocol

    FROM (
        WITH
        IF(resolver_asn = probe_asn, 1, 0) as is_isp_resolver,
        multiIf(
            top_dns_failure IN ('android_dns_cache_no_data', 'dns_nxdomain_error'),
            'nxdomain',
            coalesce(top_dns_failure , 'got_answer')
        ) as dns_failure

        SELECT
            probe_cc,
            COUNT() as count,

            anyHeavy(top_probe_analysis) as probe_analysis,

            topKWeightedIf(10, 3, 'counts')(
                dns_failure,
                toInt8(dns_blocked * 100),
                is_isp_resolver = 1
            ) as top_dns_isp_failures_by_impact,

            topKWeightedIf(10, 3, 'counts')(
                dns_failure,
                toInt8(dns_blocked * 100),
                is_isp_resolver = 0
            ) as top_dns_other_failures_by_impact,

            topKWeighted(10, 3, 'counts')(
                top_tcp_failure,
                toInt8(tcp_blocked * 100)
            ) as top_tcp_failures_by_impact,

            topKWeighted(10, 3, 'counts')(
                top_tls_failure,
                toInt8(tls_blocked * 100)
            ) as top_tls_failures_by_impact,

            quantileIf(0.99)(dns_blocked, is_isp_resolver = 1) as dns_isp_blocked_q99,
            quantileIf(0.99)(dns_down, is_isp_resolver = 1) as dns_isp_down_q99,
            quantileIf(0.99)(dns_ok, is_isp_resolver = 1) as dns_isp_ok_q99,

            quantileIf(0.99)(dns_blocked, is_isp_resolver = 0) as dns_other_blocked_q99,
            quantileIf(0.99)(dns_down, is_isp_resolver = 0) as dns_other_down_q99,
            quantileIf(0.99)(dns_ok, is_isp_resolver = 0) as dns_other_ok_q99,

            quantile(0.99)(tcp_blocked) as tcp_blocked_q99,
            quantile(0.99)(tcp_down) as tcp_down_q99,
            quantile(0.99)(tcp_ok) as tcp_ok_q99,

            quantile(0.99)(tls_blocked) as tls_blocked_q99,
            quantile(0.99)(tls_down) as tls_down_q99,
            quantile(0.99)(tls_ok) as tls_ok_q99

        FROM analysis_web_measurement

        WHERE
        {where}
        GROUP BY {", ".join(extra_cols.keys())}
        ORDER BY {", ".join(extra_cols.keys())}
    )
    """
