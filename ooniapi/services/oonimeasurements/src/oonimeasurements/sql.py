from typing import Dict


def format_aggregate_query(extra_cols: Dict[str, str], where: str):
    return f"""
    WITH
    mapSort(dns_isp_blocked_sum) as dns_isp_blocked_map,
    mapSort(dns_isp_down_sum) as dns_isp_down_map,
    dns_isp_ok_sum,
    arraySum(mapValues(dns_isp_blocked_map)) as dns_isp_blocked_sum_total,
    arraySum(mapValues(dns_isp_down_map)) as dns_isp_down_sum_total,
    dns_isp_blocked_sum_total + dns_isp_down_sum_total + dns_isp_ok_sum as dns_isp_total,

    mapSort(dns_other_blocked_sum) as dns_other_blocked_map,
    mapSort(dns_other_down_sum) as dns_other_down_map,
    dns_other_ok_sum,
    arraySum(mapValues(dns_other_blocked_map)) as dns_other_blocked_sum_total,
    arraySum(mapValues(dns_other_down_map)) as dns_other_down_sum_total,
    dns_other_blocked_sum_total + dns_other_down_sum_total + dns_other_ok_sum as dns_other_total,

    mapSort(tls_blocked_sum) as tls_blocked_map,
    mapSort(tls_down_sum) as tls_down_map,
    tls_ok_sum,
    arraySum(mapValues(tls_blocked_map)) as tls_blocked_sum_total,
    arraySum(mapValues(tls_down_map)) as tls_down_sum_total,
    tls_blocked_sum_total + tls_down_sum_total + tls_ok_sum as tls_total,

    mapSort(tcp_blocked_sum) as tcp_blocked_map,
    mapSort(tcp_down_sum) as tcp_down_map,
    tcp_ok_sum,
    arraySum(mapValues(tcp_blocked_map)) as tcp_blocked_sum_total,
    arraySum(mapValues(tcp_down_map)) as tcp_down_sum_total,
    tcp_blocked_sum_total + tcp_down_sum_total + tcp_ok_sum as tcp_total,

    -- Calculate max blocked, max down, and min ok across all protocols
    greatest(dns_isp_blocked, dns_other_blocked, tls_blocked, tcp_blocked) as max_blocked,
    greatest(dns_isp_down, dns_other_down, tls_down, tcp_down) as max_down,
    least(dns_isp_ok, dns_other_ok, tls_ok, tcp_ok) as min_ok,

    -- Determine which protocol has the highest blocked value when max_blocked wins
    multiIf(
        dns_isp_blocked >= dns_other_blocked AND 
        dns_isp_blocked >= tls_blocked AND 
        dns_isp_blocked >= tcp_blocked, 'dns_isp',
        dns_other_blocked >= tls_blocked AND 
        dns_other_blocked >= tcp_blocked, 'dns_other',
        tls_blocked >= tcp_blocked, 'tls',
        'tcp'
    ) as max_blocked_protocol,

    -- Determine which protocol has the highest down value when max_down wins
    multiIf(
        dns_isp_down >= dns_other_down AND 
        dns_isp_down >= tls_down AND 
        dns_isp_down >= tcp_down, 'dns_isp',
        dns_other_down >= tls_down AND 
        dns_other_down >= tcp_down, 'dns_other',
        tls_down >= tcp_down, 'tls',
        'tcp'
    ) as max_down_protocol,

    -- Determine which protocol has the minimum ok value when min_ok wins
    multiIf(
        dns_isp_ok <= dns_other_ok AND 
        dns_isp_ok <= tls_ok AND 
        dns_isp_ok <= tcp_ok, 'dns_isp',
        dns_other_ok <= tls_ok AND 
        dns_other_ok <= tcp_ok, 'dns_other',
        tls_ok <= tcp_ok, 'tls',
        'tcp'
    ) as min_ok_protocol,

    -- Final determination of most likely values
    multiIf(
        max_blocked >= max_down AND max_blocked >= min_ok,
            (multiIf(
                max_blocked_protocol = 'dns_isp', dns_isp_ok,
                max_blocked_protocol = 'dns_other', dns_other_ok,
                max_blocked_protocol = 'tls', tls_ok,
                tcp_ok
            ),
            multiIf(
                max_blocked_protocol = 'dns_isp', dns_isp_down,
                max_blocked_protocol = 'dns_other', dns_other_down,
                max_blocked_protocol = 'tls', tls_down,
                tcp_down
            ),
            max_blocked,
            multiIf(
                max_blocked_protocol = 'dns_isp', if(dns_isp_outcome = 'ok', 'ok', concat('dns_isp.', dns_isp_outcome)),
                max_blocked_protocol = 'dns_other', if(dns_other_outcome = 'ok', 'ok', concat('dns_other.', dns_other_outcome)),
                max_blocked_protocol = 'tls', if(tls_outcome = 'ok', 'ok', concat('tls.', tls_outcome)),
                if(tcp_outcome = 'ok', 'ok', concat('tcp.', tcp_outcome))
            )),
        max_down >= min_ok,
            (multiIf(
                max_down_protocol = 'dns_isp', dns_isp_ok,
                max_down_protocol = 'dns_other', dns_other_ok,
                max_down_protocol = 'tls', tls_ok,
                tcp_ok
            ),
            max_down,
            multiIf(
                max_down_protocol = 'dns_isp', dns_isp_blocked,
                max_down_protocol = 'dns_other', dns_other_blocked,
                max_down_protocol = 'tls', tls_blocked,
                tcp_blocked
            ),
            multiIf(
                max_down_protocol = 'dns_isp', if(dns_isp_outcome = 'ok', 'ok', concat('dns_isp.', dns_isp_outcome)),
                max_down_protocol = 'dns_other', if(dns_other_outcome = 'ok', 'ok', concat('dns_other.', dns_other_outcome)),
                max_down_protocol = 'tls', if(tls_outcome = 'ok', 'ok', concat('tls.', tls_outcome)),
                if(tcp_outcome = 'ok', 'ok', concat('tcp.', tcp_outcome))
            )),
        (min_ok,
        multiIf(
            min_ok_protocol = 'dns_isp', dns_isp_down,
            min_ok_protocol = 'dns_other', dns_other_down,
            min_ok_protocol = 'tls', tls_down,
            tcp_down
        ),
        multiIf(
            min_ok_protocol = 'dns_isp', dns_isp_blocked,
            min_ok_protocol = 'dns_other', dns_other_blocked,
            min_ok_protocol = 'tls', tls_blocked,
            tcp_blocked
        ),
        'ok')
    ) as most_likely_tuple

    SELECT 
    {",".join(extra_cols.keys())},
    probe_analysis,
    count,

    if(dns_isp_total = 0, 0, dns_isp_blocked_sum_total / dns_isp_total) as dns_isp_blocked,
    if(dns_isp_total = 0, 0, dns_isp_down_sum_total / dns_isp_total) as dns_isp_down,
    if(dns_isp_total = 0, 0, dns_isp_ok_sum / dns_isp_total) as dns_isp_ok,

    if(dns_other_total = 0, 0, dns_other_blocked_sum_total / dns_other_total) as dns_other_blocked,
    if(dns_other_total = 0, 0, dns_other_down_sum_total / dns_other_total) as dns_other_down,
    if(dns_other_total = 0, 0, dns_other_ok_sum / dns_other_total) as dns_other_ok,

    if(tls_total = 0, 0, tls_blocked_sum_total / tls_total) as tls_blocked,
    if(tls_total = 0, 0, tls_down_sum_total / tls_total) as tls_down,
    if(tls_total = 0, 0, tls_ok_sum / tls_total) as tls_ok,

    if(tcp_total = 0, 0, tcp_blocked_sum_total / tcp_total) as tcp_blocked,
    if(tcp_total = 0, 0, tcp_down_sum_total / tcp_total) as tcp_down,
    if(tcp_total = 0, 0, tcp_ok_sum / tcp_total) as tcp_ok,

    multiIf(
        dns_isp_total = 0, '',
        dns_isp_ok >= dns_isp_blocked AND 
        dns_isp_ok >= dns_isp_down, 'ok',
        dns_isp_blocked > dns_isp_down,
        concat('blocked.',
            arrayElement(mapKeys(dns_isp_blocked_map), 1)
        ),
        concat('down.',
            arrayElement(mapKeys(dns_isp_down_map), 1)
        )
    ) as dns_isp_outcome,

    multiIf(
        dns_other_total = 0, '',
        dns_other_ok >= dns_other_blocked AND 
        dns_other_ok >= dns_other_down, 'ok',
        dns_other_blocked > dns_other_down,
        concat('blocked.',
            arrayElement(mapKeys(dns_other_blocked_map), 1)
        ),
        concat('down.',
            arrayElement(mapKeys(dns_other_down_map), 1)
        )
    ) as dns_other_outcome,

    multiIf(
        tcp_total = 0, '',
        tcp_ok >= tcp_blocked AND 
        tcp_ok >= tcp_down, 'ok',
        tcp_blocked > tcp_down,
        concat('blocked.',
            arrayElement(mapKeys(tcp_blocked_map), 1)
        ),
        concat('down.',
            arrayElement(mapKeys(tcp_down_map), 1)
        )
    ) as tcp_outcome,

    multiIf(
        tls_total = 0, '',
        tls_ok >= tls_blocked AND 
        tls_ok >= tls_down, 'ok',
        tls_blocked > tls_down,
        concat('blocked.',
            arrayElement(mapKeys(tls_blocked_map), 1)
        ),
        concat('down.',
            arrayElement(mapKeys(tls_down_map), 1)
        )
    ) as tls_outcome,

    most_likely_tuple.1 as most_likely_ok,
    most_likely_tuple.2 as most_likely_down,
    most_likely_tuple.3 as most_likely_blocked,
    most_likely_tuple.4 as most_likely_label

    FROM (
        WITH
        IF(resolver_asn = probe_asn, 1, 0) as is_isp_resolver,
        multiIf(
            top_dns_failure IN ('android_dns_cache_no_data', 'dns_nxdomain_error'),
            'nxdomain',
            coalesce(top_dns_failure, 'got_answer')
        ) as dns_failure
        SELECT
            {",".join(extra_cols.values())},
            COUNT() as count,
        
            anyHeavy(top_probe_analysis) as probe_analysis,
        
            sumMapIf(
                map(
                    dns_failure, dns_blocked
                ), dns_blocked > 0 AND is_isp_resolver
            ) as dns_isp_blocked_sum,
            sumMapIf(
                map(
                    dns_failure, dns_blocked
                ), dns_blocked > 0 AND NOT is_isp_resolver
            ) as dns_other_blocked_sum,
        
            sumMapIf(
                map(
                    dns_failure, dns_down
                ), dns_down > 0 AND is_isp_resolver
            ) as dns_isp_down_sum,
            sumMapIf(
                map(
                    dns_failure, dns_down
                ), dns_down > 0 AND NOT is_isp_resolver
            ) as dns_other_down_sum,
        
            sumIf(dns_ok, is_isp_resolver) as dns_isp_ok_sum,
            sumIf(dns_ok, NOT is_isp_resolver) as dns_other_ok_sum,
        
            sumMapIf(
                map(
                    coalesce(top_tcp_failure, ''), tcp_blocked
                ), tcp_blocked > 0
            )  as tcp_blocked_sum,
            sumMapIf(
                map(
                    coalesce(top_tcp_failure, ''), tcp_down
                ), tcp_down > 0
            )  as tcp_down_sum,
            sum(tcp_ok) as tcp_ok_sum,
        
            sumMapIf(
                map(
                    coalesce(top_tls_failure, ''), tls_blocked
                ), tls_blocked > 0
            ) as tls_blocked_sum,
            sumMapIf(
                map(
                    coalesce(top_tls_failure, ''), tls_down
                ), tls_down > 0
            ) as tls_down_sum,
        
            sum(tls_ok) as tls_ok_sum
        
        FROM analysis_web_measurement
        {where}
        GROUP BY {", ".join(extra_cols.keys())}
        ORDER BY {", ".join(extra_cols.keys())}
    )
    """
