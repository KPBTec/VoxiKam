#!/usr/bin/env python3
# la plataforma anterior — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
cleanup_active_calls.py — Limpia registros zombie de active_calls.

Se llama automáticamente desde el ExecStartPost del servicio Kamailio
para que al reiniciar Kamailio (que pierde todo el estado de diálogos)
el panel no muestre llamadas activas que ya no existen.

También se puede correr manualmente:
  python3 cleanup_active_calls.py           # elimina entradas > 0 min (todas)
  python3 cleanup_active_calls.py 90        # elimina entradas > 90 min
"""
import os
import sys
from pathlib import Path
from datetime import datetime

import pymysql
from dotenv import load_dotenv

_marker = Path("/etc/kaplabilling.conf")
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
        autocommit=True,
    )


def main():
    max_minutes = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"cleanup_active_calls.py — {ts} (max_minutes={max_minutes})")

    conn = get_db()
    try:
        cur = conn.cursor()
        if max_minutes == 0:
            # Llamado desde ExecStartPost de Kamailio: limpiar TODO
            # Kamailio acaba de reiniciar → perdió todos los diálogos → todo es zombie
            cur.execute("DELETE FROM active_calls")
        else:
            cur.execute(
                "DELETE FROM active_calls WHERE TIMESTAMPDIFF(MINUTE, started_at, NOW()) > %s",
                (max_minutes,)
            )
        deleted = cur.rowcount
        if deleted:
            print(f"  ✓ {deleted} registro(s) zombie eliminado(s) de active_calls")
        else:
            print("  ✓ active_calls ya estaba limpia")
        cur.close()
    except Exception as e:
        print(f"  ✗ Error: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
