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

from ._shared import CarrierBuyRateIn, CarrierGroupBuyRateIn, CarrierIn, _my_cid, _sync

router = APIRouter()


# ── Carriers propios ─────────────────────────────────────────────────────────
# Mismo criterio "mini admin" que prefixes/rate_plans (modelo MagnusBilling,
# a pedido explícito del usuario) — el reseller carga su propia troncal SIP
# real, con sus propios buy-rates. gen_dispatcher.py NO necesita saber de
# esto: un carrier entra a un grupo (carrier_group_members) sin importar
# quién es su dueño — por eso no hizo falta tocar ese script para nada.

@router.get("/carriers")
async def list_carriers(user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    r = await db.execute(text("""
        SELECT ca.*, (SELECT COUNT(*) FROM carrier_rates cr WHERE cr.carrier_id = ca.id) AS rate_count
        FROM carriers ca WHERE ca.owner_customer_id = :cid ORDER BY ca.priority DESC, ca.name
    """), {"cid": _my_cid(user)})
    return r.mappings().all()


@router.get("/carriers/assignable")
async def list_assignable_carriers(user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    """
    Propios + de plataforma, pero de plataforma SOLO los que el admin le
    asignó explícitamente a este reseller — un carrier de plataforma es
    miembro del grupo Principal PROPIO del reseller (customers.
    routing_group_id sobre la propia fila de customers del reseller, ver
    customers.py::_ensure_own_group / assign_carrier — el admin lo asigna
    exactamente igual que a cualquier cliente normal). Antes esto devolvía
    TODOS los carriers de plataforma (owner_customer_id IS NULL) sin
    filtrar, así que un reseller sin ningún carrier asignado por el admin
    igual veía y podía asignar cualquiera a sus sub-clientes — sin admin no
    debe ver ninguno. Se gatea por show_reseller_customers (no
    show_reseller_carriers) porque lo consume la página de Sub-clientes al
    asignar carriers — un reseller sin la página "Carriers propios"
    habilitada igual puede asignar carriers de plataforma que el admin ya
    le concedió.
    """
    r = await db.execute(text("""
        SELECT c.id, c.name, c.status, (c.owner_customer_id = :cid) AS is_own,
               (SELECT COUNT(*) FROM carrier_rates cr WHERE cr.carrier_id = c.id) AS rate_count
        FROM carriers c
        WHERE c.owner_customer_id = :cid
           OR (c.owner_customer_id IS NULL
               AND EXISTS (
                   SELECT 1 FROM carrier_group_members m
                   JOIN customers rc ON rc.routing_group_id = m.group_id
                   WHERE rc.id = :cid AND m.carrier_id = c.id
               ))
        ORDER BY is_own DESC, c.priority DESC, c.name
    """), {"cid": _my_cid(user)})
    return r.mappings().all()


@router.post("/carriers", status_code=201)
async def create_carrier(body: CarrierIn, user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    data = body.model_dump(); data["owner_customer_id"] = my_cid
    result = await db.execute(text("""
        INSERT INTO carriers (name, host, port, priority, outbound_prefix, remove_prefix,
                              status, cps_limit, notes, owner_customer_id)
        VALUES (:name, :host, :port, :priority, :outbound_prefix, :remove_prefix,
                :status, :cps_limit, :notes, :owner_customer_id)
    """), data)
    await record_event(db, "carrier", result.lastrowid, "created_by_reseller",
                        user.get("name") or user.get("email"), body.name)
    await db.commit()
    _sync()
    return {"id": result.lastrowid}


async def _own_carrier_or_404(db: AsyncSession, cid: int, my_cid: int) -> None:
    r = await db.execute(text(
        "SELECT 1 FROM carriers WHERE id = :id AND owner_customer_id = :cid"
    ), {"id": cid, "cid": my_cid})
    if not r.first():
        raise HTTPException(404, "Carrier no encontrado — solo podés editar/borrar los que vos creaste")


@router.get("/carriers/{cid}")
async def get_carrier(cid: int, user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    await _own_carrier_or_404(db, cid, _my_cid(user))
    r = await db.execute(text("SELECT * FROM carriers WHERE id = :id"), {"id": cid})
    return r.mappings().first()


@router.put("/carriers/{cid}")
async def update_carrier(cid: int, body: CarrierIn, user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    await _own_carrier_or_404(db, cid, my_cid)
    r_before = await db.execute(text("SELECT * FROM carriers WHERE id = :id"), {"id": cid})
    before = r_before.mappings().first()
    data = body.model_dump(); data["id"] = cid
    await db.execute(text("""
        UPDATE carriers SET name=:name, host=:host, port=:port, priority=:priority,
        outbound_prefix=:outbound_prefix, remove_prefix=:remove_prefix, status=:status,
        cps_limit=:cps_limit, notes=:notes
        WHERE id=:id
    """), data)
    if before:
        await diff_and_record(db, "carrier", cid, dict(before), body.model_dump(),
                               ["status", "host", "port", "priority"], user.get("name") or user.get("email"))
    await db.commit()
    _sync()
    return {"ok": True}


@router.delete("/carriers/{cid}", status_code=204)
async def delete_carrier(cid: int, user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    await _own_carrier_or_404(db, cid, my_cid)
    r = await db.execute(text("SELECT name FROM carriers WHERE id = :id"), {"id": cid})
    row = r.first()
    await db.execute(text("DELETE FROM carriers WHERE id = :id"), {"id": cid})
    await record_event(db, "carrier", cid, "deleted_by_reseller", user.get("name") or user.get("email"),
                        row[0] if row else "")
    await db.commit()
    _sync()


@router.get("/carriers/{cid}/rates")
async def get_carrier_buy_rates(cid: int, user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    await _own_carrier_or_404(db, cid, _my_cid(user))
    r = await db.execute(text("""
        SELECT cr.*, p.prefix, p.destination
        FROM carrier_rates cr JOIN prefixes p ON cr.prefix_id = p.id
        WHERE cr.carrier_id = :id ORDER BY p.prefix
    """), {"id": cid})
    return r.mappings().all()


@router.post("/carriers/{cid}/rates", status_code=201)
async def add_carrier_buy_rate(cid: int, body: CarrierBuyRateIn, user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    await _own_carrier_or_404(db, cid, my_cid)
    data = body.model_dump(); data["carrier_id"] = cid
    await db.execute(text("""
        INSERT INTO carrier_rates (carrier_id, prefix_id, buy_rate, connectcharge, billingblock)
        VALUES (:carrier_id, :prefix_id, :buy_rate, :connectcharge, :billingblock)
        ON DUPLICATE KEY UPDATE buy_rate=:buy_rate, connectcharge=:connectcharge, billingblock=:billingblock
    """), data)
    await record_event(db, "carrier", cid, "buy_rate_set", user.get("name") or user.get("email"),
                        f"prefix_id={body.prefix_id} → {body.buy_rate}/min")
    await db.commit()
    return {"ok": True}


@router.post("/carriers/{cid}/group-rates", status_code=201)
async def add_carrier_group_buy_rate(cid: int, body: CarrierGroupBuyRateIn, user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    await _own_carrier_or_404(db, cid, my_cid)
    r = await db.execute(text("SELECT id FROM prefixes WHERE group_name = :g"), {"g": body.group_name})
    prefix_ids = [row[0] for row in r.fetchall()]
    # Auditoría v2.55: antes un INSERT por prefijo en loop — mismo criterio que
    # carriers.py::add_group_buy_rate (executemany en un solo round-trip).
    if prefix_ids:
        await db.execute(text("""
            INSERT INTO carrier_rates (carrier_id, prefix_id, buy_rate, connectcharge, billingblock)
            VALUES (:cid, :pfx, :rate, :cc, :bb)
            ON DUPLICATE KEY UPDATE buy_rate=:rate, connectcharge=:cc, billingblock=:bb
        """), [{"cid": cid, "pfx": pfx_id, "rate": body.buy_rate, "cc": body.connectcharge, "bb": body.billingblock}
               for pfx_id in prefix_ids])
    await record_event(db, "carrier", cid, "group_buy_rate_set", user.get("name") or user.get("email"),
                        f"grupo {body.group_name} → {body.buy_rate}/min ({len(prefix_ids)} prefijos)")
    await db.commit()
    return {"ok": True, "updated": len(prefix_ids)}


@router.delete("/carriers/{cid}/rates/{rid}", status_code=204)
async def delete_carrier_buy_rate(cid: int, rid: int, user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    await _own_carrier_or_404(db, cid, my_cid)
    await db.execute(text("DELETE FROM carrier_rates WHERE id=:id AND carrier_id=:cid"), {"id": rid, "cid": cid})
    await record_event(db, "carrier", cid, "buy_rate_deleted", user.get("name") or user.get("email"), f"rate_id={rid}")
    await db.commit()
