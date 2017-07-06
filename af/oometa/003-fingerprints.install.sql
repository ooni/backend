BEGIN;

select _v.register_patch( '003-fingerprints', ARRAY[ '002-features' ], NULL );

create table fingerprint (
    fingerprint_no serial primary key,
    origin_cc character(2) NOT NULL,
    body_substr text null,
    header text null,
    header_prefix text null,
    header_value text null,
    CHECK((body_substr is null) != (header is null)),
    CHECK(header is null OR ((header_prefix is null) != (header_value is null)))
);
comment on table fingerprint is 'Static set of known fingerprints of blockpages';

CREATE TABLE measurement_exc (
    msm_no integer NOT NULL,
    exc integer[] NOT NULL
);
comment on table measurement_exc is 'For `CREATE TABLE LIKE …` while updating';

create table http_request_fp (
    msm_no integer NOT NULL,
    fingerprint_no integer NOT NULL
);
comment on table http_request_fp is 'Features: decision of pipeline using `fingerprint` table';

CREATE INDEX http_request_fp_msm_no_idx ON http_request_fp (msm_no);

COPY fingerprint (origin_cc, body_substr) FROM STDIN;
IR	iframe src="http://10.10
TR	<title>Telekomünikasyon İletişim Başkanlığı</title>
GR	www.gamingcommission.gov.gr/index.php/forbidden-access-black-list/
RU	http://eais.rkn.gov.ru/
IN	The page you have requested has been blocked
BE	that is considered illegal according to Belgian legislation
IT	GdF Stop Page
CY	nba.com.cy/Eas/eas.nsf/All/6F7F17A7790A55C8C2257B130055C86F
DK	lagt at blokere for adgang til siden.
FR	xtpage = "page-blocage-terrorisme"
MY	Makluman/Notification
KR	http://warning.or.kr
RO	Accesul dumneavoastră către acest site a fost restricționat
GF	xtpage = "page-blocage-terrorisme"
\.

COPY fingerprint (origin_cc, header, header_prefix) FROM STDIN;
ID	Location	http://internet-positif.org
UK	Location	http://blocked.nb.sky.com
RU	Location	http://warning.rt.ru
SA	Server	Protected by WireFilter
AE	Server	Protected by WireFilter
\.

COPY fingerprint (origin_cc, header, header_value) FROM STDIN;
SD	Location	http://196.1.211.6:8080/alert/
QA	Location	http://www.vodafone.qa/alu.cfm
KR	Location	http://www.warning.or.kr
PT	Location	http://mobilegen.vodafone.pt/denied/dn
NO	Location	http://block-no.altibox.net/
\.

COMMIT;
