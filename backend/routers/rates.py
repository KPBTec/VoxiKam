# la plataforma anterior — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2025 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2025 – Todos los derechos reservados.

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from auth import require_admin
from database import get_db

router = APIRouter()


class PlanIn(BaseModel):
    name: str
    currency: str = "PEN"
    description: Optional[str] = None
    status: str = "active"


class RateIn(BaseModel):
    prefix_id: int
    rateinitial: float
    connectcharge: float = 0.0
    initblock: int = 60
    billingblock: int = 60
    minimal_time_charge: int = 0
    status: str = "active"


class GroupRateIn(BaseModel):
    group_name: str
    rateinitial: float
    connectcharge: float = 0.0
    billingblock: int = 60


class PrefixIn(BaseModel):
    prefix: str
    destination: str
    group_name: str = ""
    country: Optional[str] = None


@router.get("/plans")
async def list_plans(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("SELECT * FROM rate_plans ORDER BY name"))
    return r.mappings().all()


@router.post("/plans", status_code=201)
async def create_plan(body: PlanIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(text(
        "INSERT INTO rate_plans (name, currency, description, status) VALUES (:name, :currency, :description, :status)"
    ), body.model_dump())
    await db.commit()
    r = await db.execute(text("SELECT LAST_INSERT_ID() AS id"))
    return {"id": r.scalar()}


@router.put("/plans/{pid}")
async def update_plan(pid: int, body: PlanIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(text(
        "UPDATE rate_plans SET name=:name, currency=:currency, description=:description, status=:status WHERE id=:id"
    ), {**body.model_dump(), "id": pid})
    await db.commit()
    return {"ok": True}


@router.delete("/plans/{pid}", status_code=204)
async def delete_plan(pid: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(text("DELETE FROM rate_plans WHERE id = :id"), {"id": pid})
    await db.commit()


@router.get("/plans/{pid}/rates")
async def get_plan_rates(pid: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("""
        SELECT r.*, p.prefix, p.destination, p.group_name, p.country
        FROM rates r JOIN prefixes p ON r.prefix_id = p.id
        WHERE r.rate_plan_id = :pid ORDER BY p.prefix
    """), {"pid": pid})
    return r.mappings().all()


@router.post("/plans/{pid}/rates", status_code=201)
async def add_rate(pid: int, body: RateIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    data = body.model_dump(); data["rate_plan_id"] = pid
    await db.execute(text("""
        INSERT INTO rates (rate_plan_id, prefix_id, rateinitial, connectcharge,
                           initblock, billingblock, minimal_time_charge, status)
        VALUES (:rate_plan_id, :prefix_id, :rateinitial, :connectcharge,
                :initblock, :billingblock, :minimal_time_charge, :status)
        ON DUPLICATE KEY UPDATE rateinitial=:rateinitial, connectcharge=:connectcharge
    """), data)
    await db.commit()
    return {"ok": True}


@router.post("/plans/{pid}/group-rates", status_code=201)
async def add_group_rate(pid: int, body: GroupRateIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(
        text("SELECT id FROM prefixes WHERE group_name = :g"),
        {"g": body.group_name}
    )
    prefix_ids = [row[0] for row in r.fetchall()]
    for pfx_id in prefix_ids:
        await db.execute(text("""
            INSERT INTO rates (rate_plan_id, prefix_id, rateinitial, connectcharge,
                               initblock, billingblock, minimal_time_charge, status)
            VALUES (:pid, :pfx, :rate, :cc, 60, :bb, 0, 'active')
            ON DUPLICATE KEY UPDATE rateinitial=:rate, connectcharge=:cc, billingblock=:bb
        """), {"pid": pid, "pfx": pfx_id, "rate": body.rateinitial, "cc": body.connectcharge, "bb": body.billingblock})
    await db.commit()
    return {"ok": True, "updated": len(prefix_ids)}


@router.delete("/plans/{pid}/rates/{rid}", status_code=204)
async def delete_rate(pid: int, rid: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(text("DELETE FROM rates WHERE id=:id AND rate_plan_id=:pid"), {"id": rid, "pid": pid})
    await db.commit()


@router.get("/groups")
async def list_groups(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("""
        SELECT group_name, COUNT(*) AS prefix_count
        FROM prefixes
        WHERE group_name != ''
        GROUP BY group_name
        ORDER BY group_name
    """))
    return r.mappings().all()


@router.get("/prefixes")
async def list_prefixes(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("SELECT * FROM prefixes ORDER BY prefix"))
    return r.mappings().all()


@router.post("/prefixes", status_code=201)
async def add_prefix(body: PrefixIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(text(
        "INSERT INTO prefixes (prefix, destination, group_name, country) VALUES (:prefix, :destination, :group_name, :country)"
    ), body.model_dump())
    await db.commit()
    return {"ok": True}


@router.delete("/prefixes/{pid}", status_code=204)
async def delete_prefix(pid: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(text("DELETE FROM prefixes WHERE id = :id"), {"id": pid})
    await db.commit()
