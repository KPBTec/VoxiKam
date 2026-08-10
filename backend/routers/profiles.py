# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Perfiles de cliente — grupos de permisos reutilizables (estilo MagnusBilling
ACL). El detalle de QUÉ ve un perfil vive en permission_resources/
profile_permissions (db/schema.sql), no en columnas de esta tabla — ver
backend/auth.py::has_permission()/resolve_permissions() para la resolución.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from audit import record_event
from auth import require_admin
from database import get_db

router = APIRouter()


class ProfileIn(BaseModel):
    name: str
    description: Optional[str] = None
    # {resource_key: can_view} — reemplazo completo en cada save (el frontend
    # manda el árbol entero de checkboxes, no un diff), mismo criterio que
    # customers.py::CustomerIn.permissions.
    permissions: dict[str, bool] = {}


@router.get("/resources")
async def list_resources(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    """Árbol completo de recursos controlables — usado tanto acá (editor de
    perfil) como en customers/[id]/page.tsx (override por cliente sin perfil)."""
    r = await db.execute(text(
        "SELECT resource_key, parent_key, label, sort_order, default_visible "
        "FROM permission_resources ORDER BY sort_order"
    ))
    return r.mappings().all()


@router.get("")
async def list_profiles(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("""
        SELECT p.id, p.name, p.description, p.created_at,
               COUNT(c.id) AS customers_count
        FROM customer_profiles p
        LEFT JOIN customers c ON c.profile_id = p.id
        GROUP BY p.id
        ORDER BY p.name
    """))
    return r.mappings().all()


@router.post("", status_code=201)
async def create_profile(body: ProfileIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    await db.execute(text(
        "INSERT INTO customer_profiles (name, description) VALUES (:name, :description)"
    ), {"name": body.name, "description": body.description})
    r = await db.execute(text("SELECT LAST_INSERT_ID() AS id"))
    new_id = r.scalar()
    for key, val in body.permissions.items():
        await db.execute(text("""
            INSERT INTO profile_permissions (profile_id, resource_key, can_view)
            VALUES (:pid, :key, :val)
        """), {"pid": new_id, "key": key, "val": val})
    await record_event(db, "customer_profile", new_id, "created", admin.get("name") or admin.get("email"), body.name)
    await db.commit()
    return {"id": new_id}


@router.get("/{pid}")
async def get_profile(pid: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("SELECT * FROM customer_profiles WHERE id = :id"), {"id": pid})
    p = r.mappings().first()
    if not p:
        raise HTTPException(404, "Perfil no encontrado")
    perms = await db.execute(text(
        "SELECT resource_key, can_view FROM profile_permissions WHERE profile_id = :pid"
    ), {"pid": pid})
    permissions = {row["resource_key"]: bool(row["can_view"]) for row in perms.mappings().all()}
    return {**dict(p), "permissions": permissions}


@router.put("/{pid}")
async def update_profile(pid: int, body: ProfileIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    r_before = await db.execute(text("SELECT name, description FROM customer_profiles WHERE id = :id"), {"id": pid})
    before = r_before.mappings().first()
    if not before:
        raise HTTPException(404, "Perfil no encontrado")

    await db.execute(text(
        "UPDATE customer_profiles SET name=:name, description=:description WHERE id=:id"
    ), {"name": body.name, "description": body.description, "id": pid})

    await db.execute(text("DELETE FROM profile_permissions WHERE profile_id = :pid"), {"pid": pid})
    for key, val in body.permissions.items():
        await db.execute(text("""
            INSERT INTO profile_permissions (profile_id, resource_key, can_view)
            VALUES (:pid, :key, :val)
        """), {"pid": pid, "key": key, "val": val})

    if before["name"] != body.name or (before["description"] or "") != (body.description or ""):
        await record_event(db, "customer_profile", pid, "updated", admin.get("name") or admin.get("email"),
                            f"{before['name']} → {body.name}" if before["name"] != body.name else body.name)
    await db.commit()
    return {"ok": True}


@router.delete("/{pid}", status_code=204)
async def delete_profile(pid: int, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    r = await db.execute(text("SELECT name FROM customer_profiles WHERE id = :id"), {"id": pid})
    row = r.first()
    if not row:
        raise HTTPException(404, "Perfil no encontrado")
    await db.execute(
        text("UPDATE customers SET profile_id = NULL WHERE profile_id = :id"), {"id": pid}
    )
    await db.execute(text("DELETE FROM customer_profiles WHERE id = :id"), {"id": pid})
    await record_event(db, "customer_profile", pid, "deleted", admin.get("name") or admin.get("email"),
                        row[0] if row else "")
    await db.commit()
