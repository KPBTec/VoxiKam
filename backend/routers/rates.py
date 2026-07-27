# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

import csv
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from audit import diff_and_record, record_event
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
    initblock: int = 1
    billingblock: int = 1
    minimal_time_charge: int = 0
    status: str = "active"


class GroupRateIn(BaseModel):
    group_name: str
    rateinitial: float
    connectcharge: float = 0.0
    initblock: int = 1
    billingblock: int = 1


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
async def create_plan(body: PlanIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    # rate_plans ahora permite el mismo nombre entre planes de distintos
    # resellers (UNIQUE compuesto con owner_customer_id) — pero MariaDB trata
    # cada NULL como distinto en un índice único, así que "sin nombres
    # repetidos ENTRE planes de la plataforma" (owner_customer_id IS NULL)
    # no lo garantiza el índice solo, hay que validarlo acá.
    dup = await db.execute(text(
        "SELECT 1 FROM rate_plans WHERE owner_customer_id IS NULL AND name = :name"
    ), {"name": body.name})
    if dup.first():
        raise HTTPException(409, "Ya existe un plan de la plataforma con ese nombre")

    await db.execute(text(
        "INSERT INTO rate_plans (name, currency, description, status) VALUES (:name, :currency, :description, :status)"
    ), body.model_dump())
    await db.commit()
    r = await db.execute(text("SELECT LAST_INSERT_ID() AS id"))
    new_id = r.scalar()
    await record_event(db, "rate_plan", new_id, "created", admin.get("name") or admin.get("email"), body.name)
    await db.commit()
    return {"id": new_id}


@router.put("/plans/{pid}")
async def update_plan(pid: int, body: PlanIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    r = await db.execute(text("SELECT * FROM rate_plans WHERE id = :id"), {"id": pid})
    before = r.mappings().first()
    await db.execute(text(
        "UPDATE rate_plans SET name=:name, currency=:currency, description=:description, status=:status WHERE id=:id"
    ), {**body.model_dump(), "id": pid})
    if before:
        await diff_and_record(db, "rate_plan", pid, dict(before), body.model_dump(),
                               ["name", "currency", "status"], admin.get("name") or admin.get("email"))
    await db.commit()
    return {"ok": True}


@router.delete("/plans/{pid}", status_code=204)
async def delete_plan(pid: int, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    r = await db.execute(text("SELECT name FROM rate_plans WHERE id = :id"), {"id": pid})
    row = r.first()
    await db.execute(text("DELETE FROM rate_plans WHERE id = :id"), {"id": pid})
    await record_event(db, "rate_plan", pid, "deleted", admin.get("name") or admin.get("email"), row[0] if row else "")
    await db.commit()


@router.get("/plans/{pid}/rates")
async def get_plan_rates(pid: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("""
        SELECT r.*, p.prefix, p.destination, p.group_name, p.country
        FROM rates r JOIN prefixes p ON r.prefix_id = p.id
        WHERE r.rate_plan_id = :pid ORDER BY p.prefix
    """), {"pid": pid})
    return r.mappings().all()


@router.get("/plans/{pid}/rates/export-csv")
async def export_plan_rates_csv(pid: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    """
    Export de las tarifas EN VIVO del plan — de solo lectura. Para editarlas en bloque,
    el flujo recomendado es: exportar acá → editar el CSV → importarlo en un draft nuevo
    en Pricelists (revisa el diff antes de publicar), no reimportar directo a `rates`.
    """
    r = await db.execute(text("""
        SELECT p.prefix, r.rateinitial, r.connectcharge, r.billingblock, r.minimal_time_charge
        FROM rates r JOIN prefixes p ON r.prefix_id = p.id
        WHERE r.rate_plan_id = :pid ORDER BY p.prefix
    """), {"pid": pid})
    cols = ["prefix", "rateinitial", "connectcharge", "billingblock", "minimal_time_charge"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=cols)
    writer.writeheader()
    for row in r.mappings().all():
        writer.writerow({k: row[k] for k in cols})
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="rates_plan_{pid}.csv"'},
    )


@router.post("/plans/{pid}/rates", status_code=201)
async def add_rate(pid: int, body: RateIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    data = body.model_dump(); data["rate_plan_id"] = pid
    await db.execute(text("""
        INSERT INTO rates (rate_plan_id, prefix_id, rateinitial, connectcharge,
                           initblock, billingblock, minimal_time_charge, status)
        VALUES (:rate_plan_id, :prefix_id, :rateinitial, :connectcharge,
                :initblock, :billingblock, :minimal_time_charge, :status)
        ON DUPLICATE KEY UPDATE rateinitial=:rateinitial, connectcharge=:connectcharge,
            initblock=:initblock, billingblock=:billingblock
    """), data)
    await record_event(db, "rate_plan", pid, "rate_set", admin.get("name") or admin.get("email"),
                        f"prefix_id={body.prefix_id} → {body.rateinitial}/min")
    await db.commit()
    return {"ok": True}


@router.post("/plans/{pid}/group-rates", status_code=201)
async def add_group_rate(pid: int, body: GroupRateIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    r = await db.execute(
        text("SELECT id FROM prefixes WHERE group_name = :g"),
        {"g": body.group_name}
    )
    prefix_ids = [row[0] for row in r.fetchall()]
    for pfx_id in prefix_ids:
        await db.execute(text("""
            INSERT INTO rates (rate_plan_id, prefix_id, rateinitial, connectcharge,
                               initblock, billingblock, minimal_time_charge, status)
            VALUES (:pid, :pfx, :rate, :cc, :ib, :bb, 0, 'active')
            ON DUPLICATE KEY UPDATE rateinitial=:rate, connectcharge=:cc,
                initblock=:ib, billingblock=:bb
        """), {"pid": pid, "pfx": pfx_id, "rate": body.rateinitial, "cc": body.connectcharge,
               "ib": body.initblock, "bb": body.billingblock})
    await record_event(db, "rate_plan", pid, "group_rate_set", admin.get("name") or admin.get("email"),
                        f"grupo {body.group_name} → {body.rateinitial}/min ({len(prefix_ids)} prefijos)")
    await db.commit()
    return {"ok": True, "updated": len(prefix_ids)}


@router.delete("/plans/{pid}/rates/{rid}", status_code=204)
async def delete_rate(pid: int, rid: int, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    r = await db.execute(text("""
        SELECT p.prefix FROM rates r JOIN prefixes p ON r.prefix_id = p.id WHERE r.id = :id
    """), {"id": rid})
    row = r.first()
    await db.execute(text("DELETE FROM rates WHERE id=:id AND rate_plan_id=:pid"), {"id": rid, "pid": pid})
    await record_event(db, "rate_plan", pid, "rate_deleted", admin.get("name") or admin.get("email"),
                        row[0] if row else f"rate_id={rid}")
    await db.commit()


@router.get("/groups")
async def list_groups(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("""
        SELECT group_name, COUNT(*) AS prefix_count
        FROM prefixes
        WHERE group_name != '' AND owner_customer_id IS NULL
        GROUP BY group_name
        ORDER BY group_name
    """))
    return r.mappings().all()


@router.get("/prefixes")
async def list_prefixes(include_reseller: bool = False,
                         db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    """
    Por defecto solo el directorio de la plataforma (owner_customer_id IS NULL)
    — "el admin ve lo suyo y el reseller ve lo suyo". include_reseller=true es
    para soporte (ver qué prefijos privados crearon los resellers).
    """
    where = "" if include_reseller else "WHERE owner_customer_id IS NULL"
    r = await db.execute(text(f"SELECT * FROM prefixes {where} ORDER BY prefix"))
    return r.mappings().all()


@router.post("/prefixes", status_code=201)
async def add_prefix(body: PrefixIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    dup = await db.execute(text("SELECT id FROM prefixes WHERE prefix = :prefix"), {"prefix": body.prefix})
    if dup.first():
        raise HTTPException(409, "Ya existe un prefijo con ese código")
    await db.execute(text(
        "INSERT INTO prefixes (prefix, destination, group_name, country) VALUES (:prefix, :destination, :group_name, :country)"
    ), body.model_dump())
    await db.commit()
    r = await db.execute(text("SELECT LAST_INSERT_ID() AS id"))
    new_id = r.scalar()
    await record_event(db, "prefix", new_id, "created", admin.get("name") or admin.get("email"),
                        f"{body.prefix} — {body.destination}")
    await db.commit()
    return {"id": new_id, "ok": True}


@router.put("/prefixes/{pid}")
async def update_prefix(pid: int, body: PrefixIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    dup = await db.execute(text("SELECT id FROM prefixes WHERE prefix = :prefix AND id != :id"),
                            {"prefix": body.prefix, "id": pid})
    if dup.first():
        raise HTTPException(409, "Ya existe un prefijo con ese código")
    r_before = await db.execute(text("SELECT * FROM prefixes WHERE id = :id"), {"id": pid})
    before = r_before.mappings().first()
    data = body.model_dump(); data["id"] = pid
    result = await db.execute(text(
        "UPDATE prefixes SET prefix=:prefix, destination=:destination, group_name=:group_name, country=:country WHERE id=:id"
    ), data)
    if before:
        await diff_and_record(db, "prefix", pid, dict(before), body.model_dump(),
                               ["prefix", "destination", "group_name"], admin.get("name") or admin.get("email"))
    if result.rowcount == 0:
        raise HTTPException(404, "Prefijo no encontrado")
    await db.commit()
    return {"ok": True}


@router.delete("/prefixes/{pid}", status_code=204)
async def delete_prefix(pid: int, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    cnt = await db.execute(text("SELECT COUNT(*) FROM rates WHERE prefix_id = :id"), {"id": pid})
    if cnt.scalar() > 0:
        raise HTTPException(409, "Este prefijo tiene tarifas cargadas — bórralas antes de eliminarlo")
    cnt2 = await db.execute(text("SELECT COUNT(*) FROM carrier_rates WHERE prefix_id = :id"), {"id": pid})
    if cnt2.scalar() > 0:
        raise HTTPException(409, "Este prefijo tiene buy rates de carrier cargados — bórralos antes de eliminarlo")
    r = await db.execute(text("SELECT prefix, destination FROM prefixes WHERE id = :id"), {"id": pid})
    row = r.first()
    await db.execute(text("DELETE FROM prefixes WHERE id = :id"), {"id": pid})
    await record_event(db, "prefix", pid, "deleted", admin.get("name") or admin.get("email"),
                        f"{row[0]} — {row[1]}" if row else "")
    await db.commit()
