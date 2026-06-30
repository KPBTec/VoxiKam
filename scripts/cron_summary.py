#!/usr/bin/env python3
# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Cron nightly 00:05 — agrega CDRs del día anterior a las tablas de resumen.
Calcula: nbcall, nbcall_fail, sessiontime, buycost, sessionbill, lucro, ASR, ALOC
"""
import os
import sys
from datetime import date, timedelta
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
        autocommit=True,
    )


def run_summary(conn, target_date: date):
    cur = conn.cursor()
    month_str = target_date.strftime("%Y-%m")

    print(f"  Procesando CDRs de {target_date}...")

    # ── Resumen diario por cliente + carrier ──────────────────────────────────
    cur.execute("""
        INSERT INTO cdr_summary_day
            (summary_date, customer_id, carrier_id,
             nbcall, nbcall_fail, sessiontime,
             buycost, sessionbill, lucro, asr, aloc)
        SELECT
            DATE(c.start_ts)            AS summary_date,
            c.customer_id,
            c.carrier_id,
            SUM(c.disposition = 'ANSWERED')     AS nbcall,
            SUM(c.disposition != 'ANSWERED')    AS nbcall_fail,
            SUM(c.billsec)                      AS sessiontime,
            SUM(c.buycost)                      AS buycost,
            SUM(c.sessionbill)                  AS sessionbill,
            SUM(c.sessionbill - c.buycost)      AS lucro,
            ROUND(
                SUM(c.disposition = 'ANSWERED') * 100.0
                / NULLIF(COUNT(*), 0), 2
            )                                   AS asr,
            ROUND(
                SUM(c.billsec) * 1.0
                / NULLIF(SUM(c.disposition = 'ANSWERED'), 0), 2
            )                                   AS aloc
        FROM cdrs c
        WHERE DATE(c.start_ts) = %s
        GROUP BY DATE(c.start_ts), c.customer_id, c.carrier_id
        ON DUPLICATE KEY UPDATE
            nbcall      = VALUES(nbcall),
            nbcall_fail = VALUES(nbcall_fail),
            sessiontime = VALUES(sessiontime),
            buycost     = VALUES(buycost),
            sessionbill = VALUES(sessionbill),
            lucro       = VALUES(lucro),
            asr         = VALUES(asr),
            aloc        = VALUES(aloc)
    """, (target_date,))
    print(f"    ✓ cdr_summary_day: {cur.rowcount} filas")

    # ── Resumen mensual (upsert acumulativo) ──────────────────────────────────
    cur.execute("""
        INSERT INTO cdr_summary_month
            (summary_month, customer_id, carrier_id,
             nbcall, nbcall_fail, sessiontime,
             buycost, sessionbill, lucro, asr, aloc)
        SELECT
            %s                          AS summary_month,
            sd.customer_id,
            sd.carrier_id,
            SUM(sd.nbcall)              AS nbcall,
            SUM(sd.nbcall_fail)         AS nbcall_fail,
            SUM(sd.sessiontime)         AS sessiontime,
            SUM(sd.buycost)             AS buycost,
            SUM(sd.sessionbill)         AS sessionbill,
            SUM(sd.lucro)               AS lucro,
            ROUND(
                SUM(sd.nbcall) * 100.0
                / NULLIF(SUM(sd.nbcall) + SUM(sd.nbcall_fail), 0), 2
            )                           AS asr,
            ROUND(
                SUM(sd.sessiontime) * 1.0
                / NULLIF(SUM(sd.nbcall), 0), 2
            )                           AS aloc
        FROM cdr_summary_day sd
        WHERE LEFT(sd.summary_date, 7) = %s
        GROUP BY sd.customer_id, sd.carrier_id
        ON DUPLICATE KEY UPDATE
            nbcall      = VALUES(nbcall),
            nbcall_fail = VALUES(nbcall_fail),
            sessiontime = VALUES(sessiontime),
            buycost     = VALUES(buycost),
            sessionbill = VALUES(sessionbill),
            lucro       = VALUES(lucro),
            asr         = VALUES(asr),
            aloc        = VALUES(aloc)
    """, (month_str, month_str))
    print(f"    ✓ cdr_summary_month: {cur.rowcount} filas")

    # Limpiar llamadas activas huérfanas (por si Kamailio se reinició)
    cur.execute("""
        DELETE FROM active_calls
        WHERE started_at < NOW() - INTERVAL 4 HOUR
    """)
    if cur.rowcount:
        print(f"    ✓ active_calls huérfanas eliminadas: {cur.rowcount}")

    cur.close()


def main():
    # Por defecto procesa ayer; acepta fecha como argumento
    if len(sys.argv) > 1:
        target = date.fromisoformat(sys.argv[1])
    else:
        target = date.today() - timedelta(days=1)

    print(f"cron_summary.py — {date.today()} — procesando {target}")
    conn = get_db()
    try:
        run_summary(conn, target)
        print("  ✓ Completado")
    except Exception as e:
        print(f"  ✗ Error: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
