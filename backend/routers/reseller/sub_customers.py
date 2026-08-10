# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from alerts import check_balance_alert
from audit import diff_and_record, record_event
from auth import require_reseller_permission
from balance import apply_balance_change
from database import get_db
from techprefix import next_campaign_prefix, next_sub_customer_prefix

from ._shared import (
    _AUDITED_FIELDS, _my_cid, _own_group_or_404, _sync,
    BalanceIn, CustomerCarrierGroupIn, CustomerCarrierIn, CustomerPrefixIn,
    RoutingGroupIn, SubCustomerIn,
)

router = APIRouter()


# ── Sub-clientes ────────────────────────────────────────────────────────────

@router.get("/sub-customers")
async def list_sub_customers(include_deleted: bool = False,
                              user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    # Mismo criterio que customers.py::list_customers() — desactivados
    # ocultos por defecto, no mezclados sin distinción con los activos.
    where = "" if include_deleted else "AND c.status != 'deleted'"
    r = await db.execute(text(f"""
        SELECT c.*, rp.name AS rate_plan_name
        FROM customers c
        LEFT JOIN rate_plans rp ON c.rate_plan_id = rp.id
        WHERE c.parent_customer_id = :pid {where}
        ORDER BY c.name
    """), {"pid": _my_cid(user)})
    return r.mappings().all()


@router.post("/sub-customers", status_code=201)
async def create_sub_customer(body: SubCustomerIn, user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)

    # rate_plan_id, si se manda, debe ser un plan propio del reseller — nunca
    # uno de la plataforma ni de otro reseller.
    if body.rate_plan_id:
        rp = await db.execute(text(
            "SELECT 1 FROM rate_plans WHERE id = :id AND owner_customer_id = :cid"
        ), {"id": body.rate_plan_id, "cid": my_cid})
        if not rp.first():
            raise HTTPException(400, "rate_plan_id no es un plan propio de este reseller")

    data = body.model_dump()
    data["techprefix"] = await next_sub_customer_prefix(db)   # siempre autogenerado, nunca desde el body
    data["parent_customer_id"] = my_cid   # nunca confiar en un valor mandado por el cliente
    result = await db.execute(text("""
        INSERT INTO customers (parent_customer_id, name, company, email, phone,
                               rate_plan_id, techprefix, currency, billing_type, notes)
        VALUES (:parent_customer_id, :name, :company, :email, :phone,
                :rate_plan_id, :techprefix, :currency, :billing_type, :notes)
    """), data)
    await record_event(db, "customer", result.lastrowid, "created_by_reseller",
                        user.get("name") or user.get("email"), f"{body.name} <{body.email}>")
    await db.commit()
    return {"id": result.lastrowid}


@router.get("/sub-customers/{cid}")
async def get_sub_customer(cid: int, user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    r = await db.execute(text("""
        SELECT c.*, rp.name AS rate_plan_name
        FROM customers c
        LEFT JOIN rate_plans rp ON c.rate_plan_id = rp.id
        WHERE c.id = :id AND c.parent_customer_id = :pid
    """), {"id": cid, "pid": _my_cid(user)})
    row = r.mappings().first()
    if not row:
        raise HTTPException(404, "Sub-cliente no encontrado")
    # Mismo criterio que customers.py::get_customer() — grupos HABILITADOS
    # para este sub-cliente (customer_carrier_groups), no todos los grupos
    # propios del reseller. Sin esto, el panel reseller no tenía forma de
    # saber qué ya está habilitado al reabrir un sub-cliente.
    groups = await db.execute(text("""
        SELECT ccg.group_id, ccg.display_label, cg.name, cg.algorithm
        FROM customer_carrier_groups ccg JOIN carrier_groups cg ON ccg.group_id = cg.id
        WHERE ccg.customer_id = :id
    """), {"id": cid})
    return {**dict(row), "groups": groups.mappings().all()}


@router.put("/sub-customers/{cid}")
async def update_sub_customer(cid: int, body: SubCustomerIn, user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    existing = await db.execute(text(
        "SELECT billing_type, rate_plan_id, techprefix FROM customers WHERE id = :id AND parent_customer_id = :pid"
    ), {"id": cid, "pid": my_cid})
    before_row = existing.mappings().first()
    if not before_row:
        raise HTTPException(404, "Sub-cliente no encontrado")
    before = dict(before_row)

    if body.rate_plan_id:
        rp = await db.execute(text(
            "SELECT 1 FROM rate_plans WHERE id = :id AND owner_customer_id = :cid"
        ), {"id": body.rate_plan_id, "cid": my_cid})
        if not rp.first():
            raise HTTPException(400, "rate_plan_id no es un plan propio de este reseller")

    data = body.model_dump(); data["id"] = cid; data["pid"] = my_cid
    data["techprefix"] = before["techprefix"]   # nunca editable por el reseller — fijado al crear
    await db.execute(text("""
        UPDATE customers SET name=:name, company=:company, email=:email, phone=:phone,
        rate_plan_id=:rate_plan_id, techprefix=:techprefix, currency=:currency,
        billing_type=:billing_type, notes=:notes
        WHERE id=:id AND parent_customer_id=:pid
    """), data)
    # Mismo criterio que customers.py::update_customer() — diff de campo, no
    # solo un evento genérico. Antes esta función no dejaba ningún rastro en
    # Auditoría, a diferencia de create_sub_customer() (record_event).
    await diff_and_record(db, "customer", cid, before, data, _AUDITED_FIELDS,
                           user.get("name") or user.get("email"))
    await db.commit()
    return {"ok": True}


@router.post("/sub-customers/{cid}/balance")
async def adjust_sub_customer_balance(cid: int, body: BalanceIn, user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    existing = await db.execute(text(
        "SELECT status FROM customers WHERE id = :id AND parent_customer_id = :pid"
    ), {"id": cid, "pid": my_cid})
    row = existing.first()
    if not row:
        raise HTTPException(404, "Sub-cliente no encontrado")
    if row[0] == "deleted":
        # Solo el admin puede reactivar (POST /admin/customers/{cid}/reactivate)
        # — el reseller no tiene ese endpoint, por eso el mensaje no le pide
        # que lo haga él mismo.
        raise HTTPException(409, "El sub-cliente está desactivado — pedile al administrador que lo reactive")

    new_balance = await apply_balance_change(
        db, cid, body.amount, type="manual", reference="Ajuste manual desde panel reseller",
        created_by=user.get("name") or user.get("email"),
        extra_where=" AND parent_customer_id = :pid", extra_params={"pid": my_cid},
    )
    await db.commit()
    # Mismo hook que customers.py::adjust_balance() — sin esto, un ajuste hecho
    # por un reseller nunca dispara la alerta de saldo bajo del operador.
    await check_balance_alert(db, cid)
    return {"ok": True, "balance": new_balance}


# ── Prefijos de campaña de sub-clientes ──────────────────────────────────────
# Mismo concepto que customers.py::add_prefix/delete_prefix, pero scopeado a
# los sub-clientes propios del reseller. Ruta "techprefixes" (no "prefixes")
# a propósito — /reseller/prefixes ya existe y es otra cosa (prefijos de
# tarifa/rating, tabla `prefixes`, nada que ver con techprefix de routing).

@router.get("/sub-customers/{cid}/techprefixes")
async def list_sub_customer_prefixes(cid: int, user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    owns = await db.execute(text(
        "SELECT 1 FROM customers WHERE id = :id AND parent_customer_id = :pid"
    ), {"id": cid, "pid": _my_cid(user)})
    if not owns.first():
        raise HTTPException(404, "Sub-cliente no encontrado")
    r = await db.execute(text(
        "SELECT id, techprefix, label, routing_group_id "
        "FROM customer_prefixes WHERE customer_id = :id ORDER BY techprefix"
    ), {"id": cid})
    return r.mappings().all()


@router.post("/sub-customers/{cid}/techprefixes", status_code=201)
async def add_sub_customer_prefix(cid: int, body: CustomerPrefixIn, user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    owns = await db.execute(text(
        "SELECT 1 FROM customers WHERE id = :id AND parent_customer_id = :pid"
    ), {"id": cid, "pid": _my_cid(user)})
    if not owns.first():
        raise HTTPException(404, "Sub-cliente no encontrado")
    techprefix = await next_campaign_prefix(db)
    await db.execute(text(
        "INSERT INTO customer_prefixes (customer_id, techprefix, label) VALUES (:cid, :tp, :label)"
    ), {"cid": cid, "tp": techprefix, "label": body.label})
    await db.commit()
    _sync()
    return {"ok": True, "techprefix": techprefix}


@router.delete("/sub-customers/{cid}/techprefixes/{prefix_id}", status_code=204)
async def delete_sub_customer_prefix(cid: int, prefix_id: int, user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    owns = await db.execute(text(
        "SELECT 1 FROM customers WHERE id = :id AND parent_customer_id = :pid"
    ), {"id": cid, "pid": _my_cid(user)})
    if not owns.first():
        raise HTTPException(404, "Sub-cliente no encontrado")
    await db.execute(text(
        "DELETE FROM customer_prefixes WHERE id = :id AND customer_id = :cid"
    ), {"id": prefix_id, "cid": cid})
    await db.commit()
    _sync()


# ── Carriers de sub-clientes ─────────────────────────────────────────────────
# El reseller puede asignar a CADA sub-cliente propio sus carriers propios +
# los carriers de plataforma que el ADMIN le asignó a él (ver
# list_assignable_carriers, en carriers.py) — nunca los de otro reseller ni
# carriers de plataforma sin asignar. Igual que en customers.py, el gesto
# simple "asignale un carrier a este sub-cliente" crea/reutiliza el grupo
# Principal PROPIO del sub-cliente (customers.routing_group_id) por detrás.

async def _ensure_sub_customer_own_group(db: AsyncSession, cid: int, my_cid: int) -> int:
    """Mismo criterio que customers.py::_ensure_own_group, pero solo sobre
    sub-clientes propios de este reseller (owner_customer_id=my_cid, no
    NULL — un grupo creado automáticamente para un sub-cliente es del
    reseller, no de la plataforma)."""
    row = await db.execute(text(
        "SELECT routing_group_id, name FROM customers WHERE id = :id AND parent_customer_id = :pid"
    ), {"id": cid, "pid": my_cid})
    cust = row.mappings().first()
    if not cust:
        raise HTTPException(404, "Sub-cliente no encontrado")
    if cust["routing_group_id"]:
        return cust["routing_group_id"]

    result = await db.execute(text(
        "INSERT INTO carrier_groups (name, algorithm, owner_customer_id) "
        "VALUES (:name, 'priority', :owner)"
    ), {"name": f"{cust['name']} — Principal", "owner": my_cid})
    gid = result.lastrowid
    await db.execute(text(
        "UPDATE customers SET routing_group_id = :gid WHERE id = :cid"
    ), {"gid": gid, "cid": cid})
    await db.execute(text("""
        INSERT INTO customer_carrier_groups (customer_id, group_id, display_label)
        VALUES (:cid, :gid, 'Principal')
        ON DUPLICATE KEY UPDATE display_label = display_label
    """), {"cid": cid, "gid": gid})
    return gid


@router.get("/sub-customers/{cid}/carriers")
async def list_sub_customer_carriers(cid: int, user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    owns = await db.execute(text(
        "SELECT routing_group_id FROM customers WHERE id = :id AND parent_customer_id = :pid"
    ), {"id": cid, "pid": my_cid})
    row = owns.mappings().first()
    if not row:
        raise HTTPException(404, "Sub-cliente no encontrado")
    r = await db.execute(text("""
        SELECT m.carrier_id, m.priority, ca.name, ca.host, ca.status,
               (ca.owner_customer_id = :mycid) AS is_own
        FROM carrier_group_members m JOIN carriers ca ON m.carrier_id = ca.id
        WHERE m.group_id = :gid
        ORDER BY m.priority DESC
    """), {"gid": row["routing_group_id"], "mycid": my_cid})
    return r.mappings().all()


@router.post("/sub-customers/{cid}/carriers", status_code=201)
async def assign_carrier_to_sub_customer(cid: int, body: CustomerCarrierIn,
                                          user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
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

    # Mismo criterio que el lado admin (customers.py::assign_carrier) — un
    # carrier sin tarifas rutea igual pero factura buycost=0 en silencio.
    rated = await db.execute(text(
        "SELECT 1 FROM carrier_rates WHERE carrier_id = :cid LIMIT 1"
    ), {"cid": body.carrier_id})
    if not rated.first():
        raise HTTPException(400, "Este carrier no tiene tarifas de costo cargadas. Cárgale tarifas antes de asignarlo a un sub-cliente.")

    gid = await _ensure_sub_customer_own_group(db, cid, my_cid)
    await db.execute(text("""
        INSERT INTO carrier_group_members (group_id, carrier_id, priority)
        VALUES (:gid, :carid, :prio)
        ON DUPLICATE KEY UPDATE priority = :prio
    """), {"gid": gid, "carid": body.carrier_id, "prio": body.priority})
    await record_event(db, "customer", cid, "carrier_assigned", user.get("name") or user.get("email"),
                        f"carrier_id={body.carrier_id} priority={body.priority}")
    await db.commit()
    _sync()
    return {"ok": True}


@router.delete("/sub-customers/{cid}/carriers/{carrier_id}", status_code=204)
async def remove_carrier_from_sub_customer(cid: int, carrier_id: int,
                                            user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    owns = await db.execute(text(
        "SELECT routing_group_id FROM customers WHERE id = :id AND parent_customer_id = :pid"
    ), {"id": cid, "pid": my_cid})
    row = owns.mappings().first()
    if not row:
        raise HTTPException(404, "Sub-cliente no encontrado")
    if row["routing_group_id"]:
        await db.execute(text(
            "DELETE FROM carrier_group_members WHERE group_id = :gid AND carrier_id = :carid"
        ), {"gid": row["routing_group_id"], "carid": carrier_id})
    await record_event(db, "customer", cid, "carrier_removed", user.get("name") or user.get("email"),
                        f"carrier_id={carrier_id}")
    await db.commit()
    _sync()


# ── Grupos habilitados por sub-cliente + pin por prefijo ─────────────────────

@router.post("/sub-customers/{cid}/carrier-groups", status_code=201)
async def assign_group_to_sub_customer(cid: int, body: CustomerCarrierGroupIn,
                                        user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    """Habilita un grupo propio del reseller para que este sub-cliente pueda
    elegirlo — mismo criterio que assign_carrier_group() en customers.py."""
    my_cid = _my_cid(user)
    owns = await db.execute(text(
        "SELECT 1 FROM customers WHERE id = :id AND parent_customer_id = :pid"
    ), {"id": cid, "pid": my_cid})
    if not owns.first():
        raise HTTPException(404, "Sub-cliente no encontrado")
    await _own_group_or_404(db, body.group_id, my_cid)
    n = await db.execute(text(
        "SELECT COUNT(*) FROM customer_carrier_groups WHERE customer_id = :cid"
    ), {"cid": cid})
    display_label = f"Grupo {int(n.scalar()) + 1}"
    await db.execute(text("""
        INSERT INTO customer_carrier_groups (customer_id, group_id, display_label)
        VALUES (:cid, :gid, :label)
        ON DUPLICATE KEY UPDATE display_label = display_label
    """), {"cid": cid, "gid": body.group_id, "label": display_label})
    await db.commit()
    return {"ok": True}


@router.delete("/sub-customers/{cid}/carrier-groups/{group_id}", status_code=204)
async def unassign_group_from_sub_customer(cid: int, group_id: int,
                                            user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    owns = await db.execute(text(
        "SELECT 1 FROM customers WHERE id = :id AND parent_customer_id = :pid"
    ), {"id": cid, "pid": my_cid})
    if not owns.first():
        raise HTTPException(404, "Sub-cliente no encontrado")
    await db.execute(text(
        "DELETE FROM customer_carrier_groups WHERE customer_id = :cid AND group_id = :gid"
    ), {"cid": cid, "gid": group_id})
    await db.execute(text(
        "UPDATE customers SET routing_group_id = NULL WHERE id = :cid AND routing_group_id = :gid"
    ), {"cid": cid, "gid": group_id})
    await db.execute(text(
        "UPDATE customer_prefixes SET routing_group_id = NULL WHERE customer_id = :cid AND routing_group_id = :gid"
    ), {"cid": cid, "gid": group_id})
    await db.commit()
    _sync()


async def _set_sub_customer_routing_group(db: AsyncSession, my_cid: int, cid: int,
                                           prefix_id: int | None, group_id: int | None) -> None:
    owns = await db.execute(text(
        "SELECT 1 FROM customers WHERE id = :id AND parent_customer_id = :pid"
    ), {"id": cid, "pid": my_cid})
    if not owns.first():
        raise HTTPException(404, "Sub-cliente no encontrado")
    if group_id is not None:
        ok = await db.execute(text(
            "SELECT 1 FROM customer_carrier_groups WHERE customer_id = :cid AND group_id = :gid"
        ), {"cid": cid, "gid": group_id})
        if not ok.first():
            raise HTTPException(400, "Ese grupo no está habilitado para este sub-cliente — asignalo primero")
    if prefix_id is None:
        await db.execute(text(
            "UPDATE customers SET routing_group_id = :gid WHERE id = :cid"
        ), {"gid": group_id, "cid": cid})
    else:
        r = await db.execute(text(
            "UPDATE customer_prefixes SET routing_group_id = :gid WHERE id = :pid AND customer_id = :cid"
        ), {"gid": group_id, "pid": prefix_id, "cid": cid})
        if r.rowcount == 0:
            exists = await db.execute(text(
                "SELECT 1 FROM customer_prefixes WHERE id = :pid AND customer_id = :cid"
            ), {"pid": prefix_id, "cid": cid})
            if not exists.first():
                raise HTTPException(404, "Prefijo no encontrado")
    await db.commit()
    _sync()


@router.put("/sub-customers/{cid}/routing-group")
async def set_sub_customer_routing_group(cid: int, body: RoutingGroupIn,
                                          user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    """Techprefix PRINCIPAL del sub-cliente."""
    await _set_sub_customer_routing_group(db, _my_cid(user), cid, None, body.group_id)
    return {"ok": True}


@router.put("/sub-customers/{cid}/prefixes/{prefix_id}/routing-group")
async def set_sub_customer_prefix_routing_group(cid: int, prefix_id: int, body: RoutingGroupIn,
                                                 user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    """Mismo pin, para un prefijo de campaña puntual del sub-cliente."""
    await _set_sub_customer_routing_group(db, _my_cid(user), cid, prefix_id, body.group_id)
    return {"ok": True}
