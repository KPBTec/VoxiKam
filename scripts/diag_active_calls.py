#!/usr/bin/env python3
# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
diag_active_calls.py — Solo lectura. Compara active_calls contra cdrs para
saber si las llamadas "zombie" (siguen en active_calls pero Kamailio ya no
las ve activas en dlg.briefing) llegaron a facturarse o no.

No borra nada — es diagnóstico. El cleanup real es scripts/cleanup_active_calls.py.

Uso:
  python3 diag_active_calls.py
"""
import os
from pathlib import Path

import pymysql
from dotenv import load_dotenv

_marker = Path("/etc/voxikam.conf")
if _marker.exists():
    for _line in _marker.read_text().splitlines():
        if _line.startswith("INSTALL_DIR="):
            _install = Path(_line.split("=", 1)[1].strip())
            break
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
        cursorclass=pymysql.cursors.DictCursor,
    )


def main():
    conn = get_db()
    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT ac.call_id, ac.customer_id, cu.name AS customer_name,
                   ac.src_number, ac.dst_number, ac.started_at,
                   TIMESTAMPDIFF(MINUTE, ac.started_at, NOW()) AS minutos_activa
            FROM active_calls ac
            LEFT JOIN customers cu ON ac.customer_id = cu.id
            ORDER BY ac.started_at
        """)
        rows = cur.fetchall()

        if not rows:
            print("active_calls está vacía — nada que diagnosticar.")
            return

        print(f"{len(rows)} fila(s) en active_calls:\n")

        call_ids = [r["call_id"] for r in rows]
        placeholders = ",".join(["%s"] * len(call_ids))
        cur.execute(f"""
            SELECT call_id, start_ts, sessionbill, disposition
            FROM cdrs
            WHERE call_id IN ({placeholders})
        """, call_ids)
        cdr_by_callid = {r["call_id"]: r for r in cur.fetchall()}

        for r in rows:
            cdr = cdr_by_callid.get(r["call_id"])
            veredicto = (
                f"✓ FACTURADA — sessionbill={cdr['sessionbill']} disposition={cdr['disposition']}"
                if cdr else
                "✗ SIN CDR — no se facturó, revisar por qué"
            )
            print(f"call_id={r['call_id']}")
            print(f"  cliente:   {r['customer_name'] or r['customer_id']}")
            print(f"  origen→destino: {r['src_number']} → {r['dst_number']}")
            print(f"  activa hace: {r['minutos_activa']} min (started_at={r['started_at']})")
            print(f"  {veredicto}\n")

        cur.close()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
