-- Drop domain_input and citizenlab tables
-- Formatted with pgformatter 3.3
BEGIN;
SELECT
    _v.unregister_patch ('019-domain-and-citizenlab-table')
    DROP TABLE domain_input;
DROP TABLE citizenlab;
COMMIT;
