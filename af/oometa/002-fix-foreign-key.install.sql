BEGIN;

select _v.register_patch( '002-fix-foreign-key', ARRAY[ '001-fix-input-uniq' ], NULL );

-- FK CONSTRAINTs are implemented as triggers that are painfully slow during
-- batch import taking huge amount of CPU. It's not trivial to disable/enable
-- these constraints in code, so I'm dropping them altogether.

ALTER TABLE ONLY badblob DROP CONSTRAINT badblob_report_no_fkey;
ALTER TABLE ONLY dns_a DROP CONSTRAINT dns_a_domain_no_fkey;
ALTER TABLE ONLY dns_a DROP CONSTRAINT dns_a_msm_no_fkey;
ALTER TABLE ONLY http_control DROP CONSTRAINT http_control_msm_no_fkey;
ALTER TABLE ONLY http_request DROP CONSTRAINT http_request_msm_no_fkey;
ALTER TABLE ONLY http_verdict DROP CONSTRAINT http_verdict_msm_no_fkey;
ALTER TABLE ONLY measurement DROP CONSTRAINT measurement_input_no_fkey;
ALTER TABLE ONLY measurement DROP CONSTRAINT measurement_report_no_fkey;
ALTER TABLE ONLY report DROP CONSTRAINT report_autoclaved_no_fkey;
ALTER TABLE ONLY report DROP CONSTRAINT report_software_no_fkey;
ALTER TABLE ONLY tcp DROP CONSTRAINT tcp_msm_no_fkey;

COMMIT;
