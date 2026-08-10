# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from auth import require_admin
from database import get_db
from audit import diff_and_record

router = APIRouter()

CODE_COLUMNS = ["c_487", "c_486", "c_404", "c_503", "c_other", "short_calls"]
CODE_LABELS = {
    "c_487": "487 — Cancelada (predictivo)",
    "c_486": "486 — Ocupado",
    "c_404": "404 — No encontrado",
    "c_503": "503 — Sin carriers / congestión",
    "c_other": "Otros códigos de error",
    "short_calls": "Contestadas cortas (<5s, posible buzón)",
}


class PolicyIn(BaseModel):
    label: Optional[str] = None
    code_column: Optional[str] = None
    threshold_pct: Optional[float] = None
    min_calls: Optional[int] = None
    active: Optional[bool] = None

    @field_validator("label")
    @classmethod
    def _label_no_control_chars(cls, v: Optional[str]) -> Optional[str]:
        """Mismo criterio que alerts.py::RuleIn._label_no_control_chars —
        se usa en subject=f"... {label} ..." para send_email() sin sanitizar."""
        if v and any(ord(c) < 32 or ord(c) == 127 for c in v):
            raise ValueError("El label no puede contener saltos de línea ni caracteres de control")
        return v


@router.get("/columns")
async def list_columns(_=Depends(require_admin)):
    return [{"value": c, "label": CODE_LABELS[c]} for c in CODE_COLUMNS]


@router.get("")
async def list_policies(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text(
        "SELECT id, label, code_column, threshold_pct, min_calls, active FROM disconnect_policies ORDER BY id"
    ))
    return r.mappings().all()


@router.post("", status_code=201)
async def create_policy(body: PolicyIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    if not body.label or not body.code_column or body.threshold_pct is None:
        raise HTTPException(422, "label, code_column y threshold_pct son obligatorios")
    if body.code_column not in CODE_COLUMNS:
        raise HTTPException(422, f"code_column inválido — debe ser uno de: {', '.join(CODE_COLUMNS)}")
    await db.execute(text("""
        INSERT INTO disconnect_policies (label, code_column, threshold_pct, min_calls, active)
        VALUES (:label, :code_column, :threshold_pct, :min_calls, :active)
    """), {
        "label": body.label, "code_column": body.code_column,
        "threshold_pct": body.threshold_pct, "min_calls": body.min_calls or 20,
        "active": body.active if body.active is not None else True,
    })
    await db.commit()
    r = await db.execute(text("SELECT LAST_INSERT_ID() AS id"))
    return {"id": r.scalar()}


@router.put("/{pid}")
async def update_policy(pid: int, body: PolicyIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    before_row = await db.execute(text(
        "SELECT label, code_column, threshold_pct, min_calls, active FROM disconnect_policies WHERE id=:id"
    ), {"id": pid})
    before = dict(before_row.mappings().first() or {})
    if not before:
        raise HTTPException(404, "Política no encontrada")

    fields, params = [], {"id": pid}
    for field in ("label", "code_column", "threshold_pct", "min_calls", "active"):
        value = getattr(body, field)
        if value is not None:
            if field == "code_column" and value not in CODE_COLUMNS:
                raise HTTPException(422, f"code_column inválido — debe ser uno de: {', '.join(CODE_COLUMNS)}")
            fields.append(f"{field}=:{field}")
            params[field] = value
    if fields:
        await db.execute(text(f"UPDATE disconnect_policies SET {', '.join(fields)} WHERE id=:id"), params)
        after = {**before, **{k: v for k, v in params.items() if k != "id"}}
        await diff_and_record(db, "disconnect_policy", pid, before, after,
                               ["label", "code_column", "threshold_pct", "min_calls", "active"],
                               admin.get("name") or admin.get("email"))
        await db.commit()
    return {"ok": True}


@router.delete("/{pid}", status_code=204)
async def delete_policy(pid: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("DELETE FROM disconnect_policies WHERE id = :id"), {"id": pid})
    if r.rowcount == 0:
        raise HTTPException(404, "Política no encontrada")
    await db.commit()


@router.get("/alerts")
async def list_alerts(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("""
        SELECT a.id, a.ts_hour, a.pct, a.total_calls, a.created_at,
               p.label AS policy_label, c.name AS customer_name
        FROM disconnect_policy_alerts a
        JOIN disconnect_policies p ON p.id = a.policy_id
        JOIN customers c ON c.id = a.customer_id
        ORDER BY a.created_at DESC LIMIT 100
    """))
    return r.mappings().all()
