# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from auth import require_admin
from database import get_db
from alerts import get_alert_notify_email
from audit import diff_and_record

router = APIRouter()


class RuleIn(BaseModel):
    label: Optional[str] = None
    threshold: Optional[float] = None
    active: Optional[bool] = None

    @field_validator("label")
    @classmethod
    def _label_no_control_chars(cls, v: Optional[str]) -> Optional[str]:
        """alerts.py::check_balance_alert arma subject=f"... {label} ..." para
        send_email() sin sanitizar — un salto de línea en label podría intentar
        header injection en el correo de alerta. Severidad baja (admin-only,
        solo afecta su propio correo), mismo criterio defensivo que
        customers.name igual."""
        if v and any(ord(c) < 32 or ord(c) == 127 for c in v):
            raise ValueError("El label no puede contener saltos de línea ni caracteres de control")
        return v


class NotifyEmailIn(BaseModel):
    email: str


@router.get("/rules")
async def list_rules(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text(
        "SELECT id, billing_type, label, threshold, active FROM balance_alert_rules ORDER BY billing_type, threshold DESC"
    ))
    return r.mappings().all()


@router.put("/rules/{rule_id}")
async def update_rule(rule_id: int, body: RuleIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    before_row = await db.execute(text(
        "SELECT threshold, active FROM balance_alert_rules WHERE id=:id"
    ), {"id": rule_id})
    before = dict(before_row.mappings().first() or {})

    fields, params = [], {"id": rule_id}
    if body.label is not None:
        fields.append("label=:label"); params["label"] = body.label
    if body.threshold is not None:
        fields.append("threshold=:threshold"); params["threshold"] = body.threshold
    if body.active is not None:
        fields.append("active=:active"); params["active"] = body.active
    if fields:
        await db.execute(text(f"UPDATE balance_alert_rules SET {', '.join(fields)} WHERE id=:id"), params)
        after = {**before, **{k: v for k, v in {"threshold": body.threshold, "active": body.active}.items() if v is not None}}
        await diff_and_record(db, "alert_rule", rule_id, before, after, ["threshold", "active"],
                               admin.get("name") or admin.get("email"))
        await db.commit()
    return {"ok": True}


@router.get("/affected")
async def affected_customers(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    """
    Clientes que están cruzando ahora mismo alguna regla activa — calculado
    en vivo (no depende de last_alert_rule_id, que solo evita reenviar el
    mismo correo dos veces). Sirve para que el panel siempre muestre el
    estado real, aunque el correo de esa alerta ya se haya mandado antes.
    """
    prepago = await db.execute(text("""
        SELECT c.id, c.name, c.email, c.balance, c.last_topup_amount,
               ROUND(c.balance / NULLIF(c.last_topup_amount, 0) * 100, 1) AS pct_remaining,
               r.id AS rule_id, r.label AS rule_label, r.threshold
        FROM customers c
        JOIN balance_alert_rules r ON r.billing_type = 'prepago' AND r.active = 1
        WHERE c.billing_type = 'prepago'
          AND c.last_topup_amount > 0
          AND (c.balance / c.last_topup_amount * 100) <= r.threshold
        ORDER BY pct_remaining ASC
    """))
    postpago = await db.execute(text("""
        SELECT c.id, c.name, c.email, c.balance,
               r.id AS rule_id, r.label AS rule_label, r.threshold
        FROM customers c
        JOIN balance_alert_rules r ON r.billing_type = 'postpago' AND r.active = 1
        WHERE c.billing_type = 'postpago'
          AND c.balance <= r.threshold
        ORDER BY c.balance ASC
    """))
    return {
        "prepago": prepago.mappings().all(),
        "postpago": postpago.mappings().all(),
    }


@router.get("/notify-email")
async def get_notify_email(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    return {"email": await get_alert_notify_email(db)}


@router.put("/notify-email")
async def set_notify_email(body: NotifyEmailIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(text("""
        INSERT INTO settings (key_name, value, description)
        VALUES ('alert_notify_email', :email, 'Email que recibe las alertas de balance')
        ON DUPLICATE KEY UPDATE value = :email
    """), {"email": body.email})
    await db.commit()
    return {"ok": True}
