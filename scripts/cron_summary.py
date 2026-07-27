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
    # disposition != 'RESTART_ORPHANED' (v2.26.0): esas llamadas sí se
    # contestaron pero nunca se confirmó si se facturaron (Kamailio se
    # reinició antes del BYE) — no son "contestada" ni "fallida", se sacan
    # del ASR entero para no distorsionarlo en ningún sentido. Mismo criterio
    # en backend/routers/reports.py.
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
          AND c.disposition != 'RESTART_ORPHANED'
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

    # ── Margen de reseller (tabla separada — ver comentario en db/schema.sql) ──
    # Mismo filtro exacto que reseller.py::dashboard() usa hoy en vivo:
    # disposition='ANSWERED' AND reseller_cost IS NOT NULL. reseller_cost solo
    # existe para sub-clientes de un reseller con billsec>0 (cdrs.py::ingest_cdr),
    # por eso esto NO puede vivir como columna extra en cdr_summary_day (ese
    # sum incluye llamadas fallidas, inflaría el margen).
    cur.execute("""
        INSERT INTO cdr_summary_day_reseller
            (summary_date, customer_id, nbcall, revenue, cost, margin)
        SELECT
            DATE(c.start_ts)                        AS summary_date,
            c.customer_id,
            COUNT(*)                                AS nbcall,
            ROUND(SUM(c.sessionbill), 4)             AS revenue,
            ROUND(SUM(c.reseller_cost), 4)           AS cost,
            ROUND(SUM(c.sessionbill - c.reseller_cost), 4) AS margin
        FROM cdrs c
        WHERE DATE(c.start_ts) = %s
          AND c.disposition = 'ANSWERED'
          AND c.reseller_cost IS NOT NULL
        GROUP BY DATE(c.start_ts), c.customer_id
        ON DUPLICATE KEY UPDATE
            nbcall  = VALUES(nbcall),
            revenue = VALUES(revenue),
            cost    = VALUES(cost),
            margin  = VALUES(margin)
    """, (target_date,))
    print(f"    ✓ cdr_summary_day_reseller: {cur.rowcount} filas")

    # ── Consumo por área, por cliente (tabla separada — ver comentario en db/schema.sql) ──
    # Clave = (día, cliente, prefix_matched), NUNCA el nombre de área ya
    # resuelto — se resuelve con JOIN a prefixes al leer (areas.py::
    # area_report() / portal.py::my_report_by_area()), así un rename de área
    # se refleja al instante en todo el histórico sin recalcular esta tabla.
    # nbcall_fail/pdd_ms_sum nuevos — para ASR/ACD/PDD (pedido explícito,
    # comparando contra lo que muestra un competidor real). disposition
    # NOT IN ('ANSWERED','RESTART_ORPHANED') = fallida real, mismo criterio
    # de exclusión de RESTART_ORPHANED que el resto de este script.
    cur.execute("""
        INSERT INTO cdr_summary_day_area
            (summary_date, customer_id, prefix_matched, nbcall, nbcall_fail,
             sessiontime, pdd_ms_sum, buycost, sessionbill, lucro)
        SELECT
            DATE(c.start_ts)                    AS summary_date,
            c.customer_id,
            COALESCE(c.prefix_matched, '')       AS prefix_matched,
            SUM(c.disposition = 'ANSWERED')      AS nbcall,
            SUM(c.disposition NOT IN ('ANSWERED', 'RESTART_ORPHANED')) AS nbcall_fail,
            SUM(CASE WHEN c.disposition = 'ANSWERED' THEN c.billsec ELSE 0 END) AS sessiontime,
            SUM(CASE WHEN c.answer_ts IS NOT NULL
                     THEN TIMESTAMPDIFF(MICROSECOND, c.start_ts, c.answer_ts) / 1000
                     ELSE 0 END)                 AS pdd_ms_sum,
            ROUND(SUM(c.buycost), 4)             AS buycost,
            ROUND(SUM(c.sessionbill), 4)         AS sessionbill,
            ROUND(SUM(c.sessionbill - c.buycost), 4) AS lucro
        FROM cdrs c
        WHERE DATE(c.start_ts) = %s
          AND c.customer_id IS NOT NULL
          AND c.disposition != 'RESTART_ORPHANED'
        GROUP BY DATE(c.start_ts), c.customer_id, COALESCE(c.prefix_matched, '')
        ON DUPLICATE KEY UPDATE
            nbcall      = VALUES(nbcall),
            nbcall_fail = VALUES(nbcall_fail),
            sessiontime = VALUES(sessiontime),
            pdd_ms_sum  = VALUES(pdd_ms_sum),
            buycost     = VALUES(buycost),
            sessionbill = VALUES(sessionbill),
            lucro       = VALUES(lucro)
    """, (target_date,))
    print(f"    ✓ cdr_summary_day_area: {cur.rowcount} filas")

    # ── Consumo por campaña propia del cliente (portal.py::my_campaigns()) ──
    # techprefix acá es el prefijo del marcador del CLIENTE (ej. Vicidial),
    # no el destino — mismo filtro (disposition != 'RESTART_ORPHANED') que
    # ya usaba my_campaigns() en vivo.
    cur.execute("""
        INSERT INTO cdr_summary_day_campaign
            (summary_date, customer_id, techprefix, nbcall, sessiontime, sessionbill)
        SELECT
            DATE(c.start_ts)                    AS summary_date,
            c.customer_id,
            COALESCE(c.techprefix, '')           AS techprefix,
            SUM(c.disposition = 'ANSWERED')      AS nbcall,
            SUM(CASE WHEN c.disposition = 'ANSWERED' THEN c.billsec ELSE 0 END) AS sessiontime,
            ROUND(SUM(c.sessionbill), 4)         AS sessionbill
        FROM cdrs c
        WHERE DATE(c.start_ts) = %s
          AND c.customer_id IS NOT NULL
          AND c.disposition != 'RESTART_ORPHANED'
        GROUP BY DATE(c.start_ts), c.customer_id, COALESCE(c.techprefix, '')
        ON DUPLICATE KEY UPDATE
            nbcall      = VALUES(nbcall),
            sessiontime = VALUES(sessiontime),
            sessionbill = VALUES(sessionbill)
    """, (target_date,))
    print(f"    ✓ cdr_summary_day_campaign: {cur.rowcount} filas")

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
