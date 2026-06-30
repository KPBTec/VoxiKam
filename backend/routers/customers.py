# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import subprocess, sys
from pathlib import Path

from auth import require_admin, hash_password
from database import get_db

router = APIRouter()
SCRIPTS = Path(__file__).parent.parent.parent / "scripts"


class CustomerIn(BaseModel):
    name: str
    company: Optional[str] = None
    email: EmailStr
    phone: Optional[str] = None
    rate_plan_id: Optional[int] = None
    profile_id: Optional[int] = None
    calllimit: int = 10
    cpslimit: int = 2
    techprefix: str
    currency: str = "PEN"
    show_calls: bool = True
    show_quality: bool = True
    show_reports: bool = True
    show_invoices: bool = False
    show_trunk_guide: bool = True
    status: str = "active"
    notes: Optional[str] = None


class CustomerIPIn(BaseModel):
    ip: str
    description: Optional[str] = None


class CustomerCarrierIn(BaseModel):
    carrier_id: int
    priority: int = 10


# ── CRUD Clientes ─────────────────────────────────────────────────────────────

@router.get("")
async def list_customers(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("""
        SELECT c.*, rp.name AS rate_plan_name
        FROM customers c
        LEFT JOIN rate_plans rp ON c.rate_plan_id = rp.id
        ORDER BY c.name
    """))
    return r.mappings().all()


@router.post("", status_code=201)
async def create_customer(body: CustomerIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(text("""
        INSERT INTO customers (name, company, email, phone, rate_plan_id, profile_id, calllimit,
                               cpslimit, techprefix, currency,
                               show_calls, show_quality, show_reports,
                               show_invoices, show_trunk_guide, status, notes)
        VALUES (:name, :company, :email, :phone, :rate_plan_id, :profile_id, :calllimit,
                :cpslimit, :techprefix, :currency,
                :show_calls, :show_quality, :show_reports,
                :show_invoices, :show_trunk_guide, :status, :notes)
    """), body.model_dump())
    await db.commit()
    r = await db.execute(text("SELECT LAST_INSERT_ID() AS id"))
    return {"id": r.scalar()}


@router.get("/{cid}")
async def get_customer(cid: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("""
        SELECT c.*, cp.name AS profile_name
        FROM customers c
        LEFT JOIN customer_profiles cp ON c.profile_id = cp.id
        WHERE c.id = :id
    """), {"id": cid})
    c = r.mappings().first()
    if not c:
        raise HTTPException(404, "Cliente no encontrado")
    ips = await db.execute(text("SELECT * FROM customer_ips WHERE customer_id = :id"), {"id": cid})
    cars = await db.execute(text("""
        SELECT ca.id, ca.name, ca.host, cc.priority
        FROM customer_carriers cc JOIN carriers ca ON cc.carrier_id = ca.id
        WHERE cc.customer_id = :id
    """), {"id": cid})
    usr = await db.execute(text(
        "SELECT id, name, email FROM users WHERE customer_id = :id AND role = 'client' LIMIT 1"
    ), {"id": cid})
    return {**dict(c), "ips": ips.mappings().all(), "carriers": cars.mappings().all(),
            "portal_user": usr.mappings().first()}


@router.put("/{cid}")
async def update_customer(cid: int, body: CustomerIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    data = body.model_dump()
    data["id"] = cid
    await db.execute(text("""
        UPDATE customers SET name=:name, company=:company, email=:email, phone=:phone,
        rate_plan_id=:rate_plan_id, calllimit=:calllimit, cpslimit=:cpslimit,
        techprefix=:techprefix, currency=:currency, profile_id=:profile_id,
        show_calls=:show_calls, show_quality=:show_quality, show_reports=:show_reports,
        show_invoices=:show_invoices, show_trunk_guide=:show_trunk_guide,
        status=:status, notes=:notes
        WHERE id=:id
    """), data)
    await db.commit()
    return {"ok": True}


@router.delete("/{cid}", status_code=204)
async def delete_customer(cid: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(text("DELETE FROM customers WHERE id = :id"), {"id": cid})
    await db.commit()


# ── IPs ───────────────────────────────────────────────────────────────────────

@router.post("/{cid}/ips", status_code=201)
async def add_ip(cid: int, body: CustomerIPIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(text(
        "INSERT INTO customer_ips (customer_id, ip, description) VALUES (:cid, :ip, :desc)"
    ), {"cid": cid, "ip": body.ip, "desc": body.description})
    await db.commit()
    _sync_nftables()
    return {"ok": True}


@router.delete("/{cid}/ips/{ip_id}", status_code=204)
async def delete_ip(cid: int, ip_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(text(
        "DELETE FROM customer_ips WHERE id = :id AND customer_id = :cid"
    ), {"id": ip_id, "cid": cid})
    await db.commit()
    _sync_nftables()


# ── Carriers asignados ────────────────────────────────────────────────────────

@router.post("/{cid}/carriers", status_code=201)
async def assign_carrier(cid: int, body: CustomerCarrierIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(text("""
        INSERT INTO customer_carriers (customer_id, carrier_id, priority)
        VALUES (:cid, :carrier_id, :priority)
        ON DUPLICATE KEY UPDATE priority = :priority
    """), {"cid": cid, **body.model_dump()})
    await db.commit()
    _sync_dispatcher()
    return {"ok": True}


@router.delete("/{cid}/carriers/{carrier_id}", status_code=204)
async def remove_carrier(cid: int, carrier_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(text(
        "DELETE FROM customer_carriers WHERE customer_id=:cid AND carrier_id=:cid2"
    ), {"cid": cid, "cid2": carrier_id})
    await db.commit()
    _sync_dispatcher()


# ── Balance ───────────────────────────────────────────────────────────────────

@router.post("/{cid}/balance")
async def adjust_balance(cid: int, amount: float, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(text(
        "UPDATE customers SET balance = balance + :amount WHERE id = :id"
    ), {"amount": amount, "id": cid})
    await db.commit()
    return {"ok": True}


# ── Acceso al portal (usuario cliente) ───────────────────────────────────────

class UserIn(BaseModel):
    name: str
    email: EmailStr
    password: str


class PasswordIn(BaseModel):
    password: str


@router.post("/{cid}/user", status_code=201)
async def create_client_user(cid: int, body: UserIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    existing = await db.execute(
        text("SELECT id FROM users WHERE customer_id = :cid AND role = 'client'"), {"cid": cid}
    )
    if existing.first():
        raise HTTPException(409, "Ya existe un usuario portal para este cliente")
    await db.execute(text("""
        INSERT INTO users (name, email, password_hash, role, customer_id)
        VALUES (:name, :email, :hash, 'client', :cid)
    """), {"name": body.name, "email": body.email, "hash": hash_password(body.password), "cid": cid})
    await db.commit()
    return {"ok": True}


@router.delete("/{cid}/user", status_code=204)
async def delete_client_user(cid: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(
        text("DELETE FROM users WHERE customer_id = :cid AND role = 'client'"), {"cid": cid}
    )
    await db.commit()


@router.put("/{cid}/user/password")
async def reset_client_password(cid: int, body: PasswordIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(
        text("UPDATE users SET password_hash = :hash WHERE customer_id = :cid AND role = 'client'"),
        {"hash": hash_password(body.password), "cid": cid}
    )
    await db.commit()
    return {"ok": True}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sync_nftables():
    subprocess.Popen([sys.executable, str(SCRIPTS / "gen_nftables.py")])


def _sync_dispatcher():
    subprocess.Popen([sys.executable, str(SCRIPTS / "gen_dispatcher.py")])
