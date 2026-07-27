# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Routing Simulation — dry-run de qué carrier y qué tarifa aplicaría para un
cliente + destino, SIN originar ninguna llamada. Solo lecturas: replica la
misma lógica de longest-prefix-match que ya usan routers/cdrs.py (billing) y
gen_dispatcher.py (orden de carriers), para responder "¿por qué esta llamada
saldría/salió por este carrier y a este costo?" sin abrir una consola.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from auth import require_admin
from database import get_db

router = APIRouter()


@router.get("/simulate")
async def simulate(
    customer_id: int = Query(...),
    destination: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    cust_row = await db.execute(text("""
        SELECT id, name, status, techprefix, rate_plan_id, routing_group_id FROM customers WHERE id = :id
    """), {"id": customer_id})
    customer = cust_row.mappings().first()
    if not customer:
        raise HTTPException(404, "Cliente no encontrado")

    # Un cliente puede tener, además del techprefix principal, varios
    # prefijos de campaña (customer_prefixes) — probar contra TODOS,
    # más largo primero, igual criterio que gen_dispatcher.py/cron_dlg_stats.py.
    # Antes solo probaba customer["techprefix"]: un destino marcado con un
    # prefijo de campaña simulaba mal (no lo despojaba, la tarifa/carrier
    # mostrados no correspondían a lo que realmente ruteaba en producción).
    # routing_group_id por prefijo: None en customer_prefixes = hereda el
    # del cliente (mismo criterio que gen_dispatcher.py::build_techprefix_rows).
    prefixes = [(customer["techprefix"], customer["routing_group_id"])] if customer["techprefix"] else []
    extra = await db.execute(text(
        "SELECT techprefix, routing_group_id FROM customer_prefixes WHERE customer_id = :cid"
    ), {"cid": customer_id})
    prefixes += [(row["techprefix"], row["routing_group_id"] or customer["routing_group_id"]) for row in extra.mappings().all()]
    prefixes.sort(key=lambda p: len(p[0]), reverse=True)

    dst = destination.strip()
    matched_techprefix = None
    matched_group_id = None
    for pfx, gid in prefixes:
        if pfx and dst.startswith(pfx):
            dst = dst[len(pfx):]
            matched_techprefix = pfx
            matched_group_id = gid
            break

    sell = None
    if customer["rate_plan_id"]:
        r = await db.execute(text("""
            SELECT p.prefix, p.destination, p.group_name, r.rateinitial, r.connectcharge,
                   r.billingblock, r.minimal_time_charge
            FROM rates r JOIN prefixes p ON r.prefix_id = p.id
            WHERE r.rate_plan_id = :plan_id AND :dst LIKE CONCAT(p.prefix, '%')
            ORDER BY LENGTH(p.prefix) DESC LIMIT 1
        """), {"plan_id": customer["rate_plan_id"], "dst": dst})
        row = r.mappings().first()
        if row:
            sell = dict(row)

    # Carriers del GRUPO efectivo para el prefijo que matcheó — no de
    # "todos los carriers del cliente" (eso ya no es una cosa; ver
    # backend/routers/customers.py::_ensure_own_group y Grupos de ruteo).
    # Sin match de prefijo (matched_group_id=None) devuelve vacío, mismo
    # criterio que gen_dispatcher.py: sin grupo resuelto, no hay a dónde rutear.
    carrier_rows = []
    if matched_group_id:
        carriers_res = await db.execute(text("""
            SELECT ca.id, ca.name, ca.host, ca.port, ca.status, ca.outbound_prefix,
                   ca.remove_prefix, m.priority
            FROM carrier_group_members m
            JOIN carriers ca ON ca.id = m.carrier_id
            WHERE m.group_id = :gid
            ORDER BY m.priority DESC
        """), {"gid": matched_group_id})
        carrier_rows = carriers_res.mappings().all()

    carriers = []
    first_active_found = False
    for c in carrier_rows:
        carrier_dst = dst
        if c["remove_prefix"] and carrier_dst.startswith(c["remove_prefix"]):
            carrier_dst = carrier_dst[len(c["remove_prefix"]):]
        if c["outbound_prefix"]:
            carrier_dst = c["outbound_prefix"] + carrier_dst

        buy = None
        r = await db.execute(text("""
            SELECT p.prefix, cr.buy_rate, cr.connectcharge, cr.billingblock
            FROM carrier_rates cr JOIN prefixes p ON cr.prefix_id = p.id
            WHERE cr.carrier_id = :cid AND :dst LIKE CONCAT(p.prefix, '%')
            ORDER BY LENGTH(p.prefix) DESC LIMIT 1
        """), {"cid": c["id"], "dst": carrier_dst})
        row = r.mappings().first()
        if row:
            buy = dict(row)

        would_select = c["status"] == "active" and not first_active_found
        if would_select:
            first_active_found = True

        margin = None
        if sell is not None and buy is not None:
            margin = round(float(sell["rateinitial"]) - float(buy["buy_rate"]), 6)

        carriers.append({
            "carrier_id": c["id"], "carrier_name": c["name"], "host": c["host"], "port": c["port"],
            "status": c["status"], "priority": c["priority"],
            "transformed_destination": carrier_dst,
            "buy_rate": buy, "margin_per_minute": margin,
            "would_select": would_select,
        })

    if not matched_group_id:
        warning = "Este prefijo no tiene un Grupo de ruteo resuelto — la llamada fallaría con 503"
    elif not first_active_found:
        warning = "Ningún carrier activo en el grupo — la llamada fallaría con 503"
    else:
        warning = None

    return {
        "customer": {"id": customer["id"], "name": customer["name"], "status": customer["status"]},
        "destination_input": destination,
        "destination_normalized": dst,
        "matched_techprefix": matched_techprefix,
        "sell_rate": sell,
        "carriers": carriers,
        "warning": warning,
    }
