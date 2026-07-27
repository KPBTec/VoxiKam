# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import subprocess, sys
from pathlib import Path

from auth import require_admin
from database import get_db
from audit import diff_and_record, record_event

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
    # NULL/vacío = sin límite (comportamiento de siempre). Si se setea,
    # kamailio.cfg.j2 encola (no rechaza) el excedente hacia este carrier
    # — ver route[CPS_GATE]/route[CPS_DRAIN] y gen_dispatcher.py (cps=).
    cps_limit: Optional[int] = None
    notes: Optional[str] = None

    @field_validator("cps_limit")
    @classmethod
    def _cps_limit_range(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1 <= v <= 65535):
            raise ValueError("cps_limit debe ser un número positivo (o vacío para sin límite)")
        return v


class BuyRateIn(BaseModel):
    prefix_id: int
    buy_rate: float
    connectcharge: float = 0.0
    billingblock: int = 1
    effective_date: Optional[str] = None


class GroupBuyRateIn(BaseModel):
    group_name: str
    buy_rate: float
    connectcharge: float = 0.0
    billingblock: int = 1


@router.get("")
async def list_carriers(include_reseller: bool = False,
                         db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    """
    Por defecto solo carriers de la plataforma (owner_customer_id IS NULL) —
    mismo criterio "el admin ve lo suyo y el reseller ve lo suyo" que ya usan
    prefixes/rate_plans. include_reseller=true es para soporte (ver qué
    troncales propias cargaron los resellers).
    """
    if include_reseller:
        r = await db.execute(text("""
            SELECT ca.*, cu.name AS owner_name,
                   (SELECT COUNT(*) FROM carrier_rates cr WHERE cr.carrier_id = ca.id) AS rate_count
            FROM carriers ca LEFT JOIN customers cu ON ca.owner_customer_id = cu.id
            ORDER BY ca.priority DESC, ca.name
        """))
    else:
        r = await db.execute(text("""
            SELECT ca.*,
                   (SELECT COUNT(*) FROM carrier_rates cr WHERE cr.carrier_id = ca.id) AS rate_count
            FROM carriers ca WHERE ca.owner_customer_id IS NULL ORDER BY ca.priority DESC, ca.name
        """))
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
async def create_carrier(body: CarrierIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    result = await db.execute(text("""
        INSERT INTO carriers (name, host, port, priority, outbound_prefix,
                              remove_prefix, failover_id, status, cps_limit, notes)
        VALUES (:name, :host, :port, :priority, :outbound_prefix,
                :remove_prefix, :failover_id, :status, :cps_limit, :notes)
    """), body.model_dump())
    new_id = result.lastrowid
    await record_event(db, "carrier", new_id, "created", admin.get("name") or admin.get("email"), body.name)
    await db.commit()
    _sync()
    return {"id": new_id}


@router.put("/{cid}")
async def update_carrier(cid: int, body: CarrierIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    before_row = await db.execute(text("SELECT status, host, port, priority FROM carriers WHERE id=:id"), {"id": cid})
    before = dict(before_row.mappings().first() or {})

    data = body.model_dump(); data["id"] = cid
    await db.execute(text("""
        UPDATE carriers SET name=:name, host=:host, port=:port, priority=:priority,
        outbound_prefix=:outbound_prefix, remove_prefix=:remove_prefix,
        failover_id=:failover_id, status=:status, cps_limit=:cps_limit, notes=:notes WHERE id=:id
    """), data)
    await diff_and_record(db, "carrier", cid, before, data, ["status", "host", "port", "priority"],
                           admin.get("name") or admin.get("email"))
    await db.commit()
    _sync()
    return {"ok": True}


@router.delete("/{cid}", status_code=204)
async def delete_carrier(cid: int, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    # carrier_group_members.carrier_id es ON DELETE RESTRICT a propósito
    # (ver schema.sql) — este chequeo explícito es solo para dar un 409 con
    # mensaje claro en vez de que el DELETE de abajo reviente con un
    # IntegrityError crudo.
    in_group = await db.execute(text(
        "SELECT 1 FROM carrier_group_members WHERE carrier_id = :id LIMIT 1"
    ), {"id": cid})
    if in_group.first():
        raise HTTPException(409, "Este carrier es miembro de al menos un Grupo de ruteo — sacalo del grupo antes de borrarlo")
    row = await db.execute(text("SELECT name FROM carriers WHERE id=:id"), {"id": cid})
    old = row.mappings().first()
    await db.execute(text("DELETE FROM carriers WHERE id = :id"), {"id": cid})
    await record_event(db, "carrier", cid, "deleted", admin.get("name") or admin.get("email"), old["name"] if old else "")
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
async def add_buy_rate(cid: int, body: BuyRateIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    data = body.model_dump(); data["carrier_id"] = cid
    await db.execute(text("""
        INSERT INTO carrier_rates (carrier_id, prefix_id, buy_rate, connectcharge, billingblock, effective_date)
        VALUES (:carrier_id, :prefix_id, :buy_rate, :connectcharge, :billingblock, :effective_date)
        ON DUPLICATE KEY UPDATE buy_rate=:buy_rate, connectcharge=:connectcharge, billingblock=:billingblock
    """), data)
    await record_event(db, "carrier", cid, "buy_rate_set", admin.get("name") or admin.get("email"),
                        f"prefix_id={body.prefix_id} → {body.buy_rate}/min")
    await db.commit()
    return {"ok": True}


@router.post("/{cid}/group-rates", status_code=201)
async def add_group_buy_rate(cid: int, body: GroupBuyRateIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    r = await db.execute(text("SELECT id FROM prefixes WHERE group_name = :g"), {"g": body.group_name})
    prefix_ids = [row[0] for row in r.fetchall()]
    for pfx_id in prefix_ids:
        await db.execute(text("""
            INSERT INTO carrier_rates (carrier_id, prefix_id, buy_rate, connectcharge, billingblock)
            VALUES (:cid, :pfx, :rate, :cc, :bb)
            ON DUPLICATE KEY UPDATE buy_rate=:rate, connectcharge=:cc, billingblock=:bb
        """), {"cid": cid, "pfx": pfx_id, "rate": body.buy_rate, "cc": body.connectcharge, "bb": body.billingblock})
    await record_event(db, "carrier", cid, "group_buy_rate_set", admin.get("name") or admin.get("email"),
                        f"grupo {body.group_name} → {body.buy_rate}/min ({len(prefix_ids)} prefijos)")
    await db.commit()
    return {"ok": True, "updated": len(prefix_ids)}


@router.delete("/{cid}/rates/{rate_id}", status_code=204)
async def delete_buy_rate(cid: int, rate_id: int, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    r = await db.execute(text("""
        SELECT p.prefix FROM carrier_rates cr JOIN prefixes p ON cr.prefix_id = p.id WHERE cr.id = :id
    """), {"id": rate_id})
    row = r.first()
    await db.execute(text("DELETE FROM carrier_rates WHERE id=:id AND carrier_id=:cid"), {"id": rate_id, "cid": cid})
    await record_event(db, "carrier", cid, "buy_rate_deleted", admin.get("name") or admin.get("email"),
                        row[0] if row else f"rate_id={rate_id}")
    await db.commit()


def _sync():
    subprocess.Popen([sys.executable, str(SCRIPTS / "gen_dispatcher.py")])
    subprocess.Popen([sys.executable, str(SCRIPTS / "gen_nftables.py")])
