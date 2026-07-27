#!/usr/bin/env python3
# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Migración manual, única — antes de este cambio, marcar una factura como
pagada (backend/routers/invoices.py::mark_paid()) no tocaba `customers.
balance` para nada: eran dos sistemas totalmente desconectados. Ese balance
solo acumulaba consumo desde el día 1 de la cuenta, sin descontar nunca lo ya
cobrado — un cliente antiguo con facturas pagadas religiosamente igual
mostraba un balance negativo enorme, sin relación con lo que realmente debía.

Este script recorre TODAS las facturas que ya estaban en status='paid' antes
de este cambio (invoices.balance_credited_at IS NULL AND status='paid') y
acredita cada una al balance del cliente correspondiente, exactamente como
ahora hace mark_paid() para facturas nuevas — mismo criterio de
`balance_transactions` (type='invoice_payment') y el mismo campo
`balance_credited_at` como marca de "ya se acreditó", para que correr este
script dos veces sea inofensivo (no vuelve a acreditar una factura ya
marcada).

Dry-run por default (solo reporta, no toca nada). --apply para aplicar de
verdad.

Uso:
    venv/bin/python3 scripts/backfill_invoice_balance_credit.py
    venv/bin/python3 scripts/backfill_invoice_balance_credit.py --apply
"""
import argparse
import os
import sys
from pathlib import Path

import pymysql
from dotenv import load_dotenv

_marker = Path("/etc/voxikam.conf")
if _marker.exists():
    for _line in _marker.read_text().splitlines():
        if _line.startswith("INSTALL_DIR="):
            _install = Path(_line.split("=", 1)[1].strip()); break
    else:
        _install = Path(__file__).parent.parent
else:
    _install = Path(__file__).parent.parent
load_dotenv(_install / "backend" / ".env")


def get_db():
    url = os.getenv("DATABASE_URL_SYNC", "")
    parts = url.replace("mysql+pymysql://", "").split("@")
    user_pass = parts[0].split(":")
    host_port_db = parts[1].split("/")
    host_port = host_port_db[0].split(":")
    return pymysql.connect(
        host=host_port[0],
        port=int(host_port[1]) if len(host_port) > 1 else 3306,
        user=user_pass[0],
        password=user_pass[1],
        database=host_port_db[1],
        charset="utf8mb4",
        autocommit=False,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    conn = get_db()
    cur = conn.cursor(pymysql.cursors.DictCursor)

    cur.execute("""
        SELECT i.id, i.customer_id, i.total, i.period_start, i.period_end, c.name AS customer_name
        FROM invoices i JOIN customers c ON c.id = i.customer_id
        WHERE i.status = 'paid' AND i.balance_credited_at IS NULL
        ORDER BY i.customer_id, i.period_start
    """)
    pending = cur.fetchall()

    if not pending:
        print("Nada para acreditar — todas las facturas pagadas ya están reflejadas en el balance.")
        return

    per_customer: dict = {}
    for inv in pending:
        d = per_customer.setdefault(inv["customer_id"], {"name": inv["customer_name"], "n": 0, "total": 0.0})
        d["n"] += 1
        d["total"] += float(inv["total"])

    print(f"{len(pending):,} factura(s) pagada(s) sin acreditar, en {len(per_customer)} cliente(s):\n")
    for cid, d in per_customer.items():
        print(f"  {d['name']} (id={cid}): {d['n']} factura(s) — total a acreditar S/{d['total']:.2f}")

    if not args.apply:
        print("\nModo diagnóstico (sin --apply, no se tocó nada).")
        return

    print("\nAcreditando...")
    wcur = conn.cursor()
    try:
        for inv in pending:
            amount = float(inv["total"])
            wcur.execute("UPDATE customers SET balance = balance + %s WHERE id = %s",
                          (amount, inv["customer_id"]))
            wcur.execute("SELECT balance FROM customers WHERE id = %s", (inv["customer_id"],))
            new_balance = wcur.fetchone()[0]
            wcur.execute("""
                INSERT INTO balance_transactions (customer_id, type, amount, balance_after, reference, created_by)
                VALUES (%s, 'invoice_payment', %s, %s, %s, 'backfill_invoice_balance_credit.py')
            """, (inv["customer_id"], amount, new_balance, f"Factura #{inv['id']} pagada (backfill retroactivo)"))
            wcur.execute("UPDATE invoices SET balance_credited_at = NOW() WHERE id = %s", (inv["id"],))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        wcur.close()

    print(f"\n✓ {len(pending):,} factura(s) acreditada(s) — el balance de cada cliente ahora descuenta lo ya pagado.")


if __name__ == "__main__":
    main()
