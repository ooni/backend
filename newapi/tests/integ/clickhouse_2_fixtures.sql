-- Populate lookup tables

INSERT INTO test_groups (test_name, test_group) VALUES ('bridge_reachability', 'circumvention'), ('meek_fronted_requests_test', 'circumvention'), ('psiphon', 'circumvention'), ('riseupvpn', 'circumvention'), ('tcp_connect', 'circumvention'), ('tor', 'circumvention'), ('torsf', 'circumvention'), ('vanilla_tor', 'circumvention'), ('dnscheck', 'experimental'), ('urlgetter', 'experimental'), ('facebook_messenger', 'im'), ('signal', 'im'), ('telegram', 'im'), ('whatsapp', 'im'), ('dns_consistency', 'legacy'), ('http_host', 'legacy'), ('http_requests', 'legacy'), ('multi_protocol_traceroute', 'legacy'), ('http_header_field_manipulation', 'middlebox'), ('http_invalid_request_line', 'middlebox'), ('dash', 'performance'), ('ndt', 'performance')('web_connectivity', 'websites') ;

-- Create integ test data for Clickhouse

INSERT INTO citizenlab VALUES ('www.ushmm.org', 'https://www.ushmm.org/', 'ZZ', 'CULTR');
INSERT INTO citizenlab VALUES ('www.cabofrio.rj.gov.br', 'http://www.cabofrio.rj.gov.br/', 'BR', 'CULTR');
INSERT INTO citizenlab VALUES ('ncac.org', 'http://ncac.org/', 'ZZ', 'NEWS');

-- get_measurement_meta integ tests
INSERT INTO jsonl (report_id, input, s3path, linenum) VALUES ('20210709T004340Z_webconnectivity_MY_4818_n1_YCM7J9mGcEHds2K3', 'https://www.backtrack-linux.org/', 'raw/20210709/00/MY/webconnectivity/2021070900_MY_webconnectivity.n0.2.jsonl.gz', 35)


