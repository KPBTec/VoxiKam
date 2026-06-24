# la plataforma anterior — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2025 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2025 – Todos los derechos reservados.

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import subprocess, sys
from pathlib import Path

from auth import require_admin
from database import get_db

router = APIRouter()
SCRIPTS = Path(__file__).parent.parent.parent / "scripts"


class CarrierIn(BaseModel):
    name: str
    host: str
    port: int = 5060
    priority: int = 10
    outbound_prefix: str = ""
    remove_prefix: str = ""
    failover_id: Optional[int] = None
    status: str = "active"
    notes: Optional[str] = None


class BuyRateIn(BaseModel):
    prefix_id: int
    buy_rate: float
    connect_charge: float = 0.0
    billingblock: int = 60
    effective_date: Optional[str] = None


class GroupBuyRateIn(BaseModel):
    group_name: str
    buy_rate: float
    connect_charge: float = 0.0
    billingblock: int = 60


@router.get("")
async def list_carriers(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("SELECT * FROM carriers ORDER BY priority DESC, name"))
    return r.mappings().all()


@router.get("/{cid}")
async def get_carrier(cid: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("SELECT * FROM carriers WHERE id = :id"), {"id": cid})
    c = r.mappings().first()
    if not c:
        from fastapi import HTTPException
        raise HTTPException(404, "Carrier no encontrado")
    return c


@router.post("", status_code=201)
async def create_carrier(body: CarrierIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(text("""
        INSERT INTO carriers (name, host, port, priority, outbound_prefix,
                              remove_prefix, failover_id, status, notes)
        VALUES (:name, :host, :port, :priority, :outbound_prefix,
                :remove_prefix, :failover_id, :status, :notes)
    """), body.model_dump())
    await db.commit()
    r = await db.execute(text("SELECT LAST_INSERT_ID() AS id"))
    _sync()
    return {"id": r.scalar()}


@router.put("/{cid}")
async def update_carrier(cid: int, body: CarrierIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    data = body.model_dump(); data["id"] = cid
    await db.execute(text("""
        UPDATE carriers SET name=:name, host=:host, port=:port, priority=:priority,
        outbound_prefix=:outbound_prefix, remove_prefix=:remove_prefix,
        failover_id=:failover_id, status=:status, notes=:notes WHERE id=:id
    """), data)
    await db.commit()
    _sync()
    return {"ok": True}


@router.delete("/{cid}", status_code=204)
async def delete_carrier(cid: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(text("DELETE FROM carriers WHERE id = :id"), {"id": cid})
    await db.commit()
    _sync()


# ── Buy rates ─────────────────────────────────────────────────────────────────

@router.get("/{cid}/rates")
async def get_buy_rates(cid: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("""
        SELECT cr.*, p.prefix, p.destination
        FROM carrier_rates cr JOIN prefixes p ON cr.prefix_id = p.id
        WHERE cr.carrier_id = :id ORDER BY p.prefix
    """), {"id": cid})
    return r.mappings().all()


@router.post("/{cid}/rates", status_code=201)
async def add_buy_rate(cid: int, body: BuyRateIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    data = body.model_dump(); data["carrier_id"] = cid
    await db.execute(text("""
        INSERT INTO carrier_rates (carrier_id, prefix_id, buy_rate, connect_charge, billingblock, effective_date)
        VALUES (:carrier_id, :prefix_id, :buy_rate, :connect_charge, :billingblock, :effective_date)
        ON DUPLICATE KEY UPDATE buy_rate=:buy_rate, connect_charge=:connect_charge
    """), data)
    await db.commit()
    return {"ok": True}


@router.post("/{cid}/group-rates", status_code=201)
async def add_group_buy_rate(cid: int, body: GroupBuyRateIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("SELECT id FROM prefixes WHERE group_name = :g"), {"g": body.group_name})
    prefix_ids = [row[0] for row in r.fetchall()]
    for pfx_id in prefix_ids:
        await db.execute(text("""
            INSERT INTO carrier_rates (carrier_id, prefix_id, buy_rate, connect_charge, billingblock)
            VALUES (:cid, :pfx, :rate, :cc, :bb)
            ON DUPLICATE KEY UPDATE buy_rate=:rate, connect_charge=:cc, billingblock=:bb
        """), {"cid": cid, "pfx": pfx_id, "rate": body.buy_rate, "cc": body.connect_charge, "bb": body.billingblock})
    await db.commit()
    return {"ok": True, "updated": len(prefix_ids)}


@router.delete("/{cid}/rates/{rate_id}", status_code=204)
async def delete_buy_rate(cid: int, rate_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(text("DELETE FROM carrier_rates WHERE id=:id AND carrier_id=:cid"), {"id": rate_id, "cid": cid})
    await db.commit()


def _sync():
    subprocess.Popen([sys.executable, str(SCRIPTS / "gen_dispatcher.py")])
    subprocess.Popen([sys.executable, str(SCRIPTS / "gen_nftables.py")])
