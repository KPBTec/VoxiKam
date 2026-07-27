# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from auth import require_admin
from database import get_db

router = APIRouter()


@router.get("")
async def list_audit(
    entity: Optional[str] = Query(None, description="customer, carrier, firewall_rule, alert_rule, admin_user"),
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    cond = "WHERE entity = :entity" if entity else ""
    params = {"lim": limit}
    if entity:
        params["entity"] = entity
    r = await db.execute(text(f"""
        SELECT id, entity, entity_id, field, old_value, new_value, changed_by, changed_at
        FROM settings_history
        {cond}
        ORDER BY id DESC
        LIMIT :lim
    """), params)
    return r.mappings().all()
