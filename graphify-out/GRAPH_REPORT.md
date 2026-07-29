# Graph Report - .  (2026-07-29)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 1614 nodes · 3346 edges · 117 communities (80 shown, 37 thin omitted)
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 34 edges (avg confidence: 0.62)
- Token cost: 4,955 input · 1,313 output

## Graph Freshness
- Built from commit: `a0f071de`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Event Logging
- Customer Management
- Audit and Policies
- Area Reports API
- Alert Notifications
- Dashboard Layouts
- Admin Management Pages
- System Migration Scripts
- Live Call Monitoring
- Authentication and Permissions
- Audit and Billing UI
- Customer Detail Portal
- Project Dependencies
- CORS and Billing Worker
- Billing Recalculation Logic
- Inbound Routing UI
- TypeScript Configuration
- HEP Protocol Listener
- CDR Management UI
- Carrier Group Management
- Carrier and Rates API
- Firewall and Fail2Ban
- Pricelist Management
- Database Router Middleware
- Infrastructure Control
- ClickHouse and PCAP Tracing
- Deployment Scripts
- Alert Rules API
- Infrastructure Health Monitoring
- System Logs and Status
- Webhook Management
- Invoices and Calls UI
- CDR Ingestion API
- LAN Peer Management
- User Profile Management
- Quality Metrics UI
- SIP Trace Migration
- Email Configuration
- System Domain Settings
- Timeseries Data API
- System Health UI
- SIP Tracing UI
- Carrier Detail UI
- Client Reports UI
- Quality Analysis Logic
- Dashboard KPI Logic
- Carrier Group UI
- Admin Reports UI
- Reseller Group UI
- Entity Comments API
- Admin Billing Recalc UI
- Reseller Billing Recalc UI
- Dialog Statistics Cron
- RTPEngine Maintenance
- System Service Actions
- Traffic Sampling Config
- Prefix Management UI
- Rate Management UI
- External Data Sync
- Database Partitioning Cron
- Timeseries Processing Cron
- Balance Block Sync
- System Config Documentation
- Area Reports UI
- Active Call Cleanup
- Firewall Management UI
- Infrastructure Status UI
- Partition Migration Tool
- System CLI Utility
- Project Metadata
- HEP Statistics
- Area Summary Backfill
- Config Template Generator
- Backfill Status Cron
- Quality Processing Cron
- Backend Infrastructure
- Routing Simulation
- Root App Layout
- Next.js Configuration
- Graphify Plugin
- Service Audit Script
- System Autotune Script
- Invoice Balance Backfill
- Database Backup Script
- Active Call Diagnostics
- Dependency Installation
- TLS Setup Script
- Agent Documentation
- Alerts and Webhooks
- Pricelist Platform
- Next.js Environment
- PostCSS Configuration
- OS Check Script
- Firewall Disable Script
- SIP Stack Installation
- ClickHouse Installation
- System Permissions
- SIP Systemd Services
- Backend Requirements
- Multi-admin Management
- Area Profitability
- Configuration Audit History
- Autotune System
- Cron Job Health
- Disconnect Policies
- External CDR Sync
- Billing Migration
- Table Partitioning
- Routing Simulation
- Traffic Sampling
- Initial Seed Data
- VoxiKam Landing Page
- RTPEngine Configuration

## God Nodes (most connected - your core abstractions)
1. `apiGet()` - 94 edges
2. `record_event()` - 89 edges
3. `_my_cid()` - 48 edges
4. `apiPost()` - 36 edges
5. `require_admin()` - 35 edges
6. `get_db()` - 35 edges
7. `ErrorBanner()` - 35 edges
8. `apiPut()` - 27 edges
9. `diff_and_record()` - 26 edges
10. `apiDelete()` - 26 edges

## Surprising Connections (you probably didn't know these)
- `build_techprefix_rows()` --calls--> `_resolve()`  [INFERRED]
  scripts/gen_dispatcher.py → backend/routers/live.py
- `deploy.sh script` --calls--> `hdr()`  [EXTRACTED]
  deploy.sh → scripts/_colors.sh
- `VoxiKam Platform` --conceptually_related_to--> `Pricelists`  [INFERRED]
  README.md → CHANGELOG.md
- `CDR Ingest Router` --references--> `MariaDB Schema`  [INFERRED]
  backend/README.md → db/README.md
- `FastAPI Backend` --shares_data_with--> `MariaDB Database`  [INFERRED]
  backend/requirements.txt → docs/schema.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **VoxiKam Core Infrastructure** — kamailio_sip_server, mariadb_database, nftables_firewall, backend_fastapi [EXTRACTED 0.90]
- **System Automation Scripts** — gen_nftables_py, gen_dispatcher_py, voxikam_user [INFERRED 0.85]
- **Core Billing & Tarification Flow** — changelog_pricelists, changelog_balance_alerts, changelog_areas_profitability [EXTRACTED 0.90]
- **System Maintenance & Autotune** — changelog_autotune, changelog_cron_health, changelog_partitioning [EXTRACTED 0.85]
- **Security & Observability Stack** — changelog_traffic_sampling, changelog_audit_log, changelog_webhooks [INFERRED 0.75]
- **SIP Billing and CDR Flow** — docs_kamailio_routing_logic, backend_cdrs, db_schema, scripts_cron_summary [EXTRACTED 0.95]
- **VoxiKam Security Stack** — backend_security_middleware, fail2ban_config, scripts_gen_nftables, nginx_config [EXTRACTED 0.90]
- **Infrastructure and Config Generation** — scripts_gen_nftables, scripts_gen_dispatcher, systemd_backend_service, systemd_frontend_service [INFERRED 0.85]

## Communities (117 total, 37 thin omitted)

### Community 0 - "Event Logging"
Cohesion: 0.08
Nodes (91): Para acciones que no son un diff de campo (crear, borrar, activar/desactivar)., record_event(), BaseModel, RecalcRequest, add_carrier_buy_rate(), add_carrier_group_buy_rate(), add_group_rate(), add_own_group_member() (+83 more)

### Community 1 - "Customer Management"
Cohesion: 0.06
Nodes (70): add_ip(), add_prefix(), adjust_balance(), assign_carrier(), assign_carrier_group(), create_client_user(), create_customer(), CustomerCarrierGroupIn (+62 more)

### Community 2 - "Audit and Policies"
Cohesion: 0.07
Nodes (56): diff_and_record(), AsyncSession, record_change(), create_policy(), delete_policy(), list_alerts(), list_columns(), list_policies() (+48 more)

### Community 3 - "Area Reports API"
Cohesion: 0.07
Nodes (58): balance(), cdrs(), AsyncSession, get, area_report(), _area_report_rows(), AreaIn, backfill_status() (+50 more)

### Community 4 - "Alert Notifications"
Cohesion: 0.08
Nodes (55): check_balance_alert(), get_alert_notify_email(), AsyncSession, check_disconnect_policies(), AsyncSession, alert_html(), get_mail_config(), AsyncSession (+47 more)

### Community 5 - "Dashboard Layouts"
Cohesion: 0.06
Nodes (35): Dashboard(), RANGES, TsData, AdminLayout(), ClientLayout(), MODULE_MAP, Overview(), RANGES (+27 more)

### Community 6 - "Admin Management Pages"
Cohesion: 0.06
Nodes (29): Affected, AffectedRow, Rule, Area, AreaGroupsPage(), Country, Carrier, CarriersPage() (+21 more)

### Community 7 - "System Migration Scripts"
Cohesion: 0.08
Nodes (41): get_db(), main(), date, run_summary(), main(), _next_4digit_techprefix(), Mismo criterio que reseller.py::_techprefix_conflicts() — colisión por…, Misma búsqueda que reseller.py::_next_techprefix(), arrancando en 5000 — el… (+33 more)

### Community 8 - "Live Call Monitoring"
Cohesion: 0.07
Nodes (44): CDR Ingest Router, cleanup_stale(), live_calls(), live_connecting(), live_detail(), _prefix_map(), AsyncSession, delete (+36 more)

### Community 9 - "Authentication and Permissions"
Cohesion: 0.08
Nodes (41): create_token(), get_current_user(), has_permission(), hash_password(), AsyncSession, Resuelve un permiso puntual — COALESCE(override del cliente, override del…, Resuelve TODOS los resource_key de una sola vez — usado por login() para armar…, Factory — dependency que verifica un ítem del árbol de permisos granular… (+33 more)

### Community 10 - "Audit and Billing UI"
Cohesion: 0.06
Nodes (28): AuditPage(), AuditRow, ENTITY_LABELS, GROUPS, BillingResetPage(), ResetResult, LivePage(), sec2str() (+20 more)

### Community 11 - "Customer Detail Portal"
Cohesion: 0.08
Nodes (32): BalanceTx, CustomerCarrier, CustomerDetail, CustomerDetailPage(), CustomerGroup, CustomerIP, CustomerPrefix, leafResources() (+24 more)

### Community 12 - "Project Dependencies"
Cohesion: 0.05
Nodes (37): clsx, dependencies, clsx, jose, lucide-react, next, react, react-dom (+29 more)

### Community 13 - "CORS and Billing Worker"
Cohesion: 0.07
Nodes (32): add_origin(), Se llama una sola vez al importar main.py. Mismo fallback que antes…, Agrega un origen sin sacar los que ya había — así un FQDN nuevo no tira abajo…, seed_from_env(), _billable_blocks(), _billing_worker(), _calc_bill(), ClientErrorIn (+24 more)

### Community 14 - "Billing Recalculation Logic"
Cohesion: 0.15
Nodes (27): apply_recalc(), _billable_blocks(), _blocked_invoices(), _customer_names(), get_job(), _job_path(), list_recalc_carriers(), list_recalc_customers() (+19 more)

### Community 15 - "Inbound Routing UI"
Cohesion: 0.09
Nodes (22): EMPTY_FORM, EntrantePage(), LanPeer, CarrierResult, Customer, RateInfo, RoutingSimPage(), SimResult (+14 more)

### Community 16 - "TypeScript Configuration"
Cohesion: 0.07
Nodes (26): compilerOptions, allowJs, esModuleInterop, incremental, isolatedModules, jsx, lib, module (+18 more)

### Community 17 - "HEP Protocol Listener"
Cohesion: 0.12
Nodes (22): _enqueue(), _enqueue_rtcp(), _extract_call_id(), _flush_loop(), _flush_rtcp_loop(), _get_ch_client(), _get_pool(), _hdr() (+14 more)

### Community 18 - "CDR Management UI"
Cohesion: 0.13
Nodes (22): CDR, CdrDetailPanel(), CdrsPage(), dt(), FailedCDR, hangupCauseVariant(), money(), QUALITY_VARIANT (+14 more)

### Community 19 - "Carrier Group Management"
Cohesion: 0.16
Nodes (20): add_member(), CarrierGroupIn, create_group(), delete_group(), get_group(), GroupMemberIn, list_groups(), AsyncSession (+12 more)

### Community 20 - "Carrier and Rates API"
Cohesion: 0.20
Nodes (21): add_buy_rate(), add_group_buy_rate(), BuyRateIn, CarrierIn, create_carrier(), delete_buy_rate(), delete_carrier(), get_buy_rates() (+13 more)

### Community 21 - "Firewall and Fail2Ban"
Cohesion: 0.17
Nodes (21): add_rule(), delete_rule(), fail2ban_config(), fail2ban_status(), fail2ban_unban(), list_rules(), _parse_banned_ips(), AsyncSession (+13 more)

### Community 22 - "Pricelist Management"
Cohesion: 0.17
Nodes (22): create_draft(), _csv_response(), discard_draft(), DraftIn, DraftItemIn, export_draft_csv(), get_draft(), import_csv() (+14 more)

### Community 23 - "Database Router Middleware"
Cohesion: 0.22
Nodes (9): require_admin(), Base, get_db(), list_audit(), AsyncSession, get, FastAPI, register_routes() (+1 more)

### Community 24 - "Infrastructure Control"
Cohesion: 0.23
Nodes (21): disable_tls(), enable_tls(), get_infra_status(), _marker_value(), AsyncSession, BackgroundTasks, BaseModel, get (+13 more)

### Community 25 - "ClickHouse and PCAP Tracing"
Cohesion: 0.13
Nodes (19): AsyncClient, get_ch(), Doble-check con lock — mismo patrón que hep_listener.py::_get_pool(), para que…, _build_pcap(), _classify_query(), download_pcap(), get_stream(), get_trace() (+11 more)

### Community 26 - "Deployment Scripts"
Cohesion: 0.22
Nodes (16): apply_conf(), ask(), ask_secret(), chk_http(), chk_svc(), _drop_db(), deploy.sh script, _spinner() (+8 more)

### Community 27 - "Alert Rules API"
Cohesion: 0.22
Nodes (14): affected_customers(), get_notify_email(), list_rules(), NotifyEmailIn, AsyncSession, BaseModel, field_validator, get (+6 more)

### Community 28 - "Infrastructure Health Monitoring"
Cohesion: 0.22
Nodes (15): alert_html(), check_crons(), check_resources(), get_db(), get_mail_config(), infra_alerts_enabled(), _load_state(), main() (+7 more)

### Community 29 - "System Logs and Status"
Cohesion: 0.21
Nodes (12): cron_health(), _job_status(), get, Path, _tail(), get, _run(), services_status() (+4 more)

### Community 30 - "Webhook Management"
Cohesion: 0.27
Nodes (14): create_webhook(), delete_webhook(), list_events(), list_webhooks(), AsyncSession, BaseModel, delete, get (+6 more)

### Community 31 - "Invoices and Calls UI"
Cohesion: 0.17
Nodes (12): Customer, Invoice, InvoicesPage(), CDR, DISPOSITION_STATE, fmtMoney(), fmtSec(), MyCalls() (+4 more)

### Community 32 - "CDR Ingestion API"
Cohesion: 0.16
Nodes (14): _billable_blocks(), CdrIngestIn, ingest_cdr(), list_cdrs(), list_failed_cdrs(), AsyncSession, BackgroundTasks, BaseModel (+6 more)

### Community 33 - "LAN Peer Management"
Cohesion: 0.19
Nodes (12): add_lan_peer(), delete_lan_peer(), LanPeerIn, list_lan_peers(), AsyncSession, BaseModel, delete, field_validator (+4 more)

### Community 34 - "User Profile Management"
Cohesion: 0.21
Nodes (14): create_profile(), delete_profile(), get_profile(), list_profiles(), list_resources(), ProfileIn, AsyncSession, BaseModel (+6 more)

### Community 35 - "Quality Metrics UI"
Cohesion: 0.19
Nodes (10): num(), pct(), QRow, QualityPage(), ASR_VARIANT, MyQualityPage(), num(), pct() (+2 more)

### Community 36 - "SIP Trace Migration"
Cohesion: 0.30
Nodes (13): _ch_count_from(), cmd_cutover(), cmd_diagnose(), cmd_truncate(), _copy_batches(), _count_from(), get_clickhouse(), get_mysql() (+5 more)

### Community 37 - "Email Configuration"
Cohesion: 0.19
Nodes (13): get_mail_config_status(), MailConfigIn, AsyncSession, BaseModel, get, post, put, Envía un correo de prueba con la config guardada AHORA MISMO — para validar… (+5 more)

### Community 38 - "System Domain Settings"
Cohesion: 0.28
Nodes (12): DomainIn, _fmt_bytes(), get_domain(), get_domain_endpoint(), AsyncSession, BaseModel, get, put (+4 more)

### Community 39 - "Timeseries Data API"
Cohesion: 0.33
Nodes (12): admin_timeseries(), _build_series(), client_timeseries(), _hour_labels_day(), _minute_labels(), AsyncSession, get, _query_day() (+4 more)

### Community 40 - "System Health UI"
Cohesion: 0.24
Nodes (11): CRON_STATUS_LABEL, cronDotCls(), CronJob, cronStatusVariant(), cronTextCls(), fmtAge(), OtherService, ProtocolBlock() (+3 more)

### Community 41 - "SIP Tracing UI"
Cohesion: 0.24
Nodes (9): Badge(), CallSummary, SearchView(), StreamMsg, StreamView(), today(), tsLocal(), sipCodeVariant() (+1 more)

### Community 42 - "Carrier Detail UI"
Cohesion: 0.22
Nodes (9): BuyRate, Carrier, CarrierDetailPage(), Group, GROUP_COLORS, groupBadge(), Prefix, Comment (+1 more)

### Community 43 - "Client Reports UI"
Cohesion: 0.25
Nodes (10): AreaRow, CampaignRow, currentMonth(), DayRow, fmt(), money(), MONTH_NAMES, Monthly (+2 more)

### Community 44 - "Quality Analysis Logic"
Cohesion: 0.27
Nodes (10): _enrich(), _pct(), AsyncSession, get, quality_admin(), _quality_from_cdrs(), quality_my(), ASR Dashboard admin — resumen por hora y cliente. Consulta CDRs directamente… (+2 more)

### Community 45 - "Dashboard KPI Logic"
Cohesion: 0.27
Nodes (10): dashboard(), AsyncSession, get, Para un mes: - Días completados → cdr_summary_day (veloz). - Hoy (si es el mes…, KPIs de hoy para el dashboard admin., Mes más antiguo con datos en toda la plataforma — mismo propósito que…, Para un día específico: - Si es hoy → agrega desde cdrs en vivo. - Si es ayer o…, report_day() (+2 more)

### Community 46 - "Carrier Group UI"
Cohesion: 0.22
Nodes (9): ALGO_LABELS, CarrierGroup, CarrierGroupsPage(), CarrierOpt, CustomerOpt, EMPTY_FORM, GroupDetail, GroupMember (+1 more)

### Community 47 - "Admin Reports UI"
Cohesion: 0.24
Nodes (4): groupBy(), MONTH_NAMES, ReportsPage(), sumRows()

### Community 48 - "Reseller Group UI"
Cohesion: 0.22
Nodes (9): ALGO_LABELS, AssignableCarrier, CarrierGroup, EMPTY_FORM, GroupDetail, GroupMember, ResellerCarrierGroupsPage(), SubCustomerOpt (+1 more)

### Community 49 - "Entity Comments API"
Cohesion: 0.25
Nodes (9): CommentIn, create_comment(), delete_comment(), list_comments(), AsyncSession, BaseModel, delete, get (+1 more)

### Community 50 - "Admin Billing Recalc UI"
Cohesion: 0.28
Nodes (7): BillingRecalcPage(), BlockedInvoice, CustomerDelta, fmt(), Option, RecalcResult, todayISO()

### Community 51 - "Reseller Billing Recalc UI"
Cohesion: 0.28
Nodes (7): BlockedInvoice, CustomerDelta, fmt(), Option, RecalcResult, ResellerBillingRecalcPage(), todayISO()

### Community 52 - "Dialog Statistics Cron"
Cohesion: 0.33
Nodes (8): capture(), fetch_known_prefixes(), get_db(), _kill(), main(), Mata y reapea un proceso que quedó colgado — sin esto, un kamcmd que no…, None = falló la captura — el caller NO debe pisar el snapshot anterior con…, customers.techprefix (principal) + customer_prefixes.techprefix (campaña),…

### Community 53 - "RTPEngine Maintenance"
Cohesion: 0.36
Nodes (6): die(), info(), ok(), sep(), fix_rtpengine.sh script, warn()

### Community 54 - "System Service Actions"
Cohesion: 0.25
Nodes (8): act_on_service(), list_services(), AsyncSession, BaseModel, get, post, _run(), ServiceAction

### Community 55 - "Traffic Sampling Config"
Cohesion: 0.36
Nodes (7): get_config(), AsyncSession, BaseModel, get, put, RetentionIn, set_config()

### Community 56 - "Prefix Management UI"
Cohesion: 0.29
Nodes (7): Area, Country, Group, GROUP_COLORS, groupBadge(), Prefix, PrefixesPage()

### Community 57 - "Rate Management UI"
Cohesion: 0.29
Nodes (7): Group, GROUP_COLORS, groupBadge(), Plan, Prefix, Rate, RatesPage()

### Community 58 - "External Data Sync"
Cohesion: 0.46
Nodes (7): connect_target(), get_config(), get_local_db(), main(), _placeholder(), Retorna (cursor_id, rows_synced, rows_failed, sample_errors). rows_synced…, sync_batches()

### Community 59 - "Database Partitioning Cron"
Cohesion: 0.43
Nodes (7): _add_partition(), get_db(), main(), maintain_cdrs(), _partition_names(), date, REORGANIZE p_future para separar `name` (< boundary) y dejar p_future de nuevo…

### Community 60 - "Timeseries Processing Cron"
Cohesion: 0.39
Nodes (7): get_ch(), get_db(), main(), None si no hay CLICKHOUSE_URL configurado o falla la conexión — la resolución…, call_id → carrier_id, cruzando contra el dst_ip real de sip_traces., _resolve_carriers(), run()

### Community 61 - "Balance Block Sync"
Cohesion: 0.39
Nodes (7): fetch_blocked(), get_db(), main(), Techprefix (principal + campaña) de todo cliente prepago con balance<=0. Sin…, Reemplaza TODO el contenido de balance_block_map — mismo criterio "regenerar…, reload_kamailio(), sync_balance_block()

### Community 62 - "System Config Documentation"
Cohesion: 0.29
Nodes (7): Cron Documentation, gen_dispatcher.py, gen_nftables.py, Kamailio SIP Server, nftables Firewall, Firewall Configuration Documentation, Jinja2 Templates Documentation

### Community 63 - "Area Reports UI"
Cohesion: 0.33
Nodes (5): AreasReportPage(), CustomerOpt, MONTH_NAMES, ReportRow, todayISO()

### Community 64 - "Active Call Cleanup"
Cohesion: 0.43
Nodes (6): _alert_restart_orphans(), _archive_orphans_as_cdrs(), get_db(), main(), Correo best-effort al admin — un fallo acá nunca debe frenar el cleanup (mismo…, SELECT + INSERT INTO cdrs (disposition='RESTART_ORPHANED') para cada fila de…

### Community 65 - "Firewall Management UI"
Cohesion: 0.40
Nodes (5): EMPTY, FirewallPage(), FirewallRule, SERVICES, svcBadge()

### Community 66 - "Infrastructure Status UI"
Cohesion: 0.47
Nodes (5): Action, fmtAgo(), fmtBytes(), Infra, InfraPage()

### Community 67 - "Partition Migration Tool"
Cohesion: 0.60
Nodes (5): get_db(), is_partitioned(), main(), migrate_table(), row_count()

### Community 68 - "System CLI Utility"
Cohesion: 0.47
Nodes (4): _as_root(), voxikam-cli.sh script, SVC_MAP, _usage()

### Community 70 - "HEP Statistics"
Cohesion: 0.70
Nodes (4): hep_stats(), _is_fresh(), get, _read_stats()

### Community 71 - "Area Summary Backfill"
Cohesion: 0.60
Nodes (4): get_db(), main(), Reconstruye cdr_summary_day_area para cada día con CDRs, desde el más viejo…, _rebuild_area_summary()

### Community 72 - "Config Template Generator"
Cohesion: 0.70
Nodes (4): main(), Path, render(), write()

### Community 73 - "Backfill Status Cron"
Cohesion: 0.83
Nodes (3): get_db(), main(), run()

### Community 74 - "Quality Processing Cron"
Cohesion: 0.83
Nodes (3): get_db(), main(), run()

### Community 75 - "Backend Infrastructure"
Cohesion: 0.67
Nodes (3): FastAPI Backend, Database Schema Documentation, MariaDB Database

### Community 76 - "Routing Simulation"
Cohesion: 0.67
Nodes (3): AsyncSession, get, simulate()

## Knowledge Gaps
- **247 isolated node(s):** `Rule`, `AffectedRow`, `Affected`, `Area`, `Country` (+242 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **37 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `record_event()` connect `Event Logging` to `LAN Peer Management`, `Audit and Policies`, `Area Reports API`, `Alert Notifications`, `Email Configuration`, `User Profile Management`, `System Domain Settings`, `Authentication and Permissions`, `Billing Recalculation Logic`, `Carrier Group Management`, `Carrier and Rates API`, `Firewall and Fail2Ban`, `Pricelist Management`, `Database Router Middleware`, `Infrastructure Control`, `System Service Actions`, `Webhook Management`?**
  _High betweenness centrality (0.063) - this node is a cross-community bridge._
- **Why does `MariaDB Schema` connect `Live Call Monitoring` to `System Migration Scripts`?**
  _High betweenness centrality (0.051) - this node is a cross-community bridge._
- **Why does `CDR Ingest Router` connect `Live Call Monitoring` to `Database Router Middleware`?**
  _High betweenness centrality (0.051) - this node is a cross-community bridge._
- **What connects `Rule`, `AffectedRow`, `Affected` to the rest of the system?**
  _247 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Event Logging` be split into smaller, more focused modules?**
  _Cohesion score 0.07784557121817799 - nodes in this community are weakly interconnected._
- **Should `Customer Management` be split into smaller, more focused modules?**
  _Cohesion score 0.06210526315789474 - nodes in this community are weakly interconnected._
- **Should `Audit and Policies` be split into smaller, more focused modules?**
  _Cohesion score 0.06721311475409836 - nodes in this community are weakly interconnected._