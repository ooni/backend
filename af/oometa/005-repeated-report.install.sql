BEGIN;

select _v.register_patch( '005-repeated-report', ARRAY[ '004-measurements-index' ], NULL );

create domain sha512 as bytea check (octet_length(value) = 64);

create sequence dupgrp_no_seq;

-- Everything goes to `public` schema.
CREATE TABLE repeated_report (
    -- group_no < 0 is indication of manual data entry
    dupgrp_no integer NOT NULL,
    used boolean NOT NULL,
    textname text UNIQUE NOT NULL,
    -- NB: `filename` is part of "private" information, it's not stored intentionally
    orig_sha1 sha1 NOT NULL,
    orig_sha512 sha512 NOT NULL);

-- These two files differ, but the first one includes EVERY `datum` from the second one.
-- Also, measurements are _reordered_ within the file. It looks like strange in-place editing.
-- You can compare output of following commands:
-- $ zcat autoclaved/2016-02-11/index.json.gz | awk '/20160210T163242Z-IR-AS201227-http_requests-yZthLDkKNe6IdePf7B1gMgNvRxSMDwNGWD6BB1MWcuY2T3q7oLmDQkjhZARARuic-0.1.0-probe.yaml/ {a = 1} (a == 1 && /"datum"/) {print} /"\/report"/ {a = 0}' | jq .orig_sha1 | sort
-- Corresponding `canned` entries are:
-- {"text_crc32": 413542756, "text_sha1": "xVNkUEwQmauT/F6uO1X6ICvCRN0=", "text_size": 25559440, "textname": "2016-02-11/20160210T163242Z-IR-AS201227-http_requests-yZthLDkKNe6IdePf7B1gMgNvRxSMDwNGWD6BB1MWcuY2T3q7oLmDQkjhZARARuic-0.1.0-probe.yaml"}
-- {"text_crc32": -1449913125, "text_sha1": "BI75eyhWrwX/BdVOzLA8GIu/Pxg=", "text_size": 15786443, "textname": "2016-02-23/20160210T163242Z-IR-AS201227-http_requests-yZthLDkKNe6IdePf7B1gMgNvRxSMDwNGWD6BB1MWcuY2T3q7oLmDQkjhZARARuic-0.1.0-probe.yaml"}
COPY repeated_report (dupgrp_no, used, orig_sha1, orig_sha512, textname) FROM STDIN;
-1	true	\\xc55364504c1099ab93fc5eae3b55fa202bc244dd	\\x18f8c9cca8b76c53063acce30ec328bd54cff5fd399cfef4ab0666aece0b5f8681e6fab6ca73113ace4f0ff10389451f3ccd737d69a23db258eea73cccdc9798	2016-02-11/20160210T163242Z-IR-AS201227-http_requests-yZthLDkKNe6IdePf7B1gMgNvRxSMDwNGWD6BB1MWcuY2T3q7oLmDQkjhZARARuic-0.1.0-probe.yaml
-1	false	\\x048ef97b2856af05ff05d54eccb03c188bbf3f18	\\xb042c07fab30a8d855c1b60017b10235f0fabe76e75da25422d66c004fa4b6d8e23ebb48c5cc8ac31b0bf93e9140f3ec95d9702fff8e5744973959b0ec4cd237	2016-02-23/20160210T163242Z-IR-AS201227-http_requests-yZthLDkKNe6IdePf7B1gMgNvRxSMDwNGWD6BB1MWcuY2T3q7oLmDQkjhZARARuic-0.1.0-probe.yaml
\.

CREATE FUNCTION ooconstraint_repeated_report() RETURNS VOID STABLE AS $$
BEGIN
    PERFORM 1 FROM repeated_report LEFT JOIN report USING (textname) WHERE NOT used AND report.textname IS NOT NULL;
    IF FOUND THEN
        RAISE EXCEPTION 'Unused repeated_report in `report` table';
    END IF;

    PERFORM 1 FROM repeated_report LEFT JOIN report USING (textname) WHERE used AND report.textname IS NULL;
    IF FOUND THEN
        RAISE EXCEPTION 'Used repeated_report not in `report` table';
    END IF;
END;
$$ LANGUAGE plpgsql;

COMMIT;
