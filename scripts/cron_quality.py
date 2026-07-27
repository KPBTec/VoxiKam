#!/usr/bin/env python3
# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
cron_quality.py — ASR Dashboard: resumen de calidad por hora y cliente.

Ejecutar cada 1 minuto via cron.
Agrega la hora actual con UPSERT desde cdrs + cdrs_failed.
Retención: 35 días (auto-purge).

Métricas por (ts_hour, customer_id):
  answered    = llamadas contestadas (cdrs)
  short_calls = contestadas con billsec < 5s (probable buzón/voicemail)
  c_487       = Request Terminated (predictivo cancela cuando alguien contesta)
  c_486       = Busy
  c_404       = Not Found (número no existe en carrier)
  c_503       = Service Unavailable (carrier caído)
  c_other     = otros códigos de error
  total       = answered + todos los fallidos
"""
import os
from datetime import datetime, timedelta
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
    cur = conn.cursor()
    now      = datetime.now()
    ts_hour  = now.replace(minute=0, second=0, microsecond=0)
    ts_str   = ts_hour.strftime("%Y-%m-%d %H:%M:%S")
    prev_str = (ts_hour - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")

    # ── Contestadas de la hora actual ────────────────────────────────────────
    # disposition = 'ANSWERED' explícito — antes esto no filtraba nada,
    # contaba CUALQUIER fila de cdrs como "contestada" (incluidas NO_ANSWER y,
    # desde v2.26.0, RESTART_ORPHANED — llamadas que sí se atendieron pero
    # nunca se confirmó que se facturaran). Mismo criterio que
    # backend/routers/reports.py y scripts/cron_summary.py.
    cur.execute("""
        SELECT
            customer_id,
            COUNT(*)          AS answered,
            SUM(billsec < 5)  AS short_calls
        FROM cdrs
        WHERE start_ts >= %s AND start_ts < %s
          AND customer_id IS NOT NULL
          AND disposition = 'ANSWERED'
        GROUP BY customer_id
    """, (ts_str, (ts_hour + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")))
    answered_rows = {r[0]: {"answered": r[1], "short_calls": r[2] or 0}
                     for r in cur.fetchall()}

    # ── Fallidas de la hora actual ───────────────────────────────────────────
    cur.execute("""
        SELECT
            customer_id,
            SUM(sip_code = 487)                            AS c_487,
            SUM(sip_code = 486)                            AS c_486,
            SUM(sip_code = 404)                            AS c_404,
            SUM(sip_code = 503)                            AS c_503,
            SUM(sip_code NOT IN (487, 486, 404, 503))      AS c_other,
            COUNT(*)                                        AS failed_total
        FROM cdrs_failed
        WHERE start_ts >= %s AND start_ts < %s
          AND customer_id IS NOT NULL
        GROUP BY customer_id
    """, (ts_str, (ts_hour + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")))
    failed_rows = {r[0]: {
        "c_487": r[1] or 0, "c_486": r[2] or 0,
        "c_404": r[3] or 0, "c_503": r[4] or 0,
        "c_other": r[5] or 0, "failed_total": r[6] or 0,
    } for r in cur.fetchall()}

    # ── Merge por customer_id y upsert ───────────────────────────────────────
    all_customers = set(answered_rows) | set(failed_rows)
    rows_saved = 0

    for cid in all_customers:
        a = answered_rows.get(cid, {"answered": 0, "short_calls": 0})
        f = failed_rows.get(cid,   {"c_487": 0, "c_486": 0, "c_404": 0,
                                     "c_503": 0, "c_other": 0, "failed_total": 0})
        total = a["answered"] + f["failed_total"]

        cur.execute("""
            INSERT INTO traffic_quality_hourly
                (ts_hour, customer_id, total, answered, short_calls,
                 c_487, c_486, c_404, c_503, c_other)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                total       = VALUES(total),
                answered    = VALUES(answered),
                short_calls = VALUES(short_calls),
                c_487       = VALUES(c_487),
                c_486       = VALUES(c_486),
                c_404       = VALUES(c_404),
                c_503       = VALUES(c_503),
                c_other     = VALUES(c_other)
        """, (ts_str, cid, total, a["answered"], a["short_calls"],
              f["c_487"], f["c_486"], f["c_404"], f["c_503"], f["c_other"]))
        rows_saved += 1

    # ── Purgar datos > 35 días ───────────────────────────────────────────────
    cur.execute("DELETE FROM traffic_quality_hourly WHERE ts_hour < NOW() - INTERVAL 35 DAY")
    purged = cur.rowcount

    conn.commit()
    cur.close()

    print(f"  ✓ {ts_str}: {len(all_customers)} clientes actualizados"
          + (f" — purge: {purged}" if purged else ""))


def main():
    print(f"cron_quality.py — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
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
