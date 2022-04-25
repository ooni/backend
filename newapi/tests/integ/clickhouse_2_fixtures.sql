-- Populate lookup tables

INSERT INTO test_groups (test_name, test_group) VALUES ('bridge_reachability', 'circumvention'), ('meek_fronted_requests_test', 'circumvention'), ('psiphon', 'circumvention'), ('riseupvpn', 'circumvention'), ('tcp_connect', 'circumvention'), ('tor', 'circumvention'), ('torsf', 'circumvention'), ('vanilla_tor', 'circumvention'), ('dnscheck', 'experimental'), ('urlgetter', 'experimental'), ('facebook_messenger', 'im'), ('signal', 'im'), ('telegram', 'im'), ('whatsapp', 'im'), ('dns_consistency', 'legacy'), ('http_host', 'legacy'), ('http_requests', 'legacy'), ('multi_protocol_traceroute', 'legacy'), ('http_header_field_manipulation', 'middlebox'), ('http_invalid_request_line', 'middlebox'), ('dash', 'performance'), ('ndt', 'performance')('web_connectivity', 'websites') ;

-- Create integ test data for Clickhouse

--INSERT INTO url_priorities VALUES ('NEWS', '*', '*', '*', 100);
--INSERT INTO url_priorities VALUES ('POLR', '*', '*', '*', 100);
--INSERT INTO url_priorities VALUES ('HUMR', '*', '*', '*', 100);
--INSERT INTO url_priorities VALUES ('LGBT', '*', '*', '*', 100);
--INSERT INTO url_priorities VALUES ('ANON', '*', '*', '*', 100);
--INSERT INTO url_priorities VALUES ('MMED', '*', '*', '*', 80);
--INSERT INTO url_priorities VALUES ('SRCH', '*', '*', '*', 80);
--INSERT INTO url_priorities VALUES ('PUBH', '*', '*', '*', 80);
--INSERT INTO url_priorities VALUES ('REL', '*', '*', '*', 60);
--INSERT INTO url_priorities VALUES ('XED', '*', '*', '*', 60);
--INSERT INTO url_priorities VALUES ('HOST', '*', '*', '*', 60);
--INSERT INTO url_priorities VALUES ('ENV', '*', '*', '*', 60);
--INSERT INTO url_priorities VALUES ('FILE', '*', '*', '*', 40);
--INSERT INTO url_priorities VALUES ('CULTR', '*', '*', '*', 40);
--INSERT INTO url_priorities VALUES ('IGO', '*', '*', '*', 40);
--INSERT INTO url_priorities VALUES ('GOVT', '*', '*', '*', 40);
--INSERT INTO url_priorities VALUES ('DATE', '*', '*', '*', 30);
--INSERT INTO url_priorities VALUES ('HATE', '*', '*', '*', 30);
--INSERT INTO url_priorities VALUES ('MILX', '*', '*', '*', 30);
--INSERT INTO url_priorities VALUES ('PROV', '*', '*', '*', 30);
--INSERT INTO url_priorities VALUES ('PORN', '*', '*', '*', 30);
--INSERT INTO url_priorities VALUES ('GMB', '*', '*', '*', 30);
--INSERT INTO url_priorities VALUES ('ALDR', '*', '*', '*', 30);
--INSERT INTO url_priorities VALUES ('GAME', '*', '*', '*', 20);
--INSERT INTO url_priorities VALUES ('MISC', '*', '*', '*', 20);
--INSERT INTO url_priorities VALUES ('HACK', '*', '*', '*', 20);
--INSERT INTO url_priorities VALUES ('ECON', '*', '*', '*', 20);
--INSERT INTO url_priorities VALUES ('COMM', '*', '*', '*', 20);
--INSERT INTO url_priorities VALUES ('CTRL', '*', '*', '*', 20);
--INSERT INTO url_priorities VALUES ('COMT', '*', '*', '*', 100);
--INSERT INTO url_priorities VALUES ('GRP', '*', '*', '*', 100);

--INSERT INTO citizenlab VALUES ('www.ushmm.org', 'https://www.ushmm.org/', 'ZZ', 'CULTR', 90);
--INSERT INTO citizenlab VALUES ('www.cabofrio.rj.gov.br', 'http://www.cabofrio.rj.gov.br/', 'BR', 'CULTR', 90);
--INSERT INTO citizenlab VALUES ('ncac.org', 'http://ncac.org/', 'ZZ', 'NEWS', 150);

-- get_measurement_meta integ tests
INSERT INTO jsonl (report_id, input, s3path, linenum) VALUES ('20210709T004340Z_webconnectivity_MY_4818_n1_YCM7J9mGcEHds2K3', 'https://www.backtrack-linux.org/', 'raw/20210709/00/MY/webconnectivity/2021070900_MY_webconnectivity.n0.2.jsonl.gz', 35)


