# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
audit.py — Auditoría de cambios de configuración.

No es un log de TODO — es deliberadamente selectivo: cubre los campos que
afectan dinero, servicio o seguridad (estado de cliente, tarifas, carriers,
reglas de firewall, reglas de alerta, usuarios admin). Un `notes` que cambia
no se audita, un `status` que pasa de active→suspended sí.

Uso típico: leer la fila ANTES del UPDATE, aplicar el cambio, y llamar
diff_and_record() con el before/after — solo inserta filas para los campos
que realmente cambiaron.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def record_change(
    db: AsyncSession,
    entity: str,
    entity_id: int,
    field: str,
    old_value,
    new_value,
    changed_by: str,
) -> None:
    if old_value == new_value:
        return
    await db.execute(text("""
        INSERT INTO settings_history (entity, entity_id, field, old_value, new_value, changed_by)
        VALUES (:entity, :id, :field, :old, :new, :by)
    """), {
        "entity": entity, "id": entity_id, "field": field,
        "old": None if old_value is None else str(old_value),
        "new": None if new_value is None else str(new_value),
        "by": changed_by,
    })


async def diff_and_record(
    db: AsyncSession,
    entity: str,
    entity_id: int,
    before: dict,
    after: dict,
    fields: list[str],
    changed_by: str,
) -> None:
    for field in fields:
        if field in before and field in after:
            await record_change(db, entity, entity_id, field, before[field], after[field], changed_by)


async def record_event(
    db: AsyncSession,
    entity: str,
    entity_id: int,
    event: str,
    changed_by: str,
    detail: str = "",
) -> None:
    """Para acciones que no son un diff de campo (crear, borrar, activar/desactivar)."""
    await record_change(db, entity, entity_id, event, "", detail or "—", changed_by)
