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

router = APIRouter()

MODULES = ["show_calls", "show_quality", "show_reports", "show_invoices", "show_trunk_guide"]


class ProfileIn(BaseModel):
    name: str
    description: Optional[str] = None
    show_calls:       bool = True
    show_quality:     bool = True
    show_reports:     bool = True
    show_invoices:    bool = False
    show_trunk_guide: bool = True


@router.get("")
async def list_profiles(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("""
        SELECT p.*,
               COUNT(c.id) AS customers_count
        FROM customer_profiles p
        LEFT JOIN customers c ON c.profile_id = p.id
        GROUP BY p.id
        ORDER BY p.name
    """))
    return r.mappings().all()


@router.post("", status_code=201)
async def create_profile(body: ProfileIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(text("""
        INSERT INTO customer_profiles
            (name, description, show_calls, show_quality, show_reports, show_invoices, show_trunk_guide)
        VALUES
            (:name, :description, :show_calls, :show_quality, :show_reports, :show_invoices, :show_trunk_guide)
    """), body.model_dump())
    await db.commit()
    r = await db.execute(text("SELECT LAST_INSERT_ID() AS id"))
    return {"id": r.scalar()}


@router.get("/{pid}")
async def get_profile(pid: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("SELECT * FROM customer_profiles WHERE id = :id"), {"id": pid})
    p = r.mappings().first()
    if not p:
        raise HTTPException(404, "Perfil no encontrado")
    return p


@router.put("/{pid}")
async def update_profile(pid: int, body: ProfileIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    data = body.model_dump()
    data["id"] = pid
    await db.execute(text("""
        UPDATE customer_profiles SET
            name=:name, description=:description,
            show_calls=:show_calls, show_quality=:show_quality,
            show_reports=:show_reports, show_invoices=:show_invoices,
            show_trunk_guide=:show_trunk_guide
        WHERE id=:id
    """), data)
    await db.commit()
    return {"ok": True}


@router.delete("/{pid}", status_code=204)
async def delete_profile(pid: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(
        text("UPDATE customers SET profile_id = NULL WHERE profile_id = :id"), {"id": pid}
    )
    await db.execute(text("DELETE FROM customer_profiles WHERE id = :id"), {"id": pid})
    await db.commit()
