# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Registro centralizado de rutas de la API.
Para agregar un nuevo módulo:
  1. Crear backend/routers/nuevo_modulo.py con un APIRouter()
  2. Importarlo aquí y agregarlo a ROUTES
  3. Listo — se registra automáticamente en main.py
"""
from fastapi import FastAPI

from routers import (
    auth,
    customers,
    profiles,
    carriers,
    carrier_groups,
    lan_peers,
    rates,
    firewall,
    cdrs,
    reports,
    invoices,
    live,
    portal,
    traces,
    timeseries,
    system,
    quality,
    alerts,
    admin_users,
    audit,
    areas,
    cron_health,
    external_sync,
    webhooks,
    disconnect_policies,
    routing_sim,
    traffic_sampling,
    pricelists,
    comments,
    mail_config,
    hep_stats,
    api_v1,
    reseller,
    services_status,
    system_services,
    system_logs,
    billing_recalc,
    system_infra,
)

ROUTES = [
    # (router,            prefix,                    tags)
    (auth.router,         "/api/auth",               ["Auth"]),
    (customers.router,    "/api/admin/customers",    ["Admin · Customers"]),
    (profiles.router,     "/api/admin/profiles",     ["Admin · Profiles"]),
    (carriers.router,     "/api/admin/carriers",     ["Admin · Carriers"]),
    (carrier_groups.router, "/api/admin/carrier-groups", ["Admin · Carrier Groups"]),
    (lan_peers.router,     "/api/admin/lan-peers",     ["Admin · LAN Peers"]),
    (rates.router,        "/api/admin/rates",        ["Admin · Rates"]),
    (firewall.router,     "/api/admin/firewall",     ["Admin · Firewall"]),
    (cdrs.router,         "/api/admin/cdrs",         ["Admin · CDRs"]),
    (reports.router,      "/api/admin/reports",      ["Admin · Reports"]),
    (invoices.router,     "/api/admin/invoices",     ["Admin · Invoices"]),
    (live.router,         "/api/admin/live",         ["Admin · Live"]),
    (portal.router,       "/api/my",                 ["Client Portal"]),
    (traces.router,       "/api/admin/traces",       ["Admin · Traces"]),
    (timeseries.router,   "/api/timeseries",         ["Timeseries"]),
    (system.router,       "/api/admin/system",       ["Admin · System"]),
    (quality.router,      "/api/quality",            ["Quality · ASR"]),
    (alerts.router,       "/api/admin/alerts",       ["Admin · Alerts"]),
    (admin_users.router,  "/api/admin/users",        ["Admin · Users"]),
    (audit.router,        "/api/admin/audit",        ["Admin · Audit"]),
    (areas.router,        "/api/admin/areas",        ["Admin · Areas"]),
    (cron_health.router,  "/api/admin/cron-health",  ["Admin · Cron Health"]),
    (external_sync.router, "/api/admin/external-sync", ["Admin · External Sync"]),
    (webhooks.router,      "/api/admin/webhooks",     ["Admin · Webhooks"]),
    (disconnect_policies.router, "/api/admin/disconnect-policies", ["Admin · Disconnect Policies"]),
    (routing_sim.router,   "/api/admin/routing",      ["Admin · Routing Simulation"]),
    (traffic_sampling.router, "/api/admin/traffic-sampling", ["Admin · Traffic Sampling"]),
    (pricelists.router,    "/api/admin/pricelists",   ["Admin · Pricelists"]),
    (comments.router,      "/api/admin/comments",     ["Admin · Comments"]),
    (mail_config.router,   "/api/admin/mail-config",  ["Admin · Mail Config"]),
    (hep_stats.router,     "/api/admin/hep-stats",    ["Admin · HEP Stats"]),
    (api_v1.router,        "/api/v1",                 ["API v1 · Clientes"]),
    (reseller.router,      "/api/reseller",           ["Reseller"]),
    (services_status.router, "/api/admin/services-status", ["Admin · Services Status"]),
    (system_services.router, "/api/admin/system-services", ["Admin · System Services"]),
    (system_logs.router,     "/api/admin/system/logs",  ["Admin · System Logs"]),
    (billing_recalc.router,  "/api/admin/billing-recalc", ["Admin · Billing Recalc"]),
    (system_infra.router,    "/api/admin/system/infra", ["Admin · System Infra"]),
]


def register_routes(app: FastAPI) -> None:
    for router, prefix, tags in ROUTES:
        app.include_router(router, prefix=prefix, tags=tags)
