BEGIN;

select _v.unregister_patch( '001-fix-foreign-key' );

ALTER TABLE ONLY badblob
    ADD CONSTRAINT badblob_report_no_fkey FOREIGN KEY (report_no) REFERENCES report(report_no);
ALTER TABLE ONLY dns_a
    ADD CONSTRAINT dns_a_domain_no_fkey FOREIGN KEY (domain_no) REFERENCES domain(domain_no);
ALTER TABLE ONLY dns_a
    ADD CONSTRAINT dns_a_msm_no_fkey FOREIGN KEY (msm_no) REFERENCES measurement(msm_no);
ALTER TABLE ONLY http_control
    ADD CONSTRAINT http_control_msm_no_fkey FOREIGN KEY (msm_no) REFERENCES measurement(msm_no);
ALTER TABLE ONLY http_request
    ADD CONSTRAINT http_request_msm_no_fkey FOREIGN KEY (msm_no) REFERENCES measurement(msm_no);
ALTER TABLE ONLY http_verdict
    ADD CONSTRAINT http_verdict_msm_no_fkey FOREIGN KEY (msm_no) REFERENCES measurement(msm_no);
ALTER TABLE ONLY measurement
    ADD CONSTRAINT measurement_input_no_fkey FOREIGN KEY (input_no) REFERENCES input(input_no);
ALTER TABLE ONLY measurement
    ADD CONSTRAINT measurement_report_no_fkey FOREIGN KEY (report_no) REFERENCES report(report_no);
ALTER TABLE ONLY report
    ADD CONSTRAINT report_autoclaved_no_fkey FOREIGN KEY (autoclaved_no) REFERENCES autoclaved(autoclaved_no);
ALTER TABLE ONLY report
    ADD CONSTRAINT report_software_no_fkey FOREIGN KEY (software_no) REFERENCES software(software_no);
ALTER TABLE ONLY tcp
    ADD CONSTRAINT tcp_msm_no_fkey FOREIGN KEY (msm_no) REFERENCES measurement(msm_no);

COMMIT;
