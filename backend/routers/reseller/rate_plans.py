# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from audit import diff_and_record, record_event
from auth import require_reseller_permission
from database import get_db

from ._shared import GroupRateIn, PlanIn, PrefixIn, RateIn, _my_cid

router = APIRouter()


# ── Prefijos propios ─────────────────────────────────────────────────────────
# El reseller es un "mini admin" (mismo criterio que MagnusBilling): puede
# crear sus propios prefijos/destinos, igual que el admin crea los de la
# plataforma (backend/routers/rates.py). "El admin ve lo suyo y el reseller ve
# lo suyo" — cada quien administra (crea/edita/borra) solo lo que creó, pero
# el listado de abajo SÍ incluye los de la plataforma (owner NULL) además de
# los propios, porque el reseller necesita poder tarifar también destinos que
# ya existen (Lima, Provincia, etc.) al armar sus propios rate plans — nunca
# ve los prefijos privados de OTRO reseller. El motor de tarifación
# (cdrs.py::ingest_cdr) no filtra por owner: hace longest-prefix-match contra
# toda la tabla, así que un prefijo privado del reseller tarifa igual de bien
# en cuanto le carga una tarifa en su propio rate plan.

@router.get("/prefixes")
async def list_prefixes(user=Depends(require_reseller_permission("reseller_rates")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    r = await db.execute(text("""
        SELECT *, (owner_customer_id = :cid) AS is_own
        FROM prefixes
        WHERE owner_customer_id IS NULL OR owner_customer_id = :cid
        ORDER BY prefix
    """), {"cid": my_cid})
    return r.mappings().all()


@router.post("/prefixes", status_code=201)
async def create_prefix(body: PrefixIn, user=Depends(require_reseller_permission("reseller_rates")), db: AsyncSession = Depends(get_db)):
    dup = await db.execute(text("SELECT id FROM prefixes WHERE prefix = :prefix"), {"prefix": body.prefix})
    if dup.first():
        raise HTTPException(409, "Ya existe un prefijo con ese código")
    data = body.model_dump(); data["owner_customer_id"] = _my_cid(user)
    result = await db.execute(text("""
        INSERT INTO prefixes (prefix, destination, group_name, country, owner_customer_id)
        VALUES (:prefix, :destination, :group_name, :country, :owner_customer_id)
    """), data)
    await record_event(db, "prefix", result.lastrowid, "created_by_reseller",
                        user.get("name") or user.get("email"), f"{body.prefix} — {body.destination}")
    await db.commit()
    return {"id": result.lastrowid, "ok": True}


async def _own_prefix_or_404(db: AsyncSession, pid: int, my_cid: int) -> None:
    r = await db.execute(text(
        "SELECT 1 FROM prefixes WHERE id = :id AND owner_customer_id = :cid"
    ), {"id": pid, "cid": my_cid})
    if not r.first():
        raise HTTPException(404, "Prefijo no encontrado — solo podés editar/borrar los que vos creaste")


@router.put("/prefixes/{pid}")
async def update_prefix(pid: int, body: PrefixIn, user=Depends(require_reseller_permission("reseller_rates")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    await _own_prefix_or_404(db, pid, my_cid)
    dup = await db.execute(text("SELECT id FROM prefixes WHERE prefix = :prefix AND id != :id"),
                            {"prefix": body.prefix, "id": pid})
    if dup.first():
        raise HTTPException(409, "Ya existe un prefijo con ese código")
    r_before = await db.execute(text("SELECT * FROM prefixes WHERE id = :id"), {"id": pid})
    before = r_before.mappings().first()
    data = body.model_dump(); data["id"] = pid
    await db.execute(text(
        "UPDATE prefixes SET prefix=:prefix, destination=:destination, group_name=:group_name, country=:country WHERE id=:id"
    ), data)
    if before:
        await diff_and_record(db, "prefix", pid, dict(before), body.model_dump(),
                               ["prefix", "destination", "group_name"], user.get("name") or user.get("email"))
    await db.commit()
    return {"ok": True}


@router.delete("/prefixes/{pid}", status_code=204)
async def delete_prefix(pid: int, user=Depends(require_reseller_permission("reseller_rates")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    await _own_prefix_or_404(db, pid, my_cid)
    cnt = await db.execute(text("SELECT COUNT(*) FROM rates WHERE prefix_id = :id"), {"id": pid})
    if cnt.scalar() > 0:
        raise HTTPException(409, "Este prefijo tiene tarifas cargadas — bórralas antes de eliminarlo")
    r = await db.execute(text("SELECT prefix, destination FROM prefixes WHERE id = :id"), {"id": pid})
    row = r.first()
    await db.execute(text("DELETE FROM prefixes WHERE id = :id"), {"id": pid})
    await record_event(db, "prefix", pid, "deleted_by_reseller", user.get("name") or user.get("email"),
                        f"{row[0]} — {row[1]}" if row else "")
    await db.commit()


# ── Rate plans propios ──────────────────────────────────────────────────────

@router.get("/rate-plans")
async def list_rate_plans(user=Depends(require_reseller_permission("reseller_rates")), db: AsyncSession = Depends(get_db)):
    r = await db.execute(text(
        "SELECT * FROM rate_plans WHERE owner_customer_id = :cid ORDER BY name"
    ), {"cid": _my_cid(user)})
    return r.mappings().all()


@router.post("/rate-plans", status_code=201)
async def create_rate_plan(body: PlanIn, user=Depends(require_reseller_permission("reseller_rates")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    # Nombre único entre los planes de ESTE reseller — mismo criterio de
    # scoping que el resto del router (no puede haber dos planes "Standard"
    # del mismo reseller, sí puede haber uno por cada reseller distinto).
    dup = await db.execute(text(
        "SELECT 1 FROM rate_plans WHERE owner_customer_id = :cid AND name = :name"
    ), {"cid": my_cid, "name": body.name})
    if dup.first():
        raise HTTPException(409, "Ya tenés un plan con ese nombre")

    data = body.model_dump(); data["owner_customer_id"] = my_cid
    result = await db.execute(text("""
        INSERT INTO rate_plans (name, owner_customer_id, currency, description, status)
        VALUES (:name, :owner_customer_id, :currency, :description, 'active')
    """), data)
    await record_event(db, "rate_plan", result.lastrowid, "created_by_reseller",
                        user.get("name") or user.get("email"), body.name)
    await db.commit()
    return {"id": result.lastrowid}


async def _own_plan_or_404(db: AsyncSession, pid: int, my_cid: int) -> None:
    r = await db.execute(text(
        "SELECT 1 FROM rate_plans WHERE id = :id AND owner_customer_id = :cid"
    ), {"id": pid, "cid": my_cid})
    if not r.first():
        raise HTTPException(404, "Plan no encontrado")


@router.get("/rate-plans/{pid}/rates")
async def get_rate_plan_rates(pid: int, user=Depends(require_reseller_permission("reseller_rates")), db: AsyncSession = Depends(get_db)):
    await _own_plan_or_404(db, pid, _my_cid(user))
    r = await db.execute(text("""
        SELECT r.*, p.prefix, p.destination, p.group_name, p.country
        FROM rates r JOIN prefixes p ON r.prefix_id = p.id
        WHERE r.rate_plan_id = :pid ORDER BY p.prefix
    """), {"pid": pid})
    return r.mappings().all()


@router.post("/rate-plans/{pid}/rates", status_code=201)
async def set_rate(pid: int, body: RateIn, user=Depends(require_reseller_permission("reseller_rates")), db: AsyncSession = Depends(get_db)):
    await _own_plan_or_404(db, pid, _my_cid(user))
    data = body.model_dump(); data["rate_plan_id"] = pid
    await db.execute(text("""
        INSERT INTO rates (rate_plan_id, prefix_id, rateinitial, connectcharge,
                           initblock, billingblock, minimal_time_charge, status)
        VALUES (:rate_plan_id, :prefix_id, :rateinitial, :connectcharge,
                :initblock, :billingblock, :minimal_time_charge, 'active')
        ON DUPLICATE KEY UPDATE rateinitial=:rateinitial, connectcharge=:connectcharge,
            initblock=:initblock, billingblock=:billingblock
    """), data)
    await record_event(db, "rate_plan", pid, "rate_set", user.get("name") or user.get("email"),
                        f"prefix_id={body.prefix_id} → {body.rateinitial}/min")
    await db.commit()
    return {"ok": True}


@router.post("/rate-plans/{pid}/group-rates", status_code=201)
async def add_group_rate(pid: int, body: GroupRateIn, user=Depends(require_reseller_permission("reseller_rates")), db: AsyncSession = Depends(get_db)):
    await _own_plan_or_404(db, pid, _my_cid(user))
    r = await db.execute(text("SELECT id FROM prefixes WHERE group_name = :g"), {"g": body.group_name})
    prefix_ids = [row[0] for row in r.fetchall()]
    # Auditoría v2.55: antes un INSERT por prefijo en loop — mismo criterio que
    # carriers.py::add_group_buy_rate (executemany en un solo round-trip).
    #
    # Bug real de producción (v2.58.8): el ON DUPLICATE KEY UPDATE NO puede
    # reusar los placeholders del VALUES acá — aiomysql reescribe executemany()
    # armando un solo INSERT con múltiples VALUES(...) y pega el resto de la
    # sentencia una sola vez al final; si esa cola tiene placeholders con
    # nombres repetidos del VALUES, sobran al aplicar el %-formatting final →
    # TypeError: not all arguments converted during string formatting.
    # VALUES(columna) lee el valor de la fila que se está insertando sin
    # necesitar re-bindear el parámetro.
    if prefix_ids:
        await db.execute(text("""
            INSERT INTO rates (rate_plan_id, prefix_id, rateinitial, connectcharge,
                               initblock, billingblock, minimal_time_charge, status)
            VALUES (:pid, :pfx, :rate, :cc, :ib, :bb, 0, 'active')
            ON DUPLICATE KEY UPDATE rateinitial=VALUES(rateinitial), connectcharge=VALUES(connectcharge),
                initblock=VALUES(initblock), billingblock=VALUES(billingblock)
        """), [{"pid": pid, "pfx": pfx_id, "rate": body.rateinitial, "cc": body.connectcharge,
                "ib": body.initblock, "bb": body.billingblock} for pfx_id in prefix_ids])
    await record_event(db, "rate_plan", pid, "group_rate_set", user.get("name") or user.get("email"),
                        f"grupo {body.group_name} → {body.rateinitial}/min ({len(prefix_ids)} prefijos)")
    await db.commit()
    return {"ok": True, "updated": len(prefix_ids)}


@router.delete("/rate-plans/{pid}/rates/{rid}", status_code=204)
async def delete_rate(pid: int, rid: int, user=Depends(require_reseller_permission("reseller_rates")), db: AsyncSession = Depends(get_db)):
    await _own_plan_or_404(db, pid, _my_cid(user))
    await db.execute(text("DELETE FROM rates WHERE id=:id AND rate_plan_id=:pid"), {"id": rid, "pid": pid})
    await record_event(db, "rate_plan", pid, "rate_deleted", user.get("name") or user.get("email"), f"rate_id={rid}")
    await db.commit()
