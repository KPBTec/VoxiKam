# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# MIT License · https://t.me/KPBTec · By KPBTec

import asyncio
import logging
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
from rating import billable_blocks as _billable_blocks, calc_bill as _calc_bill
from rate_limit import purge_expired as _purge_rate_limit_counters
import cors_state

log = logging.getLogger("billing-worker")

ALLOWED_ORIGINS = cors_state.seed_from_env()

# Auditoría v2.55 (workflow multi-agente): _billable_blocks()/_calc_bill()
# vivían acá duplicados byte a byte contra routers/cdrs.py — extraídos a
# rating.py (única fuente de verdad para ambos caminos de facturación). Se
# re-exportan con estos mismos nombres para no tocar _billing_worker() más
# abajo ni romper tests/test_billable_blocks.py::main_module._billable_blocks
# / tests/test_calc_bill.py::from main import _calc_bill.


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
                    # Re-auditoría v2.56.0 (hallazgo crítico): antes, una sola
                    # tarifa corrupta (ej. billingblock=0, ya bloqueado en el
                    # alta pero posible en datos viejos) hacía que _calc_bill()
                    # lanzara ZeroDivisionError ACÁ, sin ningún try/except
                    # propio — la excepción se propagaba fuera del for, el
                    # commit() de más abajo (que aplica a TODO el batch) nunca
                    # se alcanzaba, y el mismo lote de hasta 100 CDRs (de
                    # cualquier cliente, no solo el de la tarifa rota) quedaba
                    # reintentándose cada 30s para siempre. Aislar el fallo a
                    # SOLO este CDR — el resto del batch sigue facturándose.
                    try:
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
                    except Exception:
                        log.exception("Billing worker: CDR id=%s call_id=%s no pudo tarifarse — "
                                       "sigue con buycost=0/sessionbill=0, revisar la tarifa a mano",
                                       cdr.id, cdr.call_id)

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


async def _cors_origin_syncer():
    """
    Auditoría v2.55: cors_state.ALLOWED_ORIGINS es una lista en memoria POR
    PROCESO. Con uvicorn --workers N, routers/system.py::set_domain() solo
    agrega el origen nuevo al proceso que atendió ESE request — los demás
    N-1 procesos siguen con la lista vieja hasta que reinician, causando
    CORS intermitente según a qué worker el SO enrute cada request del
    navegador. Este task no reemplaza ese mecanismo (que sigue aplicando
    instantáneo en el proceso que recibió el cambio) — solo hace que los
    demás converjan solos en minutos en vez de nunca, releyendo la misma
    fuente de verdad persistente (settings) que ya usa el arranque en
    lifespan(). add_origin() es un simple "si no está, agregalo" — no hace
    nada si este proceso ya está al día.
    """
    while True:
        await asyncio.sleep(5 * 60)
        try:
            async with AsyncSessionLocal() as db:
                domain, web_port = await get_domain(db)
                if domain:
                    cors_state.add_origin(domain, web_port)
        except Exception:
            log.exception("CORS origin syncer error")


async def _rate_limit_purger():
    """
    Re-auditoría v2.56.0: rate_limit_counters (backend/rate_limit.py) es el
    almacén compartido que reemplazó los dicts en memoria de
    middleware/security.py y routers/auth.py — sin esta purga, cada (key,
    ventana) distinta que alguna vez pasó por acá deja una fila para
    siempre. El default de purge_expired() (1h) cubre con margen la ventana
    más larga configurada hoy (300s, límite por cuenta de login).
    """
    while True:
        await asyncio.sleep(15 * 60)
        try:
            async with AsyncSessionLocal() as db:
                deleted = await _purge_rate_limit_counters(db)
                if deleted:
                    log.info("Rate limit purger: %d fila(s) de ventanas vencidas eliminadas", deleted)
        except Exception:
            log.exception("Rate limit purger error")


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
    t4 = asyncio.create_task(_cors_origin_syncer())
    t5 = asyncio.create_task(_rate_limit_purger())
    yield
    for t in [t1, t2, t3, t4, t5]:
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
