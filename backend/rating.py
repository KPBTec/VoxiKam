# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
rating.py — cálculo de tarifas compartido entre los dos caminos de
facturación: routers/cdrs.py::ingest_cdr() (camino síncrono, el que corre en
producción para llamadas nuevas) y main.py::_billing_worker() (camino de
respaldo, para CDRs que quedaron con buycost=0).

Auditoría v2.55 (workflow multi-agente), hallazgo backend/QA: billable_blocks()
existía DUPLICADO byte a byte en los dos archivos, y el longest-prefix-match +
cascada de reseller (buy rate del carrier, sell rate del cliente, cost del
reseller si el cliente depende de uno) estaba reimplementado con la misma
lógica en los dos lugares — cualquier fix de tarifas (ej. el bug de initblock
de v2.38.0) tenía que aplicarse dos veces a mano.

`calc_bill()` recibe `dst` YA NORMALIZADO (sin techprefix del cliente ni
outbound_prefix del carrier) — esa normalización es específica de
ingest_cdr() y sigue viviendo ahí, este módulo no la duplica.

Paridad verificada: tests/test_billable_blocks.py, tests/test_calc_bill.py y
tests/test_ingest_cdr.py se escribieron ANTES de esta extracción, contra el
código viejo (una copia en cada archivo) — pasan sin ningún cambio contra
este módulo ya extraído, lo que confirma que el comportamiento no cambió.
"""
import math

from sqlalchemy import text


def billable_blocks(seconds: int, initblock: int, billingblock: int) -> int:
    """
    Esquema típico de telco: los primeros `initblock` segundos se facturan
    como un bloque fijo (aunque la llamada dure menos), el resto se redondea
    hacia arriba en incrementos de `billingblock`. `initblock=0` (carrier_rates
    no tiene esta columna) degenera correctamente a "todo en bloques de
    billingblock", el comportamiento de siempre.
    """
    if seconds <= initblock:
        return initblock
    return initblock + math.ceil((seconds - initblock) / billingblock) * billingblock


async def calc_bill(db, customer_id, carrier_id, dst: str, billsec: int):
    """
    Devuelve (buycost, sessionbill, reseller_cost, matched_prefix) para un
    CDR contestado. reseller_cost es None salvo que el cliente dependa de un
    reseller (customers.parent_customer_id).
    """
    buycost, sessionbill = 0.0, 0.0
    reseller_cost = None
    matched_prefix = None

    if carrier_id and billsec > 0:
        rb = await db.execute(text("""
            SELECT cr.buy_rate, cr.billingblock, cr.connectcharge
            FROM carrier_rates cr
            JOIN prefixes p ON cr.prefix_id = p.id
            WHERE cr.carrier_id = :cid AND :dst LIKE CONCAT(p.prefix, '%')
            ORDER BY LENGTH(p.prefix) DESC LIMIT 1
        """), {"cid": carrier_id, "dst": dst})
        row = rb.mappings().first()
        if row:
            blocks  = billable_blocks(billsec, 0, int(row["billingblock"]))
            buycost = round(blocks / 60 * float(row["buy_rate"]) + float(row["connectcharge"]), 6)

    parent_customer_id = None
    if customer_id and billsec > 0:
        rs = await db.execute(text("""
            SELECT r.rateinitial, r.initblock, r.billingblock, r.connectcharge,
                   r.minimal_time_charge, p.prefix, cu.parent_customer_id
            FROM rates r
            JOIN prefixes p   ON r.prefix_id   = p.id
            JOIN customers cu ON r.rate_plan_id = cu.rate_plan_id AND cu.id = :cid
            WHERE :dst LIKE CONCAT(p.prefix, '%') AND r.status = 'active'
            ORDER BY LENGTH(p.prefix) DESC LIMIT 1
        """), {"cid": customer_id, "dst": dst})
        row = rs.mappings().first()
        if row:
            billable    = max(billsec, int(row["minimal_time_charge"] or 0))
            blocks      = billable_blocks(billable, int(row["initblock"]), int(row["billingblock"]))
            sessionbill = round(blocks / 60 * float(row["rateinitial"]) + float(row["connectcharge"]), 6)
            matched_prefix = row["prefix"]
            parent_customer_id = row["parent_customer_id"]

        if parent_customer_id and billsec > 0:
            rr = await db.execute(text("""
                SELECT r.rateinitial, r.initblock, r.billingblock, r.connectcharge, r.minimal_time_charge
                FROM rates r
                JOIN customers cu ON r.rate_plan_id = cu.rate_plan_id AND cu.id = :pid
                JOIN prefixes p   ON r.prefix_id = p.id
                WHERE :dst LIKE CONCAT(p.prefix, '%') AND r.status = 'active'
                ORDER BY LENGTH(p.prefix) DESC LIMIT 1
            """), {"pid": parent_customer_id, "dst": dst})
            reseller_row = rr.mappings().first()
            if reseller_row:
                billable_r = max(billsec, int(reseller_row["minimal_time_charge"] or 0))
                blocks_r   = billable_blocks(billable_r, int(reseller_row["initblock"]), int(reseller_row["billingblock"]))
                reseller_cost = round(blocks_r / 60 * float(reseller_row["rateinitial"]) + float(reseller_row["connectcharge"]), 6)

    return buycost, sessionbill, reseller_cost, matched_prefix
