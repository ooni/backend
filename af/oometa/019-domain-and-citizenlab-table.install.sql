-- Create domain_input and citizenlab table
-- Formatted with pgformatter 3.3

BEGIN;

SELECT
    _v.register_patch ('019-domain-and-citizenlab-table',
        ARRAY['018-fastpath'],
        NULL);

CREATE TABLE domain_input (
    "domain" TEXT NOT NULL,
    "input" TEXT NOT NULL,
    "input_no" integer
);

CREATE INDEX domain_input_domain_idx ON domain_input (domain);

CREATE UNIQUE INDEX domain_input_input_sha256_key on domain_input (digest(input::text, 'sha256'));

CREATE INDEX domain_input_input_no_idx ON domain_input (input_no);

COMMENT ON COLUMN domain_input.domain IS 'FQDN or ipaddr without http and port number';

CREATE TABLE citizenlab (
    "domain" TEXT NOT NULL,
    "url" TEXT NOT NULL,
    "cc" CHARACTER(2),
    "category_code" TEXT,
    "priority" SMALLINT DEFAULT 256
);

-- indexing is more efficient on the leftmost columns
CREATE INDEX citizenlab_multi_idx ON citizenlab (url, domain, category_code, cc);

COMMENT ON COLUMN citizenlab.domain IS 'FQDN or ipaddr without http and port number';

COMMENT ON COLUMN citizenlab.category_code IS 'Category from Citizen Lab';

COMMIT;

