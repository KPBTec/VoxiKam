# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# MIT License · https://t.me/KPBTec · By KPBTec

import asyncio
import logging
import math
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import text
from dotenv import load_dotenv
import os

load_dotenv()

# Sin esto, el logger raíz de Python nunca queda configurado — su nivel
# efectivo por defecto es WARNING y el handler "lastResort" descarta todo lo
# que esté debajo, así que cada logging.getLogger(__name__)/log.info(...) de
# todo el backend (billing worker incluido) nunca llegaba a ningún lado, ni
# a journalctl ni a ningún archivo — no era un problema de retención, el
# mensaje jamás se emitía. StandardOutput/StandardError=journal en el
# .service ya capturan stdout/stderr del proceso, así que basta con un
# StreamHandler simple acá.
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

from database import AsyncSessionLocal
from routes import register_routes
from middleware.security import SecurityMiddleware
from alerts import check_balance_alert
from disconnect_policies import check_disconnect_policies
from routers.system import get_domain
import cors_state

log = logging.getLogger("billing-worker")

ALLOWED_ORIGINS = cors_state.seed_from_env()


def _billable_blocks(seconds: int, initblock: int, billingblock: int) -> int:
    """Mismo cálculo que backend/routers/cdrs.py::_billable_blocks() — los
    primeros `initblock` segundos se facturan como bloque fijo, el resto se
    redondea hacia arriba en incrementos de `billingblock`. `initblock=0`
    (carrier_rates no tiene esta columna) degenera a solo billingblock.

    Encontrado en la auditoría global v2.38.0: este worker (el camino de
    respaldo) ni siquiera LEÍA billingblock/initblock — facturaba sobre
    billsec crudo. Un CDR que cayera acá podía cobrar distinto que el mismo
    CDR procesado por el camino síncrono, con billingblock≠1s (ej. 60 o 6)."""
    if seconds <= initblock:
        return initblock
    return initblock + math.ceil((seconds - initblock) / billingblock) * billingblock


async def _calc_bill(db, customer_id: int, carrier_id, dst: str, billsec: int):
    """Devuelve (buycost, sessionbill, reseller_cost, matched_prefix) para un
    CDR contestado. reseller_cost es None salvo que el cliente dependa de un
    reseller — mismo criterio que backend/routers/cdrs.py::ingest_cdr(), que
    es el camino normal (síncrono); este worker es solo el fallback para
    CDRs que quedaron en buycost=0 (ej: el customer_id/carrier_id se
    resolvió después).

    matched_prefix: hasta acá este worker no lo devolvía — routers/areas.py
    (rentabilidad por área) hace JOIN contra cdrs.prefix_matched, así que
    todo CDR tarifado por ESTE camino (no por ingest_cdr) quedaba con
    prefix_matched NULL permanentemente, salvo que alguien corriera el
    backfill manual desde el panel. Se agrega acá para que los dos caminos
    dejen el CDR en el mismo estado, sin cambiar ningún monto facturado."""
    buycost, sessionbill = 0.0, 0.0
    reseller_cost = None
    matched_prefix = None

    if carrier_id and billsec > 0:
        rb = await db.execute(text("""
            SELECT cr.buy_rate, cr.billingblock, cr.connectcharge
            FROM carrier_rates cr
            JOIN prefixes p ON cr.prefix_id = p.id
            WHERE cr.carrier_id = :cid AND :dst LIKE CONCAT(p.prefix, '%')
            ORDER BY LENGTH(p.prefix) DESC LIMIT 1
        """), {"cid": carrier_id, "dst": dst})
        row = rb.mappings().first()
        if row:
            blocks  = _billable_blocks(billsec, 0, int(row["billingblock"]))
            buycost = round(blocks / 60 * float(row["buy_rate"]) + float(row["connectcharge"]), 6)

    parent_customer_id = None
    if customer_id and billsec > 0:
        rs = await db.execute(text("""
            SELECT r.rateinitial, r.initblock, r.billingblock, r.connectcharge,
                   r.minimal_time_charge, p.prefix, cu.parent_customer_id
            FROM rates r
            JOIN prefixes p   ON r.prefix_id   = p.id
            JOIN customers cu ON r.rate_plan_id = cu.rate_plan_id AND cu.id = :cid
            WHERE :dst LIKE CONCAT(p.prefix, '%') AND r.status = 'active'
            ORDER BY LENGTH(p.prefix) DESC LIMIT 1
        """), {"cid": customer_id, "dst": dst})
        row = rs.mappings().first()
        if row:
            billable    = max(billsec, int(row["minimal_time_charge"] or 0))
            blocks      = _billable_blocks(billable, int(row["initblock"]), int(row["billingblock"]))
            sessionbill = round(blocks / 60 * float(row["rateinitial"]) + float(row["connectcharge"]), 6)
            matched_prefix = row["prefix"]
            parent_customer_id = row["parent_customer_id"]

        if parent_customer_id and billsec > 0:
            rr = await db.execute(text("""
                SELECT r.rateinitial, r.initblock, r.billingblock, r.connectcharge, r.minimal_time_charge
                FROM rates r
                JOIN customers cu ON r.rate_plan_id = cu.rate_plan_id AND cu.id = :pid
                JOIN prefixes p   ON r.prefix_id = p.id
                WHERE :dst LIKE CONCAT(p.prefix, '%') AND r.status = 'active'
                ORDER BY LENGTH(p.prefix) DESC LIMIT 1
            """), {"pid": parent_customer_id, "dst": dst})
            reseller_row = rr.mappings().first()
            if reseller_row:
                billable_r = max(billsec, int(reseller_row["minimal_time_charge"] or 0))
                blocks_r   = _billable_blocks(billable_r, int(reseller_row["initblock"]), int(reseller_row["billingblock"]))
                reseller_cost = round(blocks_r / 60 * float(reseller_row["rateinitial"]) + float(reseller_row["connectcharge"]), 6)

    return buycost, sessionbill, reseller_cost, matched_prefix


async def _billing_worker():
    """
    Cada 30 s procesa CDRs escritos por Kamailio (buycost=0) y calcula tarifas
    desde carrier_rates y rates. También descuenta balance del cliente.
    """
    while True:
        await asyncio.sleep(30)
        try:
            async with AsyncSessionLocal() as db:
                # start_ts >= (ahora - 2 días) en el WHERE (no solo en el UPDATE de
                # abajo) — permite partition pruning real en el SELECT. Sin esto,
                # cada corrida (cada 30s) escaneaba TODOS los meses de cdrs
                # buscando buycost=0, aunque los CDRs viejos ya estén tarifados
                # hace rato — con la tabla en producción ya en varios millones de
                # filas, esto encontrado saturando CPU real (varios hilos de
                # mariadbd a full, EXPLAIN mostrando ~2M filas examinadas por
                # corrida). 2 días de margen es generoso — un CDR nunca debería
                # tardar más que este ciclo (30s) en tarifarse salvo que el
                # worker haya estado caído, y ese caso igual entra en la ventana.
                # FOR UPDATE SKIP LOCKED — con --workers > 1 (uvicorn multi-proceso,
                # ver deploy.sh WORKERS=CPUs-1) cada proceso corre su propia copia de
                # este worker cada 30s. Sin esto, dos procesos podían tomar el mismo
                # CDR pendiente en la misma ventana y facturarlo dos veces (doble
                # descuento de balance, doble fila en balance_transactions para la
                # misma llamada). Con SKIP LOCKED, cada proceso bloquea las filas que
                # toma y los demás saltan esas filas en vez de esperarlas — sets
                # disjuntos garantizados. Requiere MariaDB 10.6+ (Debian 12 trae 10.11).
                rows = await db.execute(text("""
                    SELECT id, call_id, customer_id, carrier_id, dst_number, billsec, start_ts
                    FROM cdrs
                    WHERE disposition = 'ANSWERED'
                      AND billsec > 0
                      AND buycost = 0
                      AND sessionbill = 0
                      AND customer_id IS NOT NULL
                      AND start_ts >= NOW() - INTERVAL 2 DAY
                    LIMIT 100
                    FOR UPDATE SKIP LOCKED
                """))
                pending = rows.fetchall()

                affected_customers: set[int] = set()
                for cdr in pending:
                    buycost, sessionbill, reseller_cost, matched_prefix = await _calc_bill(
                        db, cdr.customer_id, cdr.carrier_id,
                        cdr.dst_number or "", cdr.billsec
                    )
                    # start_ts en el WHERE permite partition pruning (cdrs está particionado por mes)
                    await db.execute(text(
                        "UPDATE cdrs SET buycost=:bc, reseller_cost=:rc, sessionbill=:sb, prefix_matched=:pfx WHERE id=:id AND start_ts=:start_ts"
                    ), {"bc": buycost, "rc": reseller_cost, "sb": sessionbill, "pfx": matched_prefix,
                        "id": cdr.id, "start_ts": cdr.start_ts})
                    if sessionbill > 0:
                        await db.execute(text(
                            "UPDATE customers SET balance = balance - :bill WHERE id = :cid"
                        ), {"bill": sessionbill, "cid": cdr.customer_id})
                        bal_row = await db.execute(text(
                            "SELECT balance FROM customers WHERE id = :cid"
                        ), {"cid": cdr.customer_id})
                        new_balance = bal_row.scalar()
                        await db.execute(text("""
                            INSERT INTO balance_transactions
                                (customer_id, type, amount, balance_after, reference)
                            VALUES (:cid, 'cdr', :amount, :bal, :ref)
                        """), {"cid": cdr.customer_id, "amount": -float(sessionbill),
                                "bal": new_balance, "ref": cdr.call_id})
                        affected_customers.add(cdr.customer_id)

                if pending:
                    await db.commit()
                    log.info("Billing: %d CDRs tarifados", len(pending))

                for cid in affected_customers:
                    await check_balance_alert(db, cid)
        except Exception:
            log.exception("Billing worker error")


async def _stale_calls_cleaner():
    """
    Elimina de active_calls registros zombie con más de 90 minutos.
    Corre al inicio (limpia lo que dejó un restart de Kamailio, que pierde
    todo el estado de diálogos) y luego cada 15 minutos.
    """
    while True:
        try:
            async with AsyncSessionLocal() as db:
                r = await db.execute(text("""
                    DELETE FROM active_calls
                    WHERE TIMESTAMPDIFF(MINUTE, started_at, NOW()) > 90
                """))
                await db.commit()
                if r.rowcount:
                    log.warning("Stale cleaner: %d zombie(s) eliminados de active_calls", r.rowcount)
        except Exception:
            log.exception("Stale cleaner error")
        await asyncio.sleep(15 * 60)


async def _disconnect_policy_checker():
    """
    Cada 5 min — evalúa disconnect_policies contra traffic_quality_hourly
    (que ya agrega cron_quality.py cada minuto). Solo avisa, nunca bloquea.
    """
    while True:
        await asyncio.sleep(5 * 60)
        try:
            async with AsyncSessionLocal() as db:
                await check_disconnect_policies(db)
        except Exception:
            log.exception("Disconnect policy checker error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Si desde Sistema → Dominio de acceso ya se guardó un FQDN antes de
    # este arranque, lo agregamos acá — un restart normal no debe perder
    # ese origen CORS (ver routers/system.py::set_domain).
    try:
        async with AsyncSessionLocal() as db:
            domain, web_port = await get_domain(db)
            if domain:
                cors_state.add_origin(domain, web_port)
    except Exception:
        log.exception("No se pudo leer el dominio persistido al arrancar (¿DB no lista todavía?)")

    t1 = asyncio.create_task(_billing_worker())
    t2 = asyncio.create_task(_stale_calls_cleaner())
    t3 = asyncio.create_task(_disconnect_policy_checker())
    yield
    for t in [t1, t2, t3]:
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass


# /api/docs, /api/redoc y /api/openapi.json estaban SIEMPRE expuestos, sin
# login — cualquiera sin cuenta podía enumerar el esquema completo de la API
# (todos los routers, modelos, parámetros): no es una vulnerabilidad en sí,
# pero es reconocimiento gratis de la superficie completa de ataque para
# quien esté probando el server. Off por default; ENABLE_API_DOCS=true en
# backend/.env lo prende para depurar en un entorno que no sea producción.
_DOCS_ON = os.getenv("ENABLE_API_DOCS", "false").lower() == "true"

app = FastAPI(
    title="VoxiKam API",
    version="2.2",
    docs_url="/api/docs" if _DOCS_ON else None,
    redoc_url="/api/redoc" if _DOCS_ON else None,
    openapi_url="/api/openapi.json" if _DOCS_ON else None,
    servers=[{"url": f"http://{os.getenv('DOMAIN', 'localhost')}:{os.getenv('WEB_PORT', '7666')}"}],
    lifespan=lifespan,
)

app.add_middleware(SecurityMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)

register_routes(app)


@app.get("/api/health", tags=["System"])
async def health():
    return {"status": "ok", "service": "voxikam", "version": "2.2"}


class ClientErrorIn(BaseModel):
    message: str = Field(max_length=2000)
    stack: str = Field(default="", max_length=4000)
    url: str = Field(default="", max_length=500)


@app.post("/api/client-errors", tags=["System"])
async def report_client_error(body: ClientErrorIn):
    """
    Antes de esto, un crash de React o un fetch fallido se perdía en la
    consola del navegador del usuario — cero rastro para el equipo. Llamado
    desde frontend/app/error.tsx. Sin auth a propósito (tiene que funcionar
    incluso si el usuario ya perdió la sesión) y sin escritura a DB — solo
    log.error(), que ahora sí llega a journalctl (ver logging.basicConfig
    arriba). nginx ya lo cubre con el rate-limit general de /api/.
    """
    log.error("CLIENT_ERROR url=%s message=%s stack=%s", body.url, body.message, body.stack[:1000])
    return {"ok": True}
