-- Create new test names
-- Formatted with pgformatter 3.3

BEGIN;
SELECT
    _v.register_patch ('020-new-test-names',
        ARRAY['019-domain-and-citizenlab-table'],
        NULL);
COMMIT;

-- This needs to be done outside of a transaction :-/
ALTER TYPE ootest ADD VALUE 'psiphon';
ALTER TYPE ootest ADD VALUE 'tor';

