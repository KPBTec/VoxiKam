#!/usr/bin/env python3
# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Cron nocturno (o disparado a mano desde el panel Sincronización externa) —
copia cdrs de forma incremental hacia una DB externa (mysql/postgres/sqlserver)
configurada en external_sync_config. Un solo destino a la vez.

Solo lee cdrs de la DB local (SELECT ... WHERE id > cursor ORDER BY id LIMIT
BATCH_SIZE) — nunca borra ni modifica nada local, y el batch pequeño evita
competir con el billing worker o el tráfico en curso.

pyodbc (SQL Server) se importa solo si hace falta: no es una dependencia dura
del proyecto porque requiere unixODBC + el driver de Microsoft instalados a
nivel de sistema operativo — si faltan, deploy.sh no debe romperse por eso.

Uso:
    venv/bin/python3 scripts/cron_external_sync.py            # sync normal
    venv/bin/python3 scripts/cron_external_sync.py --test     # solo prueba la conexión al destino
"""
import sys
from datetime import datetime
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

BATCH_SIZE = 500

CDR_COLUMNS = [
    "id", "call_id", "customer_id", "carrier_id", "src_number", "dst_number",
    "start_ts", "billsec", "buycost", "sessionbill", "disposition", "hangup_cause",
]

DDL = {
    "mysql": """
        CREATE TABLE IF NOT EXISTS cdrs (
            id BIGINT PRIMARY KEY, call_id VARCHAR(120), customer_id INT, carrier_id INT,
            src_number VARCHAR(40), dst_number VARCHAR(40), start_ts DATETIME(3),
            billsec INT, buycost DECIMAL(10,6), sessionbill DECIMAL(10,6),
            disposition VARCHAR(20), hangup_cause VARCHAR(30)
        )
    """,
    "postgres": """
        CREATE TABLE IF NOT EXISTS cdrs (
            id BIGINT PRIMARY KEY, call_id VARCHAR(120), customer_id INT, carrier_id INT,
            src_number VARCHAR(40), dst_number VARCHAR(40), start_ts TIMESTAMP,
            billsec INT, buycost NUMERIC(10,6), sessionbill NUMERIC(10,6),
            disposition VARCHAR(20), hangup_cause VARCHAR(30)
        )
    """,
    "sqlserver": """
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='cdrs' AND xtype='U')
        CREATE TABLE cdrs (
            id BIGINT PRIMARY KEY, call_id VARCHAR(120), customer_id INT, carrier_id INT,
            src_number VARCHAR(40), dst_number VARCHAR(40), start_ts DATETIME2,
            billsec INT, buycost DECIMAL(10,6), sessionbill DECIMAL(10,6),
            disposition VARCHAR(20), hangup_cause VARCHAR(30)
        )
    """,
}


def get_local_db():
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


def get_config(conn) -> dict:
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM external_sync_config WHERE id = 1")
    cfg = cur.fetchone()
    cur.close()
    return cfg


def connect_target(cfg: dict):
    engine = cfg["engine"]
    if engine == "mysql":
        return pymysql.connect(
            host=cfg["host"], port=cfg["port"], user=cfg["db_user"],
            password=cfg["db_pass"], database=cfg["db_name"],
            charset="utf8mb4", autocommit=False, connect_timeout=10,
        )
    if engine == "postgres":
        import psycopg2
        return psycopg2.connect(
            host=cfg["host"], port=cfg["port"], user=cfg["db_user"],
            password=cfg["db_pass"], dbname=cfg["db_name"], connect_timeout=10,
        )
    if engine == "sqlserver":
        try:
            import pyodbc
        except ImportError:
            raise RuntimeError(
                "pyodbc no está instalado. En el servidor: "
                "sudo apt install unixodbc unixodbc-dev, instalar el driver ODBC de Microsoft "
                "(msodbcsql18), luego venv/bin/pip install pyodbc"
            )
        conn_str = (
            f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={cfg['host']},{cfg['port']};"
            f"DATABASE={cfg['db_name']};UID={cfg['db_user']};PWD={cfg['db_pass']};"
            "TrustServerCertificate=yes"
        )
        return pyodbc.connect(conn_str, timeout=10)
    raise ValueError(f"engine desconocido: {engine}")


def _placeholder(engine: str) -> str:
    return "?" if engine == "sqlserver" else "%s"


def sync_batches(conn_local, cfg: dict) -> tuple[int, int, int, list[str]]:
    """Retorna (cursor_id, rows_synced, rows_failed, sample_errors).

    rows_synced cuenta INSERTs que realmente tuvieron éxito en el destino —
    antes contaba filas leídas de cdrs, sin importar si el INSERT fallaba.
    Un error de "entrada duplicada" (fila ya existía por un reintento tras
    un corte a mitad de batch) se tolera sin contar como fallo real — pero
    CUALQUIER otro error (timeout, columna incompatible, etc.) ahora se
    cuenta y se reporta en vez de tragarse en silencio."""
    target = connect_target(cfg)
    target_cur = target.cursor()
    target_cur.execute(DDL[cfg["engine"]])
    target.commit()

    ph = _placeholder(cfg["engine"])
    insert_sql = (
        f"INSERT INTO cdrs ({', '.join(CDR_COLUMNS)}) VALUES ({', '.join([ph] * len(CDR_COLUMNS))})"
    )

    cursor_id = cfg["last_sync_id"] or 0
    total_synced = 0
    total_failed = 0
    sample_errors: list[str] = []
    local_cur = conn_local.cursor()
    while True:
        local_cur.execute(f"""
            SELECT {', '.join(CDR_COLUMNS)}
            FROM cdrs WHERE id > %s ORDER BY id LIMIT %s
        """, (cursor_id, BATCH_SIZE))
        rows = local_cur.fetchall()
        if not rows:
            break
        for row in rows:
            try:
                target_cur.execute(insert_sql, row)
                total_synced += 1
            except Exception as e:
                msg = str(e).lower()
                if "duplicate" in msg or "unique" in msg or "primary key" in msg:
                    total_synced += 1  # fila ya existía — reintento tras un corte, no es un fallo real
                    continue
                total_failed += 1
                if len(sample_errors) < 5:
                    sample_errors.append(f"id={row[0]}: {e}")
        target.commit()
        cursor_id = rows[-1][0]
        if len(rows) < BATCH_SIZE:
            break
    local_cur.close()
    target_cur.close()
    target.close()
    return cursor_id, total_synced, total_failed, sample_errors


def main():
    test_only = "--test" in sys.argv
    conn = get_local_db()
    cfg = get_config(conn)

    if not cfg or not cfg["host"]:
        print("Sin configuración de sincronización externa — nada que hacer")
        return

    if test_only:
        try:
            t = connect_target(cfg)
            t.close()
            print("✓ Conexión OK")
        except Exception as e:
            print(f"✗ Error de conexión: {e}")
            sys.exit(1)
        return

    if not cfg["enabled"]:
        print("Sincronización externa deshabilitada — nada que hacer")
        return

    started = datetime.now()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO external_sync_log (started_at, status) VALUES (%s, 'running')", (started,)
    )
    log_id = cur.lastrowid

    print(f"cron_external_sync.py — {started} — destino {cfg['engine']}://{cfg['host']}")
    try:
        new_cursor, total, failed, sample_errors = sync_batches(conn, cfg)
        status = "partial" if failed else "ok"
        detail = "; ".join(sample_errors) if sample_errors else None
        cur.execute("""
            UPDATE external_sync_config
            SET last_sync_at=%s, last_sync_id=%s, last_status=%s, last_error=%s
            WHERE id=1
        """, (datetime.now(), new_cursor, status, detail))
        cur.execute("""
            UPDATE external_sync_log
            SET finished_at=%s, rows_synced=%s, rows_failed=%s, status=%s, detail=%s
            WHERE id=%s
        """, (datetime.now(), total, failed, status, detail, log_id))
        if failed:
            print(f"  ⚠ {total} sincronizados, {failed} FALLARON (cursor → {new_cursor}) — ver detail en external_sync_log")
        else:
            print(f"  ✓ {total} CDRs sincronizados (cursor → {new_cursor})")
    except Exception as e:
        err = str(e)[:2000]
        cur.execute(
            "UPDATE external_sync_config SET last_status='error', last_error=%s WHERE id=1", (err,)
        )
        cur.execute("""
            UPDATE external_sync_log SET finished_at=%s, status='error', detail=%s WHERE id=%s
        """, (datetime.now(), err, log_id))
        print(f"  ✗ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
