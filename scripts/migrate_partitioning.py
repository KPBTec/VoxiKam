#!/usr/bin/env python3
# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Migración manual, única, para instalaciones que vienen de antes de v2.12.0:
convierte cdrs y sip_traces (sin particionar) al esquema particionado por
fecha que trae db/schema.sql desde v2.12.0.

NO se ejecuta automáticamente desde deploy.sh — a propósito. Un ALTER TABLE
que agrega particionado reconstruye la tabla completa (copia todas las filas),
lo cual en una tabla de CDRs/trazas con tráfico real puede tardar minutos u
horas y bloquear escrituras mientras corre. Debe correrse en una ventana de
mantenimiento, con el operador presente.

Uso:
    venv/bin/python3 scripts/migrate_partitioning.py            # solo diagnóstico
    venv/bin/python3 scripts/migrate_partitioning.py --yes      # aplica
"""
import sys
import time
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


TABLES = {
    "cdrs": {
        "date_col": "start_ts",
        "pk_alter": "DROP PRIMARY KEY, ADD PRIMARY KEY (id, start_ts)",
    },
    "sip_traces": {
        "date_col": "captured_at",
        "pk_alter": "DROP PRIMARY KEY, ADD PRIMARY KEY (id, captured_at)",
    },
}


def is_partitioned(conn, table: str) -> bool:
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM information_schema.PARTITIONS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND PARTITION_NAME IS NOT NULL
    """, (table,))
    (n,) = cur.fetchone()
    cur.close()
    return n > 0


def row_count(conn, table: str) -> int:
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    (n,) = cur.fetchone()
    cur.close()
    return n


def migrate_table(conn, table: str, cfg: dict) -> None:
    print(f"\n→ {table}: aplicando ALTER TABLE (reconstruye la tabla completa, puede tardar)...")
    t0 = time.time()
    cur = conn.cursor()
    cur.execute(f"""
        ALTER TABLE {table}
          {cfg['pk_alter']}
        PARTITION BY RANGE (TO_DAYS({cfg['date_col']})) (
            PARTITION p_start  VALUES LESS THAN (TO_DAYS('2000-01-01')),
            PARTITION p_future VALUES LESS THAN MAXVALUE
        )
    """)
    cur.close()
    print(f"  ✓ {table} particionado en {time.time() - t0:.1f}s")


def main():
    apply = "--yes" in sys.argv
    conn = get_db()

    print("Estado actual:")
    pending = []
    for table in TABLES:
        if is_partitioned(conn, table):
            print(f"  ✓ {table}: ya particionado — nada que hacer")
            continue
        n = row_count(conn, table)
        print(f"  ⚠ {table}: sin particionar — {n:,} filas")
        pending.append(table)

    if not pending:
        print("\nNada pendiente.")
        return

    if not apply:
        print(
            "\nModo diagnóstico (sin --yes, no se aplicó nada).\n"
            "Esto es un ALTER TABLE que reconstruye la tabla completa: en tablas grandes\n"
            "puede tardar minutos/horas y bloquear escrituras mientras corre. Ejecutar en\n"
            "ventana de mantenimiento:\n"
            "  venv/bin/python3 scripts/migrate_partitioning.py --yes"
        )
        return

    for table in pending:
        migrate_table(conn, table, TABLES[table])

    print("\n✓ Migración completa. scripts/cron_partitions.py ya puede mantener las particiones.")
    conn.close()


if __name__ == "__main__":
    main()
