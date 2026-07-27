#!/usr/bin/env python3
# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Cron diario 00:10 — mantiene las particiones nativas de cdrs (mensual).

- cdrs: crea particiones de los próximos MESES_ADELANTE meses. Nunca borra
  (el histórico de billing se conserva indefinidamente).

sip_traces ya no vive acá — se migró a ClickHouse (ver
backend/hep_listener.py, backend/routers/traces.py), que maneja su propia
retención con TTL nativo en vez de DROP PARTITION.

Si cdrs todavía no está particionada (instalaciones que venían de antes de
v2.12.0), este script no hace nada sobre ella y lo avisa — requiere correr
scripts/migrate_partitioning.py manualmente durante una ventana de mantenimiento.
"""
import sys
from datetime import date
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

MESES_ADELANTE_CDRS  = 3


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


def _partition_names(conn, table: str) -> set:
    cur = conn.cursor()
    cur.execute("""
        SELECT PARTITION_NAME
        FROM information_schema.PARTITIONS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND PARTITION_NAME IS NOT NULL
    """, (table,))
    names = {r[0] for r in cur.fetchall()}
    cur.close()
    return names


def _add_partition(conn, table: str, name: str, boundary: date) -> None:
    """REORGANIZE p_future para separar `name` (< boundary) y dejar p_future de nuevo al final."""
    cur = conn.cursor()
    cur.execute(f"""
        ALTER TABLE {table} REORGANIZE PARTITION p_future INTO (
            PARTITION {name} VALUES LESS THAN (TO_DAYS('{boundary.isoformat()}')),
            PARTITION p_future VALUES LESS THAN MAXVALUE
        )
    """)
    cur.close()


def maintain_cdrs(conn) -> None:
    existing = _partition_names(conn, "cdrs")
    if "p_future" not in existing:
        print("  ⚠ cdrs: tabla no particionada — omitido (correr scripts/migrate_partitioning.py)")
        return
    today = date.today().replace(day=1)
    for i in range(0, MESES_ADELANTE_CDRS + 1):
        year = today.year + (today.month - 1 + i) // 12
        month = (today.month - 1 + i) % 12 + 1
        name = f"p{year}_{month:02d}"
        if name in existing:
            continue
        boundary = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        _add_partition(conn, "cdrs", name, boundary)
        existing.add(name)
        print(f"  + cdrs: partición {name} creada (< {boundary})")


def main():
    print(f"cron_partitions.py — {date.today()}")
    conn = get_db()
    try:
        maintain_cdrs(conn)
        print("  ✓ Completado")
    except Exception as e:
        print(f"  ✗ Error: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
