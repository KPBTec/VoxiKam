# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from auth import require_admin
from database import get_db
from audit import diff_and_record, record_event

router = APIRouter()


class ProviderIn(BaseModel):
    name: str
    notes: Optional[str] = None


@router.get("")
async def list_providers(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("""
        SELECT pr.*,
               (SELECT COUNT(*) FROM carriers ca WHERE ca.provider_id = pr.id) AS carrier_count
        FROM providers pr ORDER BY pr.name
    """))
    return r.mappings().all()


@router.get("/{pid}")
async def get_provider(pid: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    from fastapi import HTTPException
    r = await db.execute(text("SELECT * FROM providers WHERE id = :id"), {"id": pid})
    p = r.mappings().first()
    if not p:
        raise HTTPException(404, "Proveedor no encontrado")
    return p


@router.post("", status_code=201)
async def create_provider(body: ProviderIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    result = await db.execute(text("INSERT INTO providers (name, notes) VALUES (:name, :notes)"), body.model_dump())
    new_id = result.lastrowid
    await record_event(db, "provider", new_id, "created", admin.get("name") or admin.get("email"), body.name)
    await db.commit()
    return {"id": new_id}


@router.put("/{pid}")
async def update_provider(pid: int, body: ProviderIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    before_row = await db.execute(text("SELECT name FROM providers WHERE id=:id"), {"id": pid})
    before = dict(before_row.mappings().first() or {})
    if not before:
        raise HTTPException(404, "Proveedor no encontrado")

    data = body.model_dump(); data["id"] = pid
    await db.execute(text("UPDATE providers SET name=:name, notes=:notes WHERE id=:id"), data)
    await diff_and_record(db, "provider", pid, before, data, ["name"], admin.get("name") or admin.get("email"))
    await db.commit()
    return {"ok": True}


@router.delete("/{pid}", status_code=204)
async def delete_provider(pid: int, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    # provider_id en carriers es ON DELETE SET NULL (ver schema.sql) — borrar
    # un proveedor no rompe nada, solo desvincula sus carriers (quedan como
    # "sin proveedor", el admin los reasigna cuando quiera).
    row = await db.execute(text("SELECT name FROM providers WHERE id=:id"), {"id": pid})
    old = row.mappings().first()
    if not old:
        raise HTTPException(404, "Proveedor no encontrado")
    await db.execute(text("DELETE FROM providers WHERE id = :id"), {"id": pid})
    await record_event(db, "provider", pid, "deleted", admin.get("name") or admin.get("email"), old["name"] if old else "")
    await db.commit()
