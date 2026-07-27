# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Recálculo de tarifas — recalcula buycost/sessionbill/reseller_cost de CDRs ya
facturados contra las tarifas ACTUALES (rates/carrier_rates), scoped por
cliente o por carrier y por rango de fechas. Caso real: un cliente negocia un
precio nuevo a mitad de mes que debe aplicar retroactivamente desde el inicio
del ciclo, o un carrier cambia su tarifa de compra y hay que corregir el
margen de llamadas ya facturadas.

REESCRITO — antes escaneaba con una query por CDR (_calc_bill() con 2-3
queries async cada una) y tenía un tope duro de 50.000 CDRs por corrida
porque un rango más grande directamente colgaba el request (encontrado en
producción real: un rango de 6 días con más de 1M de CDRs ni siquiera podía
previsualizarse). Ahora usa el mismo enfoque que scripts/recalc_billing_blocks.py
(el precedente de este mecanismo): tarifas/prefijos/clientes se cargan en
memoria UNA sola vez, el longest-prefix-match se hace en Python (no contra la
DB por fila), y los CDRs se leen/aplican en lotes con paginación por id — con
millones de CDRs esto tarda minutos, no horas. Misma fórmula exacta que
backend/main.py::_calc_bill() (ver _recalc_one() abajo), verificada contra
datos reales antes de reemplazar el camino viejo.

Corre en background (FastAPI BackgroundTasks + archivo de estado en
/var/lib/voxikam/recalc_jobs/<job_id>.json, sondeado por el frontend) — un
rango de millones de CDRs ya no puede completarse en la ventana de un solo
request HTTP (nginx corta a los 60s), así que preview/apply devuelven un
job_id de inmediato y el resultado se consulta aparte.

Seguridad:
- Reusado tanto por endpoints admin (acá) como reseller (reseller.py importa
  _start_recalc_job()/_read_job() y pasa allowed_customer_ids/allowed_carrier_ids
  para acotarlo a sus propios sub-clientes/carriers — mismo criterio de scope
  estructural que el resto de reseller.py).
- Bloquea de forma DURA si el rango pisa una factura ya `sent`/`paid` de algún
  cliente afectado — no se puede aplicar hasta resolver eso primero (cancelar/
  regenerar la factura). Una factura `draft` no bloquea, pero conviene
  regenerarla después porque va a quedar desactualizada.
- El job_id es un UUID4 (122 bits al azar) — no hay forma práctica de
  adivinarlo; es la misma superficie de protección que cualquier ID de
  recurso no listado (ej. un link de descarga firmado).
"""
import json
import math
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Literal, Optional

from auth import require_admin
from database import get_db, AsyncSessionLocal
from audit import record_event

router = APIRouter()
SCRIPTS = Path(__file__).parent.parent.parent / "scripts"
JOBS_DIR = Path("/var/lib/voxikam/recalc_jobs")
BATCH_SIZE = 5000


class RecalcRequest(BaseModel):
    scope: Literal["customer", "carrier"]
    target_id: int
    date_from: str  # YYYY-MM-DD inclusive
    date_to: str     # YYYY-MM-DD exclusivo

    @field_validator("date_to")
    @classmethod
    def _range_valid(cls, v, info):
        date_from = info.data.get("date_from")
        if date_from and v <= date_from:
            raise ValueError("date_to debe ser posterior a date_from")
        return v


# ── Motor en memoria — misma fórmula exacta que main.py::_calc_bill(),
# adaptada de scripts/recalc_billing_blocks.py (ya probado en producción) ──

def _billable_blocks(seconds: int, initblock: int, billingblock: int) -> int:
    if seconds <= initblock:
        return initblock
    return initblock + math.ceil((seconds - initblock) / billingblock) * billingblock


def _match(dst: str, entries: list):
    """entries ya viene ordenado por longitud de prefijo DESCENDENTE — el
    primer match en un recorrido lineal ya es el longest-prefix-match."""
    for entry in entries:
        if dst.startswith(entry[0]):
            return entry
    return None


def _recalc_one(dst, billsec, rate_plan_id, parent_rate_plan_id, carrier_id,
                 rates_by_plan: dict, carrier_rates: dict):
    buycost, sessionbill, reseller_cost = 0.0, 0.0, None
    matched_prefix = None

    if carrier_id and billsec > 0:
        m = _match(dst, carrier_rates.get(carrier_id, []))
        if m:
            _, buy_rate, cr_bb, cr_cc = m
            blocks = _billable_blocks(billsec, 0, cr_bb)
            buycost = round(blocks / 60 * buy_rate + cr_cc, 6)

    if rate_plan_id and billsec > 0:
        m = _match(dst, rates_by_plan.get(rate_plan_id, []))
        if m:
            prefix, rateinitial, initblock, billingblock, connectcharge, min_charge = m
            billable = max(billsec, min_charge)
            blocks = _billable_blocks(billable, initblock, billingblock)
            sessionbill = round(blocks / 60 * rateinitial + connectcharge, 6)
            matched_prefix = prefix

        if parent_rate_plan_id and billsec > 0:
            mr = _match(dst, rates_by_plan.get(parent_rate_plan_id, []))
            if mr:
                _, rateinitial_r, initblock_r, billingblock_r, connectcharge_r, min_charge_r = mr
                billable_r = max(billsec, min_charge_r)
                blocks_r = _billable_blocks(billable_r, initblock_r, billingblock_r)
                reseller_cost = round(blocks_r / 60 * rateinitial_r + connectcharge_r, 6)

    return buycost, sessionbill, reseller_cost, matched_prefix


async def _load_rates_by_plan(db: AsyncSession) -> dict:
    r = await db.execute(text("""
        SELECT r.rate_plan_id, p.prefix, r.rateinitial, r.initblock, r.billingblock,
               r.connectcharge, r.minimal_time_charge
        FROM rates r JOIN prefixes p ON r.prefix_id = p.id
        WHERE r.status = 'active'
    """))
    by_plan: dict = {}
    for row in r.mappings().all():
        by_plan.setdefault(row["rate_plan_id"], []).append((
            row["prefix"], float(row["rateinitial"]), int(row["initblock"]),
            int(row["billingblock"]), float(row["connectcharge"]), int(row["minimal_time_charge"] or 0),
        ))
    for plan_id in by_plan:
        by_plan[plan_id].sort(key=lambda t: len(t[0]), reverse=True)
    return by_plan


async def _load_carrier_rates(db: AsyncSession) -> dict:
    r = await db.execute(text("""
        SELECT cr.carrier_id, p.prefix, cr.buy_rate, cr.billingblock, cr.connectcharge
        FROM carrier_rates cr JOIN prefixes p ON cr.prefix_id = p.id
    """))
    by_carrier: dict = {}
    for row in r.mappings().all():
        by_carrier.setdefault(row["carrier_id"], []).append((
            row["prefix"], float(row["buy_rate"]), int(row["billingblock"]), float(row["connectcharge"]),
        ))
    for carrier_id in by_carrier:
        by_carrier[carrier_id].sort(key=lambda t: len(t[0]), reverse=True)
    return by_carrier


async def _load_customers(db: AsyncSession) -> dict:
    r = await db.execute(text("SELECT id, rate_plan_id, parent_customer_id FROM customers"))
    return {row["id"]: dict(row) for row in r.mappings().all()}


# ── Estado del job (background) ──────────────────────────────────────────

def _job_path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.json"


def _write_job(job_id: str, data: dict) -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    _job_path(job_id).write_text(json.dumps(data, default=str))


def _read_job(job_id: str) -> Optional[dict]:
    try:
        return json.loads(_job_path(job_id).read_text())
    except Exception:
        return None


async def _blocked_invoices(db: AsyncSession, customer_ids: list, date_from: str, date_to: str):
    if not customer_ids:
        return []
    q = text("""
        SELECT i.id, i.customer_id, cu.name AS customer_name, i.period_start, i.period_end, i.status
        FROM invoices i JOIN customers cu ON cu.id = i.customer_id
        WHERE i.customer_id IN :cids AND i.status IN ('sent', 'paid')
          AND i.period_start < :date_to AND i.period_end >= :date_from
        ORDER BY i.period_start
    """).bindparams(bindparam("cids", expanding=True))
    rows = await db.execute(q, {"cids": tuple(customer_ids), "date_from": date_from, "date_to": date_to})
    return [dict(row) for row in rows.mappings().all()]


async def _customer_names(db: AsyncSession, ids: list) -> dict:
    if not ids:
        return {}
    q = text("SELECT id, name FROM customers WHERE id IN :ids").bindparams(bindparam("ids", expanding=True))
    rows = await db.execute(q, {"ids": tuple(ids)})
    return {row["id"]: row["name"] for row in rows.mappings().all()}


def _summary_payload(per_customer: dict, names: dict, total_scanned: int, blocked: list) -> dict:
    customers_out = [{
        "customer_id": cid, "customer_name": names.get(cid, f"#{cid}"),
        "n_cdrs": d["n"],
        "old_sessionbill": round(d["old_sessionbill"], 4), "new_sessionbill": round(d["new_sessionbill"], 4),
        "delta_sessionbill": round(d["new_sessionbill"] - d["old_sessionbill"], 4),
        "old_buycost": round(d["old_buycost"], 4), "new_buycost": round(d["new_buycost"], 4),
        "delta_buycost": round(d["new_buycost"] - d["old_buycost"], 4),
    } for cid, d in per_customer.items()]
    return {
        "total_scanned": total_scanned,
        "affected_cdrs": sum(d["n"] for d in per_customer.values()),
        "customers": customers_out,
        "blocked_invoices": blocked,
        "can_apply": len(blocked) == 0 and len(customers_out) > 0,
    }


async def _run_job(job_id: str, mode: str, body: RecalcRequest, applied_by: Optional[str],
                    allowed_customer_ids=None, allowed_carrier_ids=None) -> None:
    """Corre en background (BackgroundTasks) — sesión de DB propia, no la del
    request original (que ya cerró para cuando esto arranca)."""
    _write_job(job_id, {"status": "running", "mode": mode,
                         "started_at": datetime.now(timezone.utc).isoformat(),
                         "progress": {"scanned": 0, "total": None}})
    try:
        async with AsyncSessionLocal() as db:
            if body.scope == "customer":
                if allowed_customer_ids is not None and body.target_id not in allowed_customer_ids:
                    _write_job(job_id, {"status": "error", "mode": mode, "error": "Cliente no encontrado"})
                    return
            else:
                if allowed_carrier_ids is not None and body.target_id not in allowed_carrier_ids:
                    _write_job(job_id, {"status": "error", "mode": mode, "error": "Carrier no encontrado"})
                    return

            if allowed_customer_ids is not None and not allowed_customer_ids:
                # Reseller sin sub-clientes — estructuralmente nada que escanear.
                summary = _summary_payload({}, {}, 0, [])
                _write_job(job_id, {"status": "done", "mode": mode, "result": summary})
                return

            rates_by_plan = await _load_rates_by_plan(db)
            carrier_rates = await _load_carrier_rates(db)
            customers = await _load_customers(db)
            parent_plan = {
                cid: customers[c["parent_customer_id"]]["rate_plan_id"]
                for cid, c in customers.items()
                if c["parent_customer_id"] and c["parent_customer_id"] in customers
            }

            where = ["disposition = 'ANSWERED'", "billsec > 0",
                     "start_ts >= :date_from", "start_ts < :date_to",
                     "customer_id = :target_id" if body.scope == "customer" else "carrier_id = :target_id"]
            params: dict = {"date_from": body.date_from, "date_to": body.date_to, "target_id": body.target_id}
            if allowed_customer_ids is not None:
                where.append("customer_id IN :allowed_cids")
                params["allowed_cids"] = tuple(allowed_customer_ids)
            where_sql = " AND ".join(where)

            cnt_q = text(f"SELECT COUNT(*) FROM cdrs WHERE {where_sql}")
            if allowed_customer_ids is not None:
                cnt_q = cnt_q.bindparams(bindparam("allowed_cids", expanding=True))
            total = (await db.execute(cnt_q, params)).scalar()
            _write_job(job_id, {"status": "running", "mode": mode, "progress": {"scanned": 0, "total": total}})

            to_update: list = []
            per_customer: dict = {}
            last_id = 0
            scanned = 0
            while True:
                q = text(f"""
                    SELECT id, customer_id, carrier_id, dst_number, billsec,
                           buycost, sessionbill, reseller_cost, start_ts
                    FROM cdrs WHERE {where_sql} AND id > :last_id
                    ORDER BY id LIMIT :batch_size
                """)
                if allowed_customer_ids is not None:
                    q = q.bindparams(bindparam("allowed_cids", expanding=True))
                batch_params = dict(params, last_id=last_id, batch_size=BATCH_SIZE)
                rows = (await db.execute(q, batch_params)).mappings().all()
                if not rows:
                    break

                for row in rows:
                    cust = customers.get(row["customer_id"], {})
                    rate_plan_id = cust.get("rate_plan_id")
                    parent_rp = parent_plan.get(row["customer_id"])
                    new_bc, new_sb, new_rc, _ = _recalc_one(
                        row["dst_number"] or "", row["billsec"], rate_plan_id, parent_rp,
                        row["carrier_id"], rates_by_plan, carrier_rates,
                    )
                    old_bc, old_sb = float(row["buycost"]), float(row["sessionbill"])
                    if abs(new_bc - old_bc) > 1e-6 or abs(new_sb - old_sb) > 1e-6:
                        to_update.append({
                            "id": row["id"], "start_ts": row["start_ts"],
                            "buycost": new_bc, "sessionbill": new_sb, "reseller_cost": new_rc,
                            "customer_id": row["customer_id"],
                        })
                        d = per_customer.setdefault(row["customer_id"], {
                            "n": 0, "old_sessionbill": 0.0, "new_sessionbill": 0.0,
                            "old_buycost": 0.0, "new_buycost": 0.0,
                        })
                        d["n"] += 1
                        d["old_sessionbill"] += old_sb; d["new_sessionbill"] += new_sb
                        d["old_buycost"] += old_bc; d["new_buycost"] += new_bc

                last_id = rows[-1]["id"]
                scanned += len(rows)
                _write_job(job_id, {"status": "running", "mode": mode, "progress": {"scanned": scanned, "total": total}})

            names = await _customer_names(db, list(per_customer.keys()))
            blocked = await _blocked_invoices(db, list(per_customer.keys()), body.date_from, body.date_to)
            summary = _summary_payload(per_customer, names, scanned, blocked)

            if mode == "preview" or not to_update:
                if mode == "apply" and not to_update:
                    summary = {"applied": False, "message": "No hay diferencias para aplicar en ese rango.",
                               **_summary_payload({}, {}, scanned, [])}
                _write_job(job_id, {"status": "done", "mode": mode, "result": summary})
                return

            if blocked:
                names_blocked = ", ".join(f"#{b['id']} ({b['customer_name']})" for b in blocked[:5])
                _write_job(job_id, {"status": "error", "mode": mode,
                                     "error": f"El rango pisa facturas ya emitidas/pagadas ({names_blocked}) — "
                                              f"resolvelas antes de recalcular. Volvé a generar la vista previa."})
                return

            # ── Aplicar en lotes — executemany real (SQLAlchemy lo hace solo
            # al pasar una lista de dicts a execute()), commit por lote para
            # no dejar millones de filas bloqueadas en una sola transacción.
            affected_dates = set()
            for i in range(0, len(to_update), BATCH_SIZE):
                chunk = to_update[i:i + BATCH_SIZE]
                await db.execute(text(
                    "UPDATE cdrs SET buycost=:buycost, sessionbill=:sessionbill, reseller_cost=:reseller_cost "
                    "WHERE id=:id AND start_ts=:start_ts"
                ), chunk)
                for row in chunk:
                    affected_dates.add(row["start_ts"].date())
                await db.commit()
                _write_job(job_id, {"status": "running", "mode": mode,
                                     "progress": {"applying": i + len(chunk), "total_to_apply": len(to_update)}})

            for cid, d in per_customer.items():
                delta_sb = round(d["new_sessionbill"] - d["old_sessionbill"], 6)
                if abs(delta_sb) < 1e-6:
                    continue
                # Se cobró de más antes (delta negativo) → se le devuelve (crédito, +balance).
                # Se cobró de menos (delta positivo) → se le descuenta.
                credit = round(-delta_sb, 6)
                await db.execute(text("UPDATE customers SET balance = balance + :amount WHERE id = :id"),
                                  {"amount": credit, "id": cid})
                bal_row = await db.execute(text("SELECT balance FROM customers WHERE id = :id"), {"id": cid})
                new_balance = bal_row.scalar()
                await db.execute(text("""
                    INSERT INTO balance_transactions (customer_id, type, amount, balance_after, reference, created_by)
                    VALUES (:cid, 'recalc', :amount, :bal, :ref, :by)
                """), {"cid": cid, "amount": credit, "bal": new_balance,
                        "ref": f"Recálculo de tarifas ({body.date_from} a {body.date_to}, {d['n']} CDRs)",
                        "by": applied_by})

            await record_event(db, "billing_recalc", body.target_id, "applied", applied_by or "sistema",
                                f"scope={body.scope} {body.date_from}..{body.date_to} — "
                                f"{len(to_update)} CDRs, {len(per_customer)} cliente(s)")
            await db.commit()

            # Refresca cdr_summary_day/month del rango afectado — mismo
            # motivo que la versión anterior (ver historial en git blame):
            # sin esto los reportes siguen leyendo el número viejo. El commit
            # de arriba YA pasó — CDRs y balance quedaron aplicados pase lo
            # que pase acá abajo, un fallo solo deja el reporte desactualizado.
            summary_warning = None
            for d in sorted(affected_dates):
                try:
                    subprocess.run([sys.executable, str(SCRIPTS / "cron_summary.py"), d.isoformat()],
                                    check=False, timeout=120)
                except Exception:
                    summary_warning = ("El recálculo se aplicó correctamente, pero no se pudo refrescar "
                                        "el reporte de resumen (cdr_summary_day/month) para algunas fechas "
                                        "— los totales de reportes podrían verse desactualizados hasta el "
                                        "próximo cron.")

            result = {"applied": True, **summary}
            if summary_warning:
                result["warning"] = summary_warning
            _write_job(job_id, {"status": "done", "mode": mode, "result": result})
    except Exception as e:
        _write_job(job_id, {"status": "error", "mode": mode, "error": f"Error interno: {e}"})


def _start_job(background_tasks: BackgroundTasks, mode: str, body: RecalcRequest, applied_by: Optional[str],
               allowed_customer_ids=None, allowed_carrier_ids=None) -> dict:
    job_id = str(uuid.uuid4())
    background_tasks.add_task(_run_job, job_id, mode, body, applied_by, allowed_customer_ids, allowed_carrier_ids)
    return {"job_id": job_id}


@router.get("/customers")
async def list_recalc_customers(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("SELECT id, name FROM customers WHERE status != 'deleted' ORDER BY name"))
    return r.mappings().all()


@router.get("/carriers")
async def list_recalc_carriers(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("SELECT id, name FROM carriers WHERE owner_customer_id IS NULL ORDER BY name"))
    return r.mappings().all()


@router.post("/preview")
async def preview(body: RecalcRequest, background_tasks: BackgroundTasks, _=Depends(require_admin)):
    return _start_job(background_tasks, "preview", body, None)


@router.post("/apply")
async def apply_recalc(body: RecalcRequest, background_tasks: BackgroundTasks, admin=Depends(require_admin)):
    return _start_job(background_tasks, "apply", body, admin.get("name") or admin.get("email"))


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, _=Depends(require_admin)):
    job = _read_job(job_id)
    if not job:
        raise HTTPException(404, "Job no encontrado — puede haber expirado")
    return job
