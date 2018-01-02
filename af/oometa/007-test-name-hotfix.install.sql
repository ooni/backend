-- ALTER TYPE ... ADD cannot run inside a transaction block
ALTER TYPE ootest ADD VALUE IF NOT EXISTS 'dash';
ALTER TYPE ootest ADD VALUE IF NOT EXISTS 'telegram';

BEGIN;

select _v.register_patch( '007-test-name-hotfix',  ARRAY[ '006-reingestion' ], NULL );

-- That's temporary backward-compatible hotfix till API is updated to use
-- relevant tables and relevant indexes are crated as a part of relevant process.

UPDATE report rpt
SET test_name = 'telegram'
FROM software sw
WHERE rpt.software_no = sw.software_no AND sw.test_name = 'telegram';

UPDATE report rpt
SET test_name = 'dash'
FROM software sw
WHERE rpt.software_no = sw.software_no AND sw.test_name = 'dash';

COMMIT;
