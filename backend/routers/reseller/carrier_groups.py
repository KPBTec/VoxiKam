# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from audit import record_event
from auth import require_reseller_permission
from database import get_db

from ._shared import GroupMemberIn, SubCustomerGroupIn, _my_cid, _own_group_or_404, _sync

router = APIRouter()


# ── Grupos de ruteo propios ───────────────────────────────────────────────────
# Mismo concepto que backend/routers/carrier_groups.py (admin), pero scopeado
# a owner_customer_id = este reseller — mismo criterio "mini admin" que ya
# usan prefixes/rate_plans/carriers propios. Reemplaza el pin único
# active_carrier_id/carrier_failover_enabled y el reparto por %
# customers.carrier_split_mode de antes.

@router.get("/carrier-groups")
async def list_own_groups(user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    r = await db.execute(text("""
        SELECT g.*, (SELECT COUNT(*) FROM carrier_group_members m WHERE m.group_id = g.id) AS member_count
        FROM carrier_groups g WHERE g.owner_customer_id = :cid ORDER BY g.name
    """), {"cid": _my_cid(user)})
    return r.mappings().all()


@router.get("/carrier-groups/{gid}")
async def get_own_group(gid: int, user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    await _own_group_or_404(db, gid, my_cid)
    g = await db.execute(text("SELECT * FROM carrier_groups WHERE id = :id"), {"id": gid})
    members = await db.execute(text("""
        SELECT m.carrier_id, m.priority, m.weight, ca.name, ca.host, ca.status
        FROM carrier_group_members m JOIN carriers ca ON m.carrier_id = ca.id
        WHERE m.group_id = :id ORDER BY m.priority DESC
    """), {"id": gid})
    # Solo sub-clientes PROPIOS — un grupo de un reseller solo lo puede
    # habilitar ese mismo reseller para sus sub-clientes (ver
    # assign_group_to_sub_customer, valida _own_group_or_404).
    used_by = await db.execute(text("""
        SELECT c.id AS customer_id, c.name AS customer_name, 'principal' AS ref, c.techprefix AS label
        FROM customers c WHERE c.routing_group_id = :id AND c.parent_customer_id = :mycid
        UNION ALL
        SELECT c.id AS customer_id, c.name AS customer_name, 'campaña' AS ref,
               COALESCE(cp.label, cp.techprefix) AS label
        FROM customer_prefixes cp JOIN customers c ON c.id = cp.customer_id
        WHERE cp.routing_group_id = :id AND c.parent_customer_id = :mycid
        ORDER BY customer_name
    """), {"id": gid, "mycid": my_cid})
    return {**dict(g.mappings().first()), "members": members.mappings().all(), "used_by": used_by.mappings().all()}


@router.post("/carrier-groups", status_code=201)
async def create_own_group(body: SubCustomerGroupIn, user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    result = await db.execute(text(
        "INSERT INTO carrier_groups (name, algorithm, owner_customer_id) VALUES (:name, :algorithm, :cid)"
    ), {**body.model_dump(), "cid": my_cid})
    new_id = result.lastrowid
    await record_event(db, "carrier_group", new_id, "created_by_reseller", user.get("name") or user.get("email"), body.name)
    await db.commit()
    return {"id": new_id}


@router.put("/carrier-groups/{gid}")
async def update_own_group(gid: int, body: SubCustomerGroupIn, user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    await _own_group_or_404(db, gid, my_cid)
    await db.execute(text(
        "UPDATE carrier_groups SET name=:name, algorithm=:algorithm WHERE id=:id"
    ), {**body.model_dump(), "id": gid})
    await db.commit()
    _sync()
    return {"ok": True}


@router.delete("/carrier-groups/{gid}", status_code=204)
async def delete_own_group(gid: int, user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    await _own_group_or_404(db, gid, my_cid)
    in_use = await db.execute(text("""
        SELECT customer_name, COUNT(*) AS n_prefixes FROM (
            SELECT c.id AS customer_id, c.name AS customer_name
            FROM customers c WHERE c.routing_group_id = :id
            UNION ALL
            SELECT c.id AS customer_id, c.name AS customer_name
            FROM customer_prefixes cp JOIN customers c ON c.id = cp.customer_id
            WHERE cp.routing_group_id = :id
        ) t
        GROUP BY customer_id, customer_name
        ORDER BY customer_name
    """), {"id": gid})
    users = in_use.mappings().all()
    if users:
        shown = ", ".join(f"{u['customer_name']} ({u['n_prefixes']})" for u in users[:5])
        extra = f" y {len(users) - 5} más" if len(users) > 5 else ""
        raise HTTPException(409, f"Este grupo está en uso por: {shown}{extra} — desasignalo antes de borrarlo")
    row = await db.execute(text("SELECT name FROM carrier_groups WHERE id = :id"), {"id": gid})
    g = row.mappings().first()
    await db.execute(text("DELETE FROM carrier_groups WHERE id = :id"), {"id": gid})
    await record_event(db, "carrier_group", gid, "deleted_by_reseller", user.get("name") or user.get("email"), g["name"] if g else "")
    await db.commit()


@router.post("/carrier-groups/{gid}/members", status_code=201)
async def add_own_group_member(gid: int, body: GroupMemberIn, user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    await _own_group_or_404(db, gid, my_cid)
    # Mismo criterio de visibilidad que assign_carrier_to_sub_customer —
    # propio o de plataforma ya asignado a este reseller.
    ok = await db.execute(text("""
        SELECT 1 FROM carriers c
        WHERE c.id = :id
          AND (c.owner_customer_id = :mycid
               OR (c.owner_customer_id IS NULL
                   AND EXISTS (
                       SELECT 1 FROM carrier_group_members m
                       JOIN customers rc ON rc.routing_group_id = m.group_id
                       WHERE rc.id = :mycid AND m.carrier_id = c.id
                   )))
    """), {"id": body.carrier_id, "mycid": my_cid})
    if not ok.first():
        raise HTTPException(400, "carrier_id debe ser propio de este reseller o un carrier de plataforma que el admin te haya asignado")
    await db.execute(text("""
        INSERT INTO carrier_group_members (group_id, carrier_id, priority, weight)
        VALUES (:gid, :carrier_id, :priority, :weight)
        ON DUPLICATE KEY UPDATE priority = :priority, weight = :weight
    """), {"gid": gid, **body.model_dump()})
    await db.commit()
    _sync()
    return {"ok": True}


@router.delete("/carrier-groups/{gid}/members/{carrier_id}", status_code=204)
async def remove_own_group_member(gid: int, carrier_id: int, user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    await _own_group_or_404(db, gid, _my_cid(user))
    await db.execute(text(
        "DELETE FROM carrier_group_members WHERE group_id = :gid AND carrier_id = :cid"
    ), {"gid": gid, "cid": carrier_id})
    await db.commit()
    _sync()
