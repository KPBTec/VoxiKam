# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from auth import require_reseller_permission
from database import get_db
from routers.billing_recalc import RecalcRequest, _start_job, _read_job

from ._shared import _my_cid

router = APIRouter()


# ── Recálculo de tarifas propio ──────────────────────────────────────────────
# Mismo motor que /api/admin/billing-recalc (backend/routers/billing_recalc.py
# — _start_job()/_read_job() reusan la fórmula real de facturación en background,
# no la reimplementan acá). Acotado estructuralmente a los propios sub-clientes
# y carriers del reseller, igual que el resto de este archivo.

async def _my_recalc_scope(db: AsyncSession, my_cid: int):
    subc = await db.execute(text("SELECT id FROM customers WHERE parent_customer_id = :pid"), {"pid": my_cid})
    own_carriers = await db.execute(text("SELECT id FROM carriers WHERE owner_customer_id = :pid"), {"pid": my_cid})
    return (
        {row[0] for row in subc.all()},
        {row[0] for row in own_carriers.all()},
    )


@router.get("/billing-recalc/customers")
async def list_own_recalc_customers(user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    r = await db.execute(text(
        "SELECT id, name FROM customers WHERE parent_customer_id = :pid AND status != 'deleted' ORDER BY name"
    ), {"pid": _my_cid(user)})
    return r.mappings().all()


@router.get("/billing-recalc/carriers")
async def list_own_recalc_carriers(user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    r = await db.execute(text(
        "SELECT id, name FROM carriers WHERE owner_customer_id = :pid ORDER BY name"
    ), {"pid": _my_cid(user)})
    return r.mappings().all()


@router.post("/billing-recalc/preview")
async def preview_own_recalc(body: RecalcRequest, background_tasks: BackgroundTasks,
                              user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    allowed_customers, allowed_carriers = await _my_recalc_scope(db, _my_cid(user))
    return _start_job(background_tasks, "preview", body, None, allowed_customers, allowed_carriers)


@router.post("/billing-recalc/apply")
async def apply_own_recalc(body: RecalcRequest, background_tasks: BackgroundTasks,
                            user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    allowed_customers, allowed_carriers = await _my_recalc_scope(db, _my_cid(user))
    return _start_job(background_tasks, "apply", body, user.get("name") or user.get("email"), allowed_customers, allowed_carriers)


@router.get("/billing-recalc/jobs/{job_id}")
async def get_own_recalc_job(job_id: str, user=Depends(require_reseller_permission("reseller_customers"))):
    job = _read_job(job_id)
    if not job:
        raise HTTPException(404, "Job no encontrado — puede haber expirado")
    return job
