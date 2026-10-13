--
-- PostgreSQL database dump
--

\restrict idevsddjB6HcYc6hveTGIT2dAkpe8h6afx49sTLa1Fgocfj1RCEWJhDDxVrhLgt

-- Dumped from database version 17.8 (ad62774)
-- Dumped by pg_dump version 18.3

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Data for Name: societies; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.societies (id, name, address, created_at) FROM stdin;
1	VTP Leonara	Mahalunge, Pune	2026-03-24 17:36:18.676374+00
2	Test Society	Test Address	2026-03-25 19:01:40.13722+00
\.


--
-- Data for Name: flats; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.flats (id, society_id, flat_number, owner_name, email, created_at) FROM stdin;
3	2	A101	John Doe	john@example.com	2026-03-25 19:02:14.61974+00
4	2	A102	Jane Smith	jane@example.com	2026-03-25 19:02:14.61974+00
1	1	A101	John Doe	anuragpande66@gmail.com	2026-03-24 17:38:09.38742+00
2	1	A102	Jane Smith	anuragpande781@gmail.com	2026-03-24 17:38:09.38742+00
\.


--
-- Data for Name: chargers; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.chargers (id, flat_id, charger_id, fw_version, is_active, last_seen_at, created_at) FROM stdin;
2	2	EZC002	\N	t	\N	2026-03-24 17:39:23.990558+00
3	3	EZC0012	\N	t	\N	2026-03-25 19:02:47.933817+00
4	4	EZC0023	\N	t	\N	2026-03-25 19:02:47.933817+00
1	1	EZC001	6.2.3	t	2026-05-06 06:13:51.998175+00	2026-03-24 17:39:23.990558+00
\.


--
-- Data for Name: charger_status; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.charger_status (id, charger_id, charger_status, voltage, current, energy_kwh, rfid_uid, duration_min, fault_code, temperature_c, fw_version, device_datetime, received_at) FROM stdin;
1	EZC001	active	237.20	0.11	3.7820	14AF7D05	101	200	29.90	6.2.3	2026-05-04 01:19:22+00	2026-05-06 06:13:52.818283+00
\.


--
-- Data for Name: charging_sessions; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.charging_sessions (id, session_id, charger_id, rfid_uid, start_kwhr, end_kwhr, units_consumed, status, fault_code, fw_version, started_at, ended_at, created_at, temperature_c, msg_id, start_epoch, stop_epoch, start_meter_kwh, end_meter_kwh, offline) FROM stdin;
1	1	EZC001	14AF7D05	26.1900	26.1900	0.0000	charging_ended_error	E07	4.0.0	2026-03-27 12:54:50.184123+00	2026-03-27 12:55:20.8064+00	2026-03-27 12:54:47.806562+00	\N	\N	\N	\N	\N	\N	f
2	2	EZC001	14AF7D05	26.1900	26.1900	0.0000	charging_ended_error	E07	4.0.0	2026-03-27 12:58:58.140241+00	2026-03-27 12:59:29.93388+00	2026-03-27 12:58:56.871717+00	\N	\N	\N	\N	\N	\N	f
3	3	EZC001	14AF7D05	26.1900	26.1900	0.0000	charging_ended_error	E07	4.0.0	2026-03-27 13:06:14.860396+00	2026-03-27 13:06:43.296317+00	2026-03-27 13:06:10.02591+00	\N	\N	\N	\N	\N	\N	f
4	4	EZC001	14AF7D05	26.1900	26.2070	0.0170	charging_ended	\N	4.0.0	2026-03-27 13:07:36.471397+00	2026-03-27 13:24:18.384237+00	2026-03-27 13:07:34.91934+00	\N	\N	\N	\N	\N	\N	f
6	7	EZC001	A1A8D505	26.2680	26.2680	0.0000	charging_ended_error	E07	4.0.0	2026-04-04 08:06:04.254953+00	2026-04-04 08:06:33.026885+00	2026-04-04 08:06:00.176471+00	\N	\N	\N	\N	\N	\N	f
7	8	EZC001	A1A8D505	26.2680	26.2680	0.0000	charging_ended_error	E07	4.0.0	2026-04-04 08:06:54.442784+00	2026-04-04 08:07:26.1254+00	2026-04-04 08:06:53.10601+00	\N	\N	\N	\N	\N	\N	f
9	10	EZC001	A1A8D505	26.2680	26.2680	0.0000	chargin_ended	\N	4.0.0	2026-04-04 08:08:34.68486+00	2026-04-04 08:08:34.68486+00	2026-04-04 08:08:33.347883+00	\N	\N	\N	\N	\N	\N	f
8	9	EZC001	A1A8D505	26.2680	30.2680	4.0000	charging_ended_error	E07	4.0.0	2026-04-04 08:07:32.61398+00	2026-04-04 08:08:04.304049+00	2026-04-04 08:07:31.269864+00	\N	\N	\N	\N	\N	\N	f
10	6	EZC001	14AF7D05	0.0000	\N	\N	charging_ended	\N	6.0.2	2026-04-14 11:57:49+00	2026-04-22 15:24:05.113195+00	2026-04-14 11:58:07.178789+00	22.44	\N	\N	\N	\N	\N	f
11	11	EZC001	14AF7D05	\N	0.1040	\N	charging_ended	\N	6.0.3	2026-04-22 15:24:03+00	2026-04-22 15:59:11+00	2026-04-22 15:24:04.081081+00	37.90	\N	\N	\N	\N	\N	f
12	12	EZC001	14AF7D05	0.0000	0.0010	\N	charging_ended	\N	6.0.3	2026-04-22 15:59:55+00	2026-04-22 16:01:04+00	2026-04-22 15:59:56.198187+00	38.07	\N	\N	\N	\N	\N	f
13	13	EZC001	14AF7D05	0.0000	0.0020	\N	charging_ended	\N	6.0.3	2026-04-22 16:01:11+00	2026-04-22 16:02:45+00	2026-04-22 16:01:12.617717+00	38.08	\N	\N	\N	\N	\N	f
14	19	EZC001	14AF7D05	0.0000	0.0000	\N	charging_ended_error	E07	6.2.3	2026-05-01 17:16:44+00	2026-05-01 17:17:14+00	2026-05-01 17:16:44.850927+00	32.76	\N	\N	\N	\N	\N	f
15	20	EZC001	14AF7D05	0.0000	0.0000	\N	charging_ended_error	E07	6.2.3	2026-05-01 18:02:15+00	2026-05-01 18:02:44+00	2026-05-01 18:02:17.989279+00	31.63	\N	\N	\N	\N	\N	f
16	21	EZC001	14AF7D05	0.0000	0.0000	\N	charging_ended_error	E07	6.2.3	2026-05-01 18:03:59+00	2026-05-01 18:04:30+00	2026-05-01 18:03:59.89742+00	31.69	\N	\N	\N	\N	\N	f
17	22	EZC001	14AF7D05	0.0000	\N	\N	active	\N	6.2.3	2026-05-01 18:05:12+00	\N	2026-05-01 18:05:13.407597+00	31.76	\N	\N	\N	\N	\N	f
\.


--
-- Data for Name: command_logs; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.command_logs (id, charger_id, log_type, cmd, ok, reason, rfid_uid, slots_remaining, fw_version, received_at) FROM stdin;
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.users (id, email, hashed_password, full_name, role, is_active, created_at) FROM stdin;
1	admin@indram.com	$2b$12$iJ8b0NCdlNv3BYRxQWSLHeQTgmm74h4rjYHeGz8w.oIO5NFJCcR4e	Super Admin	super_admin	t	2026-03-24 17:12:03.683028+00
2	admin@vtp.com	$2b$12$ViXcPD/Ffz9qq5JtSb4UUOBN3SA7Fil3ROeMw0qXd5w8/eFv5YLjG	VTP Admin	society_admin	t	2026-03-25 12:10:50.540679+00
3	test@society.com	$2b$12$GPwhVm6Cda7gZIdC2SVFVOgznR8yyZEk2OiRVrcgAyycXioe.CqHS	Test Admin	society_admin	t	2026-03-25 19:04:09.09933+00
4	testing@admin.com	$2b$12$nLZya5ROY.J.OkmPIBnfme58qrOaUIke6I9T3JPE6nmqAiyx2loq6	Testing Admin	society_admin	t	2026-03-27 14:02:57.852369+00
\.


--
-- Data for Name: monthly_bills; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.monthly_bills (id, society_id, billing_month, tariff, total_bill_amount, total_units_consumed, effective_unit_rate, due_date, bill_photo_s3_key, created_by, created_at) FROM stdin;
4	1	2026-04-01	10.0000	75.00	4.0000	18.7500	2026-04-26	\N	2	2026-04-19 17:56:55.510415+00
\.


--
-- Data for Name: flat_bills; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.flat_bills (id, monthly_bill_id, flat_id, units_consumed, bill_excl_taxes, mseb_taxes, electricity_charges_incl_tax, indram_charges, total_payable, pdf_s3_key, email_status, email_sent_at, created_at) FROM stdin;
5	4	1	4.0000	40.00	35.00	75.00	6.00	81.00	\N	sent	2026-04-19 17:57:13.883547+00	2026-04-19 17:56:55.510415+00
6	4	2	0.0000	0.00	0.00	0.00	0.00	0.00	\N	sent	2026-04-19 17:57:18.710583+00	2026-04-19 17:56:55.510415+00
\.


--
-- Data for Name: heartbeats; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.heartbeats (id, session_id, charger_id, status, fault_code, fw_version, received_at, temperature_c, device_datetime) FROM stdin;
\.


--
-- Data for Name: orphan_messages; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.orphan_messages (id, charger_id, session_id, event, payload, is_reviewed, received_at) FROM stdin;
1	EZC001	900	charging_ended	{"event": "charging_ended", "offline": true, "datetime": "2026-04-14 11:57:54", "rfid_uid": "14AF7D05", "charger_id": "EZC001", "fault_code": null, "fw_version": "6.0.2", "session_id": 900, "total_kwhr": 0, "temperature_c": 21.69238}	f	2026-04-14 11:58:12.573521+00
2	EZC001	402	charging_ended_error	{"event": "charging_ended_error", "offline": true, "datetime": "2026-04-14 12:05:24", "rfid_uid": "14AF7D05", "charger_id": "EZC001", "fault_code": "E07", "fw_version": "6.0.2", "session_id": 402, "total_kwhr": 0, "temperature_c": 21.62482}	f	2026-04-14 12:05:42.360031+00
3	EZC001	202	charging_ended	{"event": "charging_ended", "offline": true, "datetime": "2026-04-14 12:12:19", "rfid_uid": "14AF7D05", "charger_id": "EZC001", "fault_code": null, "fw_version": "6.0.2", "session_id": 202, "total_kwhr": 0, "temperature_c": 21.53839}	f	2026-04-14 12:12:34.871471+00
4	EZC001	202	charging_ended	{"event": "charging_ended", "offline": true, "datetime": "2026-04-22 11:20:35", "rfid_uid": "14AF7D05", "charger_id": "EZC001", "fault_code": null, "fw_version": "6.0.2", "session_id": 202, "total_kwhr": 0, "temperature_c": 23.45764}	f	2026-04-22 11:20:35.971967+00
5	EZC001	801	charging_ended_error	{"event": "charging_ended_error", "offline": true, "datetime": "", "rfid_uid": "14AF7D05", "charger_id": "EZC001", "fault_code": "E06", "fw_version": "6.0.2", "session_id": 801, "total_kwhr": 0.04, "temperature_c": 0}	f	2026-04-22 11:26:12.456707+00
6	EZC001	801	charging_ended_error	{"event": "charging_ended_error", "offline": true, "datetime": "", "rfid_uid": "14AF7D05", "charger_id": "EZC001", "fault_code": "E06", "fw_version": "6.0.2", "session_id": 801, "total_kwhr": 0, "temperature_c": 0}	f	2026-04-22 11:26:14.140242+00
7	EZC001	202	charging_ended	{"event": "charging_ended", "offline": true, "datetime": "2026-04-22 11:24:36", "rfid_uid": "14AF7D05", "charger_id": "EZC001", "fault_code": null, "fw_version": "6.0.2", "session_id": 202, "total_kwhr": 0, "temperature_c": 26.37793}	f	2026-04-22 11:26:14.174585+00
8	EZC001	202	charging_ended	{"event": "charging_ended", "offline": true, "datetime": "2026-04-22 11:23:54", "rfid_uid": "14AF7D05", "charger_id": "EZC001", "fault_code": null, "fw_version": "6.0.2", "session_id": 202, "total_kwhr": 0, "temperature_c": 26.06186}	f	2026-04-22 11:26:14.210227+00
9	EZC001	14	charging_ended	{"event": "charging_ended", "offline": true, "datetime": "2026-04-22 16:04:26", "rfid_uid": "14AF7D05", "charger_id": "EZC001", "fault_code": null, "fw_version": "6.0.3", "session_id": 14, "stop_epoch": 1776873866, "total_kwhr": 0, "start_epoch": 1776873850, "temperature_c": 38.33307}	f	2026-04-22 16:04:59.625953+00
10	EZC001	15	charging_ended	{"event": "charging_ended", "offline": true, "datetime": "2026-04-22 16:04:39", "rfid_uid": "14AF7D05", "charger_id": "EZC001", "fault_code": null, "fw_version": "6.0.3", "session_id": 15, "stop_epoch": 1776873878, "total_kwhr": 0, "start_epoch": 1776873874, "temperature_c": 38.36401}	f	2026-04-22 16:04:59.626548+00
11	EZC001	16	charging_ended	{"event": "charging_ended", "msg_id": "EZC001-0016-END", "offline": true, "datetime": "2026-05-01 17:03:55", "rfid_uid": "14AF7D05", "charger_id": "EZC001", "fault_code": null, "fw_version": "6.2.3", "session_id": 16, "stop_epoch": 1777655034, "total_kwhr": 0.006, "start_epoch": 1777654868, "end_meter_kwh": 1.433, "temperature_c": 32.58173, "start_meter_kwh": 1.427}	f	2026-05-01 17:06:41.481431+00
12	EZC001	17	charging_ended	{"event": "charging_ended", "msg_id": "EZC001-0017-END", "offline": true, "datetime": "2026-05-01 17:05:39", "rfid_uid": "14AF7D05", "charger_id": "EZC001", "fault_code": null, "fw_version": "6.2.3", "session_id": 17, "stop_epoch": 1777655138, "total_kwhr": 0.002, "start_epoch": 1777655082, "end_meter_kwh": 1.435, "temperature_c": 32.71704, "start_meter_kwh": 1.433}	f	2026-05-01 17:06:41.481363+00
13	EZC001	18	charging_ended_error	{"event": "charging_ended_error", "msg_id": "EZC001-0018-ERR", "offline": true, "datetime": "2026-05-01 17:09:07", "rfid_uid": "14AF7D05", "charger_id": "EZC001", "fault_code": "E07", "fw_version": "6.2.3", "session_id": 18, "stop_epoch": 1777655347, "total_kwhr": 0.004, "start_epoch": 1777655176, "end_meter_kwh": 1.439, "temperature_c": 33.05298, "start_meter_kwh": 1.435}	f	2026-05-01 17:09:08.129467+00
14	EZC001	18	charging_ended_error	{"event": "charging_ended_error", "msg_id": "EZC001-0018-ERR", "offline": false, "datetime": "2026-05-01 17:09:06", "rfid_uid": "14AF7D05", "charger_id": "EZC001", "fault_code": "E07", "fw_version": "6.2.3", "session_id": 18, "stop_epoch": 1777655347, "total_kwhr": 0.004, "start_epoch": 1777655176, "end_meter_kwh": 1.439, "temperature_c": 33.05, "start_meter_kwh": 1.435}	f	2026-05-01 17:09:08.204837+00
\.


--
-- Data for Name: rfid_cards; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.rfid_cards (id, flat_id, uid, label, is_active, created_at) FROM stdin;
5	3	13AF7D05	Owner Card	t	2026-03-25 19:03:32.625123+00
6	3	3B3C4D5E	Spouse Card	t	2026-03-25 19:03:32.625123+00
7	4	8F8E7D6C	Car Key	t	2026-03-25 19:03:32.625123+00
3	1	14AF7D05	Owner Card	t	2026-03-25 12:12:20.986535+00
4	1	2B3C4D5E	Spouse Card	t	2026-03-25 12:12:20.986535+00
8	1	14AF7D15	\N	t	2026-04-04 07:56:32.986424+00
\.


--
-- Data for Name: pending_commands; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.pending_commands (id, charger_id, cmd, flat_id, rfid_uid, rfid_card_id, status, reason, created_at, expires_at, resolved_at) FROM stdin;
\.


--
-- Data for Name: society_admins; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.society_admins (user_id, society_id, assigned_at) FROM stdin;
2	1	2026-03-25 12:10:50.540679+00
3	2	2026-03-25 19:04:09.09933+00
4	2	2026-03-27 14:02:57.852369+00
\.


--
-- Data for Name: tickets; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.tickets (id, title, description, status, priority, category, created_by_id, society_id, assigned_to_id, created_at, updated_at, resolved_at) FROM stdin;
2	abcde	edefdwehfehfinfe fknfnvle felf4go4oem	closed	low	other	2	1	\N	2026-05-04 13:39:22.594476+00	2026-05-04 14:09:38.109705+00	2026-05-04 14:09:38.109705+00
5	2nd check	checking if there is any increase in response time	resolved	low	other	2	1	\N	2026-05-05 06:22:15.858736+00	2026-05-05 06:24:46.621128+00	2026-05-05 06:24:46.621128+00
3	raghav	dqccwewccwcwew	closed	medium	charger	2	1	\N	2026-05-04 13:41:13.989947+00	2026-05-06 06:16:25.396366+00	2026-05-06 06:16:25.396366+00
\.


--
-- Data for Name: ticket_comments; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.ticket_comments (id, ticket_id, author_id, body, is_internal, created_at) FROM stdin;
1	3	1	i have solved the issue	f	2026-05-04 13:42:48.965858+00
2	3	2	okay thanks	f	2026-05-04 13:44:04.093895+00
3	2	1	working on it	f	2026-05-04 13:45:44.453282+00
5	2	1	resolved the issue	f	2026-05-04 14:07:21.674638+00
6	2	1	closing the ticket	f	2026-05-04 14:08:02.912731+00
7	5	1	okay checking the speed now	f	2026-05-05 06:23:40.999502+00
8	5	2	okay thanks	f	2026-05-05 06:25:19.803406+00
9	3	2	okay close this ticket now	f	2026-05-06 06:14:43.850572+00
10	3	1	closing the ticket	f	2026-05-06 06:15:38.119184+00
\.


--
-- Name: charger_status_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.charger_status_id_seq', 192, true);


--
-- Name: chargers_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.chargers_id_seq', 4, true);


--
-- Name: charging_sessions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.charging_sessions_id_seq', 17, true);


--
-- Name: command_logs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.command_logs_id_seq', 1, false);


--
-- Name: flat_bills_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.flat_bills_id_seq', 6, true);


--
-- Name: flats_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.flats_id_seq', 4, true);


--
-- Name: heartbeats_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.heartbeats_id_seq', 1, false);


--
-- Name: monthly_bills_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.monthly_bills_id_seq', 4, true);


--
-- Name: orphan_messages_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.orphan_messages_id_seq', 14, true);


--
-- Name: pending_commands_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.pending_commands_id_seq', 1, false);


--
-- Name: rfid_cards_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.rfid_cards_id_seq', 8, true);


--
-- Name: societies_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.societies_id_seq', 2, true);


--
-- Name: ticket_comments_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.ticket_comments_id_seq', 10, true);


--
-- Name: tickets_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.tickets_id_seq', 5, true);


--
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.users_id_seq', 4, true);


--
-- PostgreSQL database dump complete
--

\unrestrict idevsddjB6HcYc6hveTGIT2dAkpe8h6afx49sTLa1Fgocfj1RCEWJhDDxVrhLgt

