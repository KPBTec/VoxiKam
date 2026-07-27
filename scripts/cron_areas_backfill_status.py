#!/usr/bin/env python3
# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Cron cada hora — cuenta CDRs contestados sin prefix_matched y cachea el
resultado en `settings` (áreas_backfill_sin_match / areas_backfill_total).
GET /api/admin/areas/backfill-status (backend/routers/areas.py) lee de acá
en vez de correr la cuenta en vivo: sin filtro de fecha posible (necesita
ver TODO el histórico para saber si vale la pena el backfill), así que
sobre cdrs particionada por mes es un scan completo de la tabla — no algo
para correr en cada carga de /areas.
"""
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
        autocommit=True,
    )


def run(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT
            SUM(prefix_matched IS NULL)  AS sin_match,
            COUNT(*)                     AS total
        FROM cdrs
        WHERE disposition = 'ANSWERED' AND customer_id IS NOT NULL
    """)
    sin_match, total = cur.fetchone()
    sin_match = sin_match or 0
    total = total or 0
    print(f"  sin_match={sin_match} total={total}")

    for key, value, desc in [
        ("areas_backfill_sin_match", str(sin_match), "Cache: CDRs contestados sin prefix_matched (ver areas.py)"),
        ("areas_backfill_total",     str(total),     "Cache: total CDRs contestados con customer_id (ver areas.py)"),
    ]:
        cur.execute("""
            INSERT INTO settings (key_name, value, description)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE value = VALUES(value)
        """, (key, value, desc))
    cur.close()


def main():
    print("cron_areas_backfill_status.py — procesando")
    conn = get_db()
    try:
        run(conn)
        print("  ✓ Completado")
    except Exception as e:
        print(f"  ✗ Error: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
