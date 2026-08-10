# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
CRUD de usuarios admin. La tabla `users` ya soportaba múltiples admins
(role ENUM incluye 'admin' desde siempre) — lo que faltaba era esta pantalla.
Antes, el único admin se creaba una vez en deploy.sh y no había forma de
agregar, desactivar o ver quién más tiene acceso.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from auth import require_admin, hash_password
from database import get_db
from audit import record_event

router = APIRouter()


class AdminUserIn(BaseModel):
    name: str
    email: EmailStr
    password: str


class PasswordIn(BaseModel):
    password: str


class ActiveIn(BaseModel):
    is_active: bool


async def _count_active_admins(db: AsyncSession) -> int:
    r = await db.execute(text(
        "SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1"
    ))
    return r.scalar() or 0


async def _is_superadmin(db: AsyncSession, uid: int) -> bool:
    r = await db.execute(text("SELECT is_superadmin FROM users WHERE id = :id"), {"id": uid})
    row = r.first()
    return bool(row and row[0])


@router.get("")
async def list_admins(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("""
        SELECT id, name, email, is_active, is_superadmin, created_at
        FROM users WHERE role = 'admin' ORDER BY id
    """))
    return r.mappings().all()


@router.post("", status_code=201)
async def create_admin(body: AdminUserIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    existing = await db.execute(text("SELECT id FROM users WHERE email = :email"), {"email": body.email})
    if existing.first():
        raise HTTPException(409, "Ya existe un usuario con ese email")
    if len(body.password) < 8:
        raise HTTPException(400, "La contraseña debe tener al menos 8 caracteres")
    result = await db.execute(text("""
        INSERT INTO users (name, email, password_hash, role, customer_id, is_active)
        VALUES (:name, :email, :hash, 'admin', NULL, 1)
    """), {"name": body.name, "email": body.email, "hash": hash_password(body.password)})
    by = admin.get("name") or admin.get("email")
    await record_event(db, "admin_user", result.lastrowid, "created", by, f"{body.name} <{body.email}>")
    await db.commit()
    return {"ok": True}


@router.put("/{uid}/active")
async def set_admin_active(uid: int, body: ActiveIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    existing = await db.execute(text("SELECT 1 FROM users WHERE id = :id AND role = 'admin'"), {"id": uid})
    if not existing.first():
        raise HTTPException(404, "Administrador no encontrado")
    if uid == admin["id"] and not body.is_active:
        raise HTTPException(400, "No podés desactivar tu propia cuenta")
    if not body.is_active and await _is_superadmin(db, uid):
        raise HTTPException(400, "El super admin no puede ser desactivado")
    if not body.is_active and await _count_active_admins(db) <= 1:
        raise HTTPException(400, "No se puede desactivar — es el único admin activo que queda")
    await db.execute(text(
        "UPDATE users SET is_active = :a WHERE id = :id AND role = 'admin'"
    ), {"a": body.is_active, "id": uid})
    by = admin.get("name") or admin.get("email")
    await record_event(db, "admin_user", uid, "activated" if body.is_active else "deactivated", by)
    await db.commit()
    return {"ok": True}


@router.put("/{uid}/password")
async def reset_admin_password(uid: int, body: PasswordIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    if len(body.password) < 8:
        raise HTTPException(400, "La contraseña debe tener al menos 8 caracteres")
    existing = await db.execute(text("SELECT 1 FROM users WHERE id = :id AND role = 'admin'"), {"id": uid})
    if not existing.first():
        raise HTTPException(404, "Administrador no encontrado")
    if uid != admin["id"] and await _is_superadmin(db, uid):
        raise HTTPException(400, "Solo el super admin puede cambiar su propia contraseña")
    await db.execute(text(
        "UPDATE users SET password_hash = :hash WHERE id = :id AND role = 'admin'"
    ), {"hash": hash_password(body.password), "id": uid})
    by = admin.get("name") or admin.get("email")
    await record_event(db, "admin_user", uid, "password_reset", by)
    await db.commit()
    return {"ok": True}
