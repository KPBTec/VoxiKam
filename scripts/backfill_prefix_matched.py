#!/usr/bin/env python3
# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Backfill manual, único: recalcula cdrs.prefix_matched para CDRs históricos.

Hasta v2.13.0, prefix_matched se llenaba con un campo suelto del payload de
Kamailio que no necesariamente correspondía a la tarifa realmente aplicada —
en la práctica quedaba NULL o inconsistente para casi todo el histórico. El
reporte de Áreas (rentabilidad por área) depende de que este campo sea
confiable, así que sin este backfill TODO el histórico previo a v2.13.0
aparece agrupado en "Sin área", aunque las áreas estén bien configuradas.

Recalcula con la MISMA lógica de longest-prefix-match que ya usa
routers/cdrs.py::ingest_cdr() al tarifar — usa el rate_plan_id del cliente y
los prefijos/tarifas configurados HOY (no hay forma de saber qué tarifas
existían en el momento exacto de cada llamada vieja, pero para agrupar por
área alcanza con la definición de prefijo actual, que rara vez cambia).

Solo toca prefix_matched — nunca buycost/sessionbill/lucro, así que no
afecta nada ya facturado.

Además (agregado junto con el trigger trg_cdrs_prefix_matched, ver
db/schema.sql): reconstruye cdr_summary_day_area día por día para todo el
histórico. Sin esto, el UPDATE de arriba corrige cdrs.prefix_matched pero el
reporte de Áreas para "días completados" (routers/areas.py::
_area_report_rows(), rama day_filters) sigue leyendo cdr_summary_day_area —
una tabla de resumen nocturna (scripts/cron_summary.py) que YA quedó grabada
con el prefix_matched viejo/NULL antes de este backfill y nunca se
retocaba sola. Resultado real visto en producción: el contador de "CDRs sin
área" (GET /admin/areas/backfill-status, que sí lee cdrs en vivo) bajaba a
casi cero, pero el reporte por período seguía mostrando miles de llamadas en
"Sin área" para meses ya cerrados — dos fuentes de datos distintas, una
arreglada y la otra no. Reusa la MISMA query INSERT...ON DUPLICATE KEY
UPDATE que cron_summary.py corre cada noche para un solo día — acá, en
loop, para cada día que ya tiene CDRs, así que es idempotente y segura de
reintentar si se corta a la mitad.

Uso:
    venv/bin/python3 scripts/backfill_prefix_matched.py            # solo diagnóstico
    venv/bin/python3 scripts/backfill_prefix_matched.py --yes      # aplica
"""
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pymysql
from dotenv import load_dotenv
import os

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


def _rebuild_area_summary(cur):
    """
    Reconstruye cdr_summary_day_area para cada día con CDRs, desde el más
    viejo hasta ayer (hoy lo cubre la rama "en vivo" de _area_report_rows(),
    no la tabla de resumen). Mismo bloque exacto que scripts/cron_summary.py
    ::run_summary(), solo que en loop sobre todo el histórico en vez de un
    día puntual.
    """
    cur.execute("""
        SELECT MIN(DATE(start_ts)) FROM cdrs
        WHERE customer_id IS NOT NULL AND disposition != 'RESTART_ORPHANED'
    """)
    (min_date,) = cur.fetchone()
    if min_date is None:
        print("Sin CDRs con customer_id — nada que reconstruir en cdr_summary_day_area")
        return

    yesterday = date.today() - timedelta(days=1)
    if min_date > yesterday:
        print("Sin días completados todavía (todo el histórico es de hoy) — nada que reconstruir")
        return

    total_days = (yesterday - min_date).days + 1
    print(f"Reconstruyendo cdr_summary_day_area: {min_date} → {yesterday} ({total_days} día(s))...")
    t0 = time.time()
    d = min_date
    n = 0
    while d <= yesterday:
        # DELETE antes de re-insertar: el prefix_matched viejo pudo dejar
        # buckets (ej. '' = sin match) que ya no le corresponden a ningún CDR
        # de este día tras el UPDATE de arriba. Sin este DELETE, INSERT ...
        # ON DUPLICATE KEY UPDATE solo pisa la fila del bucket NUEVO y deja la
        # fila del bucket VIEJO como fantasma — el reporte termina sumando
        # las llamadas DOS veces (una en el bucket viejo, otra en el nuevo).
        # Confirmado reproduciendo el caso exacto contra MariaDB real antes
        # de agregar esta línea: sin DELETE, un día con 2 llamadas quedaba
        # mostrando 4.
        cur.execute("DELETE FROM cdr_summary_day_area WHERE summary_date = %s", (d,))
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
        """, (d,))
        n += 1
        if n % 30 == 0:
            print(f"  ... {d} ({n}/{total_days})")
        d += timedelta(days=1)
    print(f"✓ cdr_summary_day_area reconstruida — {n} día(s) en {time.time() - t0:.1f}s")


def main():
    apply = "--yes" in sys.argv
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*) FROM cdrs
        WHERE disposition = 'ANSWERED' AND customer_id IS NOT NULL
    """)
    (total,) = cur.fetchone()
    print(f"CDRs contestados a recalcular: {total:,}")

    if not apply:
        print(
            "\nModo diagnóstico (sin --yes, no se aplicó nada).\n"
            "Este UPDATE es liviano (solo toca prefix_matched, no buycost/sessionbill) pero\n"
            "recorre todo el histórico — en tablas grandes puede tardar. Ejecutar con:\n"
            "  venv/bin/python3 scripts/backfill_prefix_matched.py --yes"
        )
        return

    print("Aplicando...")
    t0 = time.time()
    cur.execute("""
        UPDATE cdrs c
        JOIN customers cu ON cu.id = c.customer_id
        SET c.prefix_matched = (
            SELECT p.prefix
            FROM rates r JOIN prefixes p ON r.prefix_id = p.id
            WHERE r.rate_plan_id = cu.rate_plan_id
              AND c.dst_number LIKE CONCAT(p.prefix, '%')
            ORDER BY LENGTH(p.prefix) DESC LIMIT 1
        )
        WHERE c.disposition = 'ANSWERED' AND c.customer_id IS NOT NULL
    """)
    affected = cur.rowcount
    print(f"✓ {affected:,} filas actualizadas en {time.time() - t0:.1f}s")

    _rebuild_area_summary(cur)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
