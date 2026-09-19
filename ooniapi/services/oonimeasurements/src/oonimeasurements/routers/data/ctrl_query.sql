-- Params:
--   %(hostnames)s            -- list of hostnames to build the ground truth for
--   %(start_time)s           -- typically now() - INTERVAL 1 HOUR
--   %(end_time)s             -- typically now()
--   %(cloud_provider_asns)s  -- list of ASNs considered to be known cloud providers
SELECT
hostname,
ip,
port,
asn,
as_org_name,
is_cloud_provider,
in_dns_answers,
tls_consistent,
tcp_success_count,
tcp_failure_count,
tls_success_count,
tls_failure_count,
dns_success_count,
dns_nxdomain_count,
dns_other_failure_count
FROM
(
    SELECT
    hostname,
    ip,
    port,

    any(ip_asn) as asn,
    any(ip_as_org_name) as as_org_name,
    coalesce(any(ip_asn IN %(cloud_provider_asns)s), 0) as is_cloud_provider,

    countIf(dns_success = 1) as row_dns_success_count,
    countIf(dns_failure = 'dns_nxdomain_error') as row_dns_nxdomain_count,
    countIf(dns_failure IS NOT NULL AND dns_failure != 'dns_nxdomain_error') as row_dns_other_failure_count,

    row_dns_success_count > 0 as in_dns_answers,

    countIf(tcp_success = 1) as tcp_success_count,
    countIf(tcp_success = 0) as tcp_failure_count,
    countIf(tls_success = 1) as tls_success_count,
    countIf(tls_success = 0 AND tls_failure IS NOT NULL) as tls_failure_count,

    max(tls_success_count > 0) OVER (PARTITION BY hostname, ip) as tls_consistent,

    sum(row_dns_success_count) OVER (PARTITION BY hostname) as dns_success_count,
    sum(row_dns_nxdomain_count) OVER (PARTITION BY hostname) as dns_nxdomain_count,
    sum(row_dns_other_failure_count) OVER (PARTITION BY hostname) as dns_other_failure_count

    FROM obs_web_ctrl
    WHERE measurement_start_time > %(start_time)s
    AND measurement_start_time <= %(end_time)s
    AND hostname IN %(hostnames)s
    GROUP BY hostname, ip, port
)
