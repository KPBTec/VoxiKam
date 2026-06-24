# la plataforma anterior — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# MIT License · https://t.me/KPBTec · By KPBTec

import asyncio
import logging
import math
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from dotenv import load_dotenv
import os

load_dotenv()

from database import AsyncSessionLocal
from routes import register_routes
from middleware.security import SecurityMiddleware

log = logging.getLogger("billing-worker")

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "").split(",")
if not any(ALLOWED_ORIGINS):
    ALLOWED_ORIGINS = [f"http://{os.getenv('DOMAIN', 'localhost')}:{os.getenv('WEB_PORT', '7666')}"]


async def _calc_bill(db, customer_id: int, carrier_id, dst: str, billsec: int):
    """Devuelve (buycost, sessionbill) para un CDR contestado."""
    buycost, sessionbill = 0.0, 0.0

    if carrier_id and billsec > 0:
        rb = await db.execute(text("""
            SELECT cr.buy_rate, cr.connect_charge
            FROM carrier_rates cr
            JOIN prefixes p ON cr.prefix_id = p.id
            WHERE cr.carrier_id = :cid AND :dst LIKE CONCAT(p.prefix, '%')
            ORDER BY LENGTH(p.prefix) DESC LIMIT 1
        """), {"cid": carrier_id, "dst": dst})
        row = rb.mappings().first()
        if row:
            buycost = round(billsec / 60 * float(row["buy_rate"]) + float(row["connect_charge"]), 6)

    if customer_id and billsec > 0:
        rs = await db.execute(text("""
            SELECT r.rateinitial, r.connectcharge, r.minimal_time_charge
            FROM rates r
            JOIN prefixes p   ON r.prefix_id   = p.id
            JOIN customers cu ON r.rate_plan_id = cu.rate_plan_id AND cu.id = :cid
            WHERE :dst LIKE CONCAT(p.prefix, '%') AND r.status = 'active'
            ORDER BY LENGTH(p.prefix) DESC LIMIT 1
        """), {"cid": customer_id, "dst": dst})
        row = rs.mappings().first()
        if row:
            billable    = max(billsec, int(row["minimal_time_charge"] or 0))
            sessionbill = round(billable / 60 * float(row["rateinitial"]) + float(row["connectcharge"]), 6)

    return buycost, sessionbill


async def _billing_worker():
    """
    Cada 30 s procesa CDRs escritos por Kamailio (buycost=0) y calcula tarifas
    desde carrier_rates y rates. También descuenta balance del cliente.
    """
    while True:
        await asyncio.sleep(30)
        try:
            async with AsyncSessionLocal() as db:
                rows = await db.execute(text("""
                    SELECT id, customer_id, carrier_id, dst_number, billsec
                    FROM cdrs
                    WHERE disposition = 'ANSWERED'
                      AND billsec > 0
                      AND buycost = 0
                      AND sessionbill = 0
                      AND customer_id IS NOT NULL
                    LIMIT 100
                """))
                pending = rows.fetchall()

                for cdr in pending:
                    buycost, sessionbill = await _calc_bill(
                        db, cdr.customer_id, cdr.carrier_id,
                        cdr.dst_number or "", cdr.billsec
                    )
                    await db.execute(text(
                        "UPDATE cdrs SET buycost=:bc, sessionbill=:sb WHERE id=:id"
                    ), {"bc": buycost, "sb": sessionbill, "id": cdr.id})
                    if sessionbill > 0:
                        await db.execute(text(
                            "UPDATE customers SET balance = balance - :bill WHERE id = :cid"
                        ), {"bill": sessionbill, "cid": cdr.customer_id})

                if pending:
                    await db.commit()
                    log.info("Billing: %d CDRs tarifados", len(pending))
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    t1 = asyncio.create_task(_billing_worker())
    t2 = asyncio.create_task(_stale_calls_cleaner())
    yield
    for t in [t1, t2]:
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="la plataforma anterior API",
    version="2.2",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
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
    return {"status": "ok", "service": "kaplabilling", "version": "2.2"}
