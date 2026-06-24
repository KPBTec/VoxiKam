# la plataforma anterior — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2025 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2025 – Todos los derechos reservados.

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
)

ROUTES = [
    # (router,            prefix,                    tags)
    (auth.router,         "/api/auth",               ["Auth"]),
    (customers.router,    "/api/admin/customers",    ["Admin · Customers"]),
    (profiles.router,     "/api/admin/profiles",     ["Admin · Profiles"]),
    (carriers.router,     "/api/admin/carriers",     ["Admin · Carriers"]),
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
]


def register_routes(app: FastAPI) -> None:
    for router, prefix, tags in ROUTES:
        app.include_router(router, prefix=prefix, tags=tags)
