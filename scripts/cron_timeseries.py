#!/usr/bin/env python3
# la plataforma anterior — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
cron_timeseries.py — snapshot de llamadas contestadas por minuto.

Lee el snapshot que cron_dlg_stats.py actualiza cada 10s en:
  /var/lib/kaplabilling/live_snapshot.json

Usa DATE_FORMAT(NOW(),...) de MySQL para el timestamp — así el backend
que también usa NOW() siempre encuentra los datos sin importar la zona
horaria del servidor Python.

Retención: 25 horas (auto-purge).
"""
import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pymysql
from dotenv import load_dotenv

_marker = Path("/etc/kaplabilling.conf")
if _marker.exists():
    for _line in _marker.read_text().splitlines():
        if _line.startswith("INSTALL_DIR="):
            _install = Path(_line.split("=", 1)[1].strip()); break
    else:
        _install = Path(__file__).parent.parent
else:
    _install = Path(__file__).parent.parent
load_dotenv(_install / "backend" / ".env")

SNAPSHOT_FILE = Path("/var/lib/kaplabilling/live_snapshot.json")


def get_db():
    url       = os.getenv("DATABASE_URL_SYNC", "")
    parts     = url.replace("mysql+pymysql://", "").split("@")
    user_pass = parts[0].split(":")
    host_db   = parts[1].split("/")
    host_port = host_db[0].split(":")
    return pymysql.connect(
        host=host_port[0],
        port=int(host_port[1]) if len(host_port) > 1 else 3306,
        user=user_pass[0],
        password=user_pass[1],
        database=host_db[1],
        charset="utf8mb4",
        autocommit=False,
    )


def run(conn):
    # ── 1) Leer snapshot (generado por cron_dlg_stats.py cada 10s) ──────────
    try:
        snap = json.loads(SNAPSHOT_FILE.read_text())
    except Exception as e:
        print(f"  ⚠ no se pudo leer snapshot: {e}")
        return

    # resumen_por_prefijo: [{prefijo, llamadas_activas, timbrando, total}]
    por_pfx = snap.get("resumen_por_prefijo", [])
    if not por_pfx:
        ts_snap = snap.get("ts", "?")
        print(f"  ✓ {ts_snap}: sin llamadas activas en snapshot")
        return

    # ── 2) Resolver prefijo → customer_id ───────────────────────────────────
    cur = conn.cursor()
    cur.execute(
        "SELECT id, techprefix FROM customers "
        "WHERE techprefix IS NOT NULL AND techprefix != ''"
    )
    prefix_map = {row[1]: row[0] for row in cur.fetchall()}

    # ── 3) Insertar usando NOW() de MySQL (sin depender de la TZ del servidor) ─
    rows_saved = 0
    total_calls = 0
    for entry in por_pfx:
        pfx     = entry.get("prefijo", "")
        count   = entry.get("llamadas_activas", 0)  # state=4 confirmadas
        cust_id = prefix_map.get(pfx)
        if not cust_id or not count:
            continue

        cur.execute("""
            INSERT INTO calls_timeseries
                (ts, customer_id, carrier_id, call_count, answered_count, failed_count)
            VALUES (DATE_FORMAT(NOW(), %s), %s, 0, %s, %s, 0)
            ON DUPLICATE KEY UPDATE
                call_count     = VALUES(call_count),
                answered_count = VALUES(answered_count)
        """, ("%Y-%m-%d %H:%i:00", cust_id, count, count))
        rows_saved  += 1
        total_calls += count

    # ── 4) Purgar registros > 25 horas ──────────────────────────────────────
    cur.execute("DELETE FROM calls_timeseries WHERE ts < NOW() - INTERVAL 25 HOUR")
    purged = cur.rowcount

    conn.commit()
    cur.close()

    ts_snap = snap.get("ts", "?")
    print(f"  ✓ {ts_snap}: {total_calls} contestadas en {rows_saved} cliente(s)"
          + (f" — purge: {purged}" if purged else ""))


def main():
    print(f"cron_timeseries.py — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    conn = get_db()
    try:
        run(conn)
    except Exception as e:
        print(f"  ✗ Error: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
