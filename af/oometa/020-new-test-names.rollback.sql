-- Delete new test names
-- Formatted with pgformatter 3.3

BEGIN;
SELECT
    _v.unregister_patch ('020-new-test-names');
-- rename type, add old one and switch the colums
-- This all work in a transaction, contrarily
-- to the addition of new values
ALTER TYPE ootest RENAME TO ootest_old;
CREATE TYPE ootest AS enum (
    'web_connectivity',
    'http_requests',
    'dns_consistency',
    'http_invalid_request_line',
    'bridge_reachability',
    'tcp_connect',
    'http_header_field_manipulation',
    'http_host',
    'multi_protocol_traceroute',
    'meek_fronted_requests_test',
    'whatsapp',
    'vanilla_tor',
    'facebook_messenger',
    'ndt'
);
ALTER TABLE report
    ALTER COLUMN test_name TYPE ootest
    USING test_name::text::ootest;
ALTER TABLE fastpath
    ALTER COLUMN test_name TYPE ootest
    USING test_name::text::ootest;
DROP TYPE ootest_old;
COMMIT;

