#!/usr/bin/env python3
# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Migración manual, única — recalcula sessionbill/buycost/reseller_cost de CDRs
ya facturados con el bug real de initblock/billingblock encontrado en
producción: el default de fábrica (60/60) redondeaba TODA llamada hacia
arriba al minuto completo, en vez de facturar por segundo real (1/1). La
tarifa configurada (S/./min) nunca cambió — el bloque de facturación sí, y
eso infla el costo de llamadas cortas sin que se note en el panel de Tarifas.

Los CDRs ya facturados quedan congelados para siempre — cambiar rates/
carrier_rates (ya corregido a 1/1 en esta misma sesión) solo afecta llamadas
NUEVAS. Este script corrige el histórico ya facturado mal:
  1. Recalcula buycost/sessionbill/reseller_cost por CDR (misma fórmula
     exacta que backend/main.py::_billable_blocks()/_calc_bill(), contra las
     rates/carrier_rates ACTUALES — ya corregidas a 1/1).
  2. Ajusta el balance del cliente por la diferencia neta (positiva = se le
     devuelve lo cobrado de más), con su propio balance_transactions.
  3. Refresca cdr_summary_day/month del rango afectado (scripts/cron_summary.py
     — si no se refresca, el reporte admin mensual/diario sigue leyendo el
     número viejo aunque el CDR ya esté corregido).

Rendimiento: las tarifas (rates/carrier_rates + prefixes) se cargan UNA sola
vez en memoria al arrancar — el longest-prefix-match se hace en Python
(str.startswith, ya ordenado por longitud descendente), no contra la base
por cada CDR. Con millones de CDRs, hacer 2-3 queries individuales por fila
tarda horas; esto tarda minutos. Los CDRs se leen en lotes (fetchmany) para
no cargar todo en memoria de una vez y para poder mostrar progreso real.

Dry-run por default (solo reporta, no toca nada). --apply para aplicar de
verdad.

Uso:
    venv/bin/python3 scripts/recalc_billing_blocks.py --from 2026-07-01 --to 2026-07-15
    venv/bin/python3 scripts/recalc_billing_blocks.py --from 2026-07-01 --to 2026-07-15 --apply
    venv/bin/python3 scripts/recalc_billing_blocks.py --from 2026-07-01 --to 2026-07-15 --customer-id 2 --apply
"""
import argparse
import math
import sys
import time
from pathlib import Path

import pymysql

sys.path.insert(0, str(Path(__file__).parent))
from cron_summary import get_db, run_summary  # reusa la agregación ya probada, no reimplementarla

BATCH_SIZE = 20_000


def _billable_blocks(seconds: int, initblock: int, billingblock: int) -> int:
    """Idéntico a backend/main.py::_billable_blocks() — no reimplementar con
    otra fórmula, tiene que dar exactamente lo mismo que produjo/produce el
    billing worker real."""
    if seconds <= initblock:
        return initblock
    return initblock + math.ceil((seconds - initblock) / billingblock) * billingblock


def _load_rates_by_plan(cur) -> dict:
    """rate_plan_id -> [(prefix, rateinitial, initblock, billingblock, connectcharge, minimal_time_charge), ...]
    ordenado por longitud de prefijo DESCENDENTE — el primer match en un
    recorrido lineal ya es el longest-prefix-match (mismo criterio que
    ORDER BY LENGTH(p.prefix) DESC LIMIT 1 en SQL)."""
    cur.execute("""
        SELECT r.rate_plan_id, p.prefix, r.rateinitial, r.initblock, r.billingblock,
               r.connectcharge, r.minimal_time_charge
        FROM rates r JOIN prefixes p ON r.prefix_id = p.id
        WHERE r.status = 'active'
    """)
    by_plan: dict = {}
    for row in cur.fetchall():
        by_plan.setdefault(row["rate_plan_id"], []).append((
            row["prefix"], float(row["rateinitial"]), int(row["initblock"]),
            int(row["billingblock"]), float(row["connectcharge"]), int(row["minimal_time_charge"] or 0),
        ))
    for plan_id in by_plan:
        by_plan[plan_id].sort(key=lambda t: len(t[0]), reverse=True)
    return by_plan


def _load_carrier_rates(cur) -> dict:
    """carrier_id -> [(prefix, buy_rate, billingblock, connectcharge), ...], mismo criterio de orden."""
    cur.execute("""
        SELECT cr.carrier_id, p.prefix, cr.buy_rate, cr.billingblock, cr.connectcharge
        FROM carrier_rates cr JOIN prefixes p ON cr.prefix_id = p.id
    """)
    by_carrier: dict = {}
    for row in cur.fetchall():
        by_carrier.setdefault(row["carrier_id"], []).append((
            row["prefix"], float(row["buy_rate"]), int(row["billingblock"]), float(row["connectcharge"]),
        ))
    for carrier_id in by_carrier:
        by_carrier[carrier_id].sort(key=lambda t: len(t[0]), reverse=True)
    return by_carrier


def _match(dst: str, entries: list):
    for entry in entries:
        if dst.startswith(entry[0]):
            return entry
    return None


def _recalc_one(dst, billsec, rate_plan_id, parent_rate_plan_id, carrier_id,
                 rates_by_plan: dict, carrier_rates: dict):
    """Misma lógica que backend/main.py::_calc_bill(), en memoria — sin
    ninguna query por CDR."""
    buycost, sessionbill, reseller_cost = 0.0, 0.0, None

    if carrier_id and billsec > 0:
        m = _match(dst, carrier_rates.get(carrier_id, []))
        if m:
            _, buy_rate, cr_bb, cr_cc = m
            blocks = _billable_blocks(billsec, 0, cr_bb)
            buycost = round(blocks / 60 * buy_rate + cr_cc, 6)

    if rate_plan_id and billsec > 0:
        m = _match(dst, rates_by_plan.get(rate_plan_id, []))
        if m:
            _, rateinitial, initblock, billingblock, connectcharge, min_charge = m
            billable = max(billsec, min_charge)
            blocks = _billable_blocks(billable, initblock, billingblock)
            sessionbill = round(blocks / 60 * rateinitial + connectcharge, 6)

        if parent_rate_plan_id and billsec > 0:
            mr = _match(dst, rates_by_plan.get(parent_rate_plan_id, []))
            if mr:
                _, rateinitial_r, initblock_r, billingblock_r, connectcharge_r, min_charge_r = mr
                billable_r = max(billsec, min_charge_r)
                blocks_r = _billable_blocks(billable_r, initblock_r, billingblock_r)
                reseller_cost = round(blocks_r / 60 * rateinitial_r + connectcharge_r, 6)

    return buycost, sessionbill, reseller_cost


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="date_from", required=True, help="YYYY-MM-DD, inclusive")
    ap.add_argument("--to", dest="date_to", required=True, help="YYYY-MM-DD, exclusivo")
    ap.add_argument("--customer-id", type=int, default=None)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    conn = get_db()
    cur = conn.cursor(pymysql.cursors.DictCursor)

    print("Cargando tarifas en memoria (rates + carrier_rates + customers)...")
    rates_by_plan = _load_rates_by_plan(cur)
    carrier_rates = _load_carrier_rates(cur)
    cur.execute("SELECT id, name, rate_plan_id, parent_customer_id FROM customers")
    customers = {row["id"]: row for row in cur.fetchall()}
    # rate_plan_id del reseller padre, resuelto una sola vez (no por CDR)
    parent_plan = {
        cid: customers[c["parent_customer_id"]]["rate_plan_id"]
        for cid, c in customers.items()
        if c["parent_customer_id"] and c["parent_customer_id"] in customers
    }
    print(f"  {sum(len(v) for v in rates_by_plan.values())} tarifas de venta, "
          f"{sum(len(v) for v in carrier_rates.values())} de compra, {len(customers)} clientes.")

    where = "disposition='ANSWERED' AND billsec > 0 AND start_ts >= %s AND start_ts < %s"
    params = [args.date_from, args.date_to]
    if args.customer_id:
        where += " AND customer_id = %s"
        params.append(args.customer_id)

    # Cursor server-side (SSCursor) — con fetchmany normal, pymysql igual trae
    # todo el resultset a memoria del cliente en el primer execute(). Con
    # millones de filas usamos SSDictCursor para leer en streaming real.
    scur = conn.cursor(pymysql.cursors.SSDictCursor)
    scur.execute(f"""
        SELECT id, customer_id, carrier_id, dst_number, billsec, buycost, sessionbill, reseller_cost, start_ts
        FROM cdrs WHERE {where} ORDER BY customer_id, start_ts
    """, params)

    per_customer = {}
    to_update = []
    affected_dates = set()
    total = 0
    t0 = time.time()

    while True:
        batch = scur.fetchmany(BATCH_SIZE)
        if not batch:
            break
        for r in batch:
            total += 1
            cust = customers.get(r["customer_id"])
            rate_plan_id = cust["rate_plan_id"] if cust else None
            parent_plan_id = parent_plan.get(r["customer_id"])
            new_bc, new_sb, new_rc = _recalc_one(
                r["dst_number"], r["billsec"], rate_plan_id, parent_plan_id, r["carrier_id"],
                rates_by_plan, carrier_rates,
            )
            old_bc, old_sb = float(r["buycost"]), float(r["sessionbill"])
            if abs(new_bc - old_bc) > 1e-6 or abs(new_sb - old_sb) > 1e-6:
                to_update.append((r["id"], r["start_ts"], new_bc, new_sb, new_rc))
                affected_dates.add(r["start_ts"].date())
                cid = r["customer_id"]
                d = per_customer.setdefault(cid, {"n": 0, "old_sb": 0.0, "new_sb": 0.0, "old_bc": 0.0, "new_bc": 0.0})
                d["n"] += 1
                d["old_sb"] += old_sb; d["new_sb"] += new_sb
                d["old_bc"] += old_bc; d["new_bc"] += new_bc
        elapsed = time.time() - t0
        print(f"  ...{total:,} CDRs evaluados ({elapsed:.0f}s, {total/max(elapsed,0.001):,.0f}/s) "
              f"— {len(to_update):,} con diferencia hasta ahora")
    scur.close()

    print(f"\nTotal: {total:,} CDRs evaluados en {time.time()-t0:.0f}s.")

    if not to_update:
        print("Nada para corregir en ese rango.")
        return

    names = {cid: c["name"] for cid, c in customers.items()}

    print(f"\n{len(to_update):,} CDRs con diferencia real, en {len(per_customer)} cliente(s):\n")
    for cid, d in per_customer.items():
        delta_sb = d["new_sb"] - d["old_sb"]
        delta_bc = d["new_bc"] - d["old_bc"]
        print(f"  {names.get(cid, cid)} (id={cid}): {d['n']:,} CDRs — "
              f"venta S/{d['old_sb']:.4f} → S/{d['new_sb']:.4f} (delta {delta_sb:+.4f}), "
              f"compra S/{d['old_bc']:.4f} → S/{d['new_bc']:.4f} (delta {delta_bc:+.4f})")

    if not args.apply:
        print(f"\nModo diagnóstico (sin --apply, no se tocó nada).")
        print(f"Fechas a refrescar (cdr_summary_day/month) si se aplica: "
              f"{', '.join(str(d) for d in sorted(affected_dates))}")
        return

    print("\nAplicando correcciones a cdrs...")
    ucur = conn.cursor()
    for cdr_id, start_ts, new_bc, new_sb, new_rc in to_update:
        ucur.execute(
            "UPDATE cdrs SET buycost=%s, sessionbill=%s, reseller_cost=%s WHERE id=%s AND start_ts=%s",
            (new_bc, new_sb, new_rc, cdr_id, start_ts)
        )
    print(f"  ✓ {len(to_update):,} CDRs corregidos (lucro se recalcula solo, es columna generada)")

    print("\nAjustando balance por cliente...")
    for cid, d in per_customer.items():
        delta_sb = round(d["new_sb"] - d["old_sb"], 6)
        if abs(delta_sb) < 1e-6:
            continue
        # delta_sb negativo = se le cobró de más antes → se le devuelve (crédito, +balance)
        credit = round(-delta_sb, 6)
        ucur.execute("UPDATE customers SET balance = balance + %s WHERE id = %s", (credit, cid))
        ucur.execute("SELECT balance FROM customers WHERE id = %s", (cid,))
        new_balance = ucur.fetchone()[0]
        ucur.execute("""
            INSERT INTO balance_transactions (customer_id, type, amount, balance_after, reference)
            VALUES (%s, 'manual', %s, %s, %s)
        """, (cid, credit, new_balance,
              f"Ajuste retroactivo initblock/billingblock ({args.date_from} a {args.date_to}, {d['n']} CDRs)"))
        print(f"  ✓ {names.get(cid, cid)}: balance {credit:+.4f} → nuevo balance {new_balance}")
    ucur.close()

    print("\nRefrescando cdr_summary_day/month...")
    for d in sorted(affected_dates):
        run_summary(conn, d)

    print("\n✓ Recálculo completo.")


if __name__ == "__main__":
    main()
