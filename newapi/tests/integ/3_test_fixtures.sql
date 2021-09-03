--
-- Data for Name: url_priorities; Type: TABLE DATA; Schema: public; Owner: shovel
--

INSERT INTO public.url_priorities VALUES ('NEWS', '*', '*', '*', 100);
INSERT INTO public.url_priorities VALUES ('POLR', '*', '*', '*', 100);
INSERT INTO public.url_priorities VALUES ('HUMR', '*', '*', '*', 100);
INSERT INTO public.url_priorities VALUES ('LGBT', '*', '*', '*', 100);
INSERT INTO public.url_priorities VALUES ('ANON', '*', '*', '*', 100);
INSERT INTO public.url_priorities VALUES ('MMED', '*', '*', '*', 80);
INSERT INTO public.url_priorities VALUES ('SRCH', '*', '*', '*', 80);
INSERT INTO public.url_priorities VALUES ('PUBH', '*', '*', '*', 80);
INSERT INTO public.url_priorities VALUES ('REL', '*', '*', '*', 60);
INSERT INTO public.url_priorities VALUES ('XED', '*', '*', '*', 60);
INSERT INTO public.url_priorities VALUES ('HOST', '*', '*', '*', 60);
INSERT INTO public.url_priorities VALUES ('ENV', '*', '*', '*', 60);
INSERT INTO public.url_priorities VALUES ('FILE', '*', '*', '*', 40);
INSERT INTO public.url_priorities VALUES ('CULTR', '*', '*', '*', 40);
INSERT INTO public.url_priorities VALUES ('IGO', '*', '*', '*', 40);
INSERT INTO public.url_priorities VALUES ('GOVT', '*', '*', '*', 40);
INSERT INTO public.url_priorities VALUES ('DATE', '*', '*', '*', 30);
INSERT INTO public.url_priorities VALUES ('HATE', '*', '*', '*', 30);
INSERT INTO public.url_priorities VALUES ('MILX', '*', '*', '*', 30);
INSERT INTO public.url_priorities VALUES ('PROV', '*', '*', '*', 30);
INSERT INTO public.url_priorities VALUES ('PORN', '*', '*', '*', 30);
INSERT INTO public.url_priorities VALUES ('GMB', '*', '*', '*', 30);
INSERT INTO public.url_priorities VALUES ('ALDR', '*', '*', '*', 30);
INSERT INTO public.url_priorities VALUES ('GAME', '*', '*', '*', 20);
INSERT INTO public.url_priorities VALUES ('MISC', '*', '*', '*', 20);
INSERT INTO public.url_priorities VALUES ('HACK', '*', '*', '*', 20);
INSERT INTO public.url_priorities VALUES ('ECON', '*', '*', '*', 20);
INSERT INTO public.url_priorities VALUES ('COMM', '*', '*', '*', 20);
INSERT INTO public.url_priorities VALUES ('CTRL', '*', '*', '*', 20);
INSERT INTO public.url_priorities VALUES ('NEWS', 'it', '*', '*', 10);
INSERT INTO public.url_priorities VALUES ('NEWS', 'it', 'www.leggo.it', '*', 5);
INSERT INTO public.url_priorities VALUES ('COMT', '*', '*', '*', 100);
INSERT INTO public.url_priorities VALUES ('GRP', '*', '*', '*', 100);

INSERT INTO public.fastpath VALUES ('20201216054344.884408_VE_webconnectivity_a255255d74fff0be', '20201216T050353Z_webconnectivity_VE_21826_n1_wxAHEUDoof21UBss', 'http://www.theonion.com/', 'VE', 21826, 'web_connectivity', '2020-12-16 05:03:48', '2020-12-16 05:44:41', NULL, '{"blocking_general":0.0,"blocking_global":0.0,"blocking_country":0.0,"blocking_isp":0.0,"blocking_local":0.0}', 'linux', false, false, false, 'www.theonion.com', 'ooniprobe-cli', '3.0.7-beta');

INSERT INTO public.citizenlab VALUES ('www.theonion.com', 'http://www.theonion.com/', 'ZZ', 'CULTR', 40);

--INSERT INTO public.jsonl VALUES ('20201216T050353Z_webconnectivity_VE_21826_n1_wxAHEUDoof21UBss', 'http://www.theonion.com/', NULL, 'raw/20201216/05/VE/webconnectivity/2020121605_VE_webconnectivity.n0.8.jsonl.gz', 119);

-- prepare counters_test_list
INSERT INTO public.counters VALUES (CURRENT_DATE, 'web_connectivity', 'IT', 1, 'https://www.leggo.it/', 0, 0, 0, 2);
INSERT INTO public.counters VALUES (CURRENT_DATE, 'web_connectivity', 'IT', 2, 'https://www.ilfattoquotidiano.it/', 0, 0, 0, 2);
INSERT INTO public.counters VALUES (CURRENT_DATE, 'web_connectivity', 'IT', 3, 'https://www.ilmattino.it/', 0, 0, 0, 2);
INSERT INTO public.counters VALUES (CURRENT_DATE, 'web_connectivity', 'IT', 4, 'https://www.ilgiorno.it/', 0, 0, 0, 2);
REFRESH MATERIALIZED VIEW counters_test_list;
