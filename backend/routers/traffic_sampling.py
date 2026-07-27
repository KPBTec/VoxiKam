# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Traffic Sampling Rules — en esta plataforma se implementa como la ventana de
retención de sip_traces (cuánto tráfico SIP capturado se conserva antes de
purgarse). El valor vive en settings (MariaDB, igual que siempre) pero la
retención real la aplica el TTL nativo de la tabla ClickHouse
(sip_platform.sip_traces) — este endpoint empuja el cambio a ambos lados para
que el panel siga funcionando igual que antes de la migración a ClickHouse.
"""
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from auth import require_admin
from database import get_db
from clickhouse import get_ch
from audit import diff_and_record

router = APIRouter()
log = logging.getLogger("voxikam.traffic_sampling")

DEFAULT_RETENTION_HOURS = 24


class RetentionIn(BaseModel):
    retention_hours: int


@router.get("/config")
async def get_config(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text(
        "SELECT value FROM settings WHERE key_name = 'sip_traces_retention_hours'"
    ))
    row = r.first()
    return {"retention_hours": int(row[0]) if row and row[0] else DEFAULT_RETENTION_HOURS}


@router.put("/config")
async def set_config(body: RetentionIn, db: AsyncSession = Depends(get_db),
                      ch=Depends(get_ch), admin=Depends(require_admin)):
    if body.retention_hours < 1 or body.retention_hours > 24 * 180:
        return {"ok": False, "error": "Debe estar entre 1 hora y 180 días (6 meses, 4320h)"}

    before_row = await db.execute(text(
        "SELECT value FROM settings WHERE key_name = 'sip_traces_retention_hours'"
    ))
    before_val = before_row.scalar()
    before = {"retention_hours": int(before_val) if before_val else DEFAULT_RETENTION_HOURS}

    await db.execute(text("""
        INSERT INTO settings (key_name, value, description)
        VALUES ('sip_traces_retention_hours', :v, 'Horas que se conservan las trazas SIP antes de purgarse')
        ON DUPLICATE KEY UPDATE value = :v
    """), {"v": str(body.retention_hours)})

    await diff_and_record(db, "traffic_sampling", 1, before, body.model_dump(),
                           ["retention_hours"], admin.get("name") or admin.get("email"))
    await db.commit()

    # El TTL de ClickHouse se ajusta después de confirmar el commit en MariaDB
    # (fuente de verdad del setting) — un fallo acá no debe romper la respuesta:
    # el TTL es un merge en background, no una ruta urgente, y el valor queda
    # igual disponible para reintentar en el próximo cambio desde el panel.
    try:
        await ch.command(
            f"ALTER TABLE sip_platform.sip_traces MODIFY TTL "
            f"captured_at + INTERVAL {body.retention_hours} HOUR"
        )
    except Exception as e:
        log.warning("No se pudo sincronizar TTL a ClickHouse (%dh): %s", body.retention_hours, e)

    return {"ok": True}
