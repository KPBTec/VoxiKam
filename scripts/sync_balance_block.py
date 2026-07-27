#!/usr/bin/env python3
# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Bloqueo de llamadas NUEVAS para clientes prepago con saldo agotado.

Lee DB → reemplaza el contenido de la tabla balance_block_map (respalda el
htable "balance_block" de Kamailio, ver templates/kamailio.cfg.j2) con un
techprefix por cada cliente prepago con balance<=0 (principal + prefijos de
campaña) → dispara `kamcmd htable.reload balance_block`.

No corta una llamada ya en curso — el saldo real recién se descuenta al
colgar (ver backend/main.py::_billing_worker(), hasta ~30s de lag propio).
Esto solo evita que se ORIGINE una llamada nueva una vez que el saldo ya
está en 0 o negativo. Postpago nunca aparece acá.

Modo diagnóstico por default (sin --apply): imprime qué clientes/prefijos
quedarían bloqueados AHORA MISMO sin tocar la tabla ni Kamailio — correr
así primero contra una DB real antes de agregar este script al cron, para
saber si ya hay clientes que quedarían bloqueados de entrada (ej. saldo
negativo por lag de facturación, no por falta de pago real).

Uso:
    venv/bin/python3 scripts/sync_balance_block.py            # diagnóstico
    venv/bin/python3 scripts/sync_balance_block.py --apply    # aplica + recarga Kamailio
"""
import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pymysql
from dotenv import load_dotenv

_marker = Path("/etc/voxikam.conf")
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
    )


def fetch_blocked(conn) -> list[dict]:
    """
    Techprefix (principal + campaña) de todo cliente prepago con balance<=0.
    Sin filtro por status: un cliente ya suspendido no tiene techprefix en
    el htable "techmap" de todas formas (ver gen_dispatcher.py::
    fetch_customers()), así que ya no puede llamar por otra vía — filtrar
    acá también sería redundante, no incorrecto.
    """
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT c.id AS customer_id, c.name AS customer_name, c.balance,
               c.techprefix AS techprefix, 'principal' AS ref
        FROM customers c
        WHERE c.billing_type = 'prepago' AND c.balance <= 0 AND c.techprefix != ''

        UNION ALL

        SELECT c.id AS customer_id, c.name AS customer_name, c.balance,
               cp.techprefix AS techprefix, 'campaña' AS ref
        FROM customer_prefixes cp
        JOIN customers c ON c.id = cp.customer_id
        WHERE c.billing_type = 'prepago' AND c.balance <= 0
    """)
    rows = cur.fetchall()
    cur.close()
    return rows


def sync_balance_block(conn, prefixes: list[str]) -> None:
    """Reemplaza TODO el contenido de balance_block_map — mismo criterio
    "regenerar todo, no parchear" que ya usa sync_techprefix_map()."""
    cur = conn.cursor()
    cur.execute("DELETE FROM balance_block_map")
    if prefixes:
        cur.executemany(
            "INSERT INTO balance_block_map (key_name, key_type, value_type, key_value, expires) "
            "VALUES (%s, 0, 0, '1', 0)",
            [(p,) for p in prefixes],
        )
    conn.commit()
    cur.close()


def reload_kamailio():
    # Mismo criterio de separación de privilegios que gen_dispatcher.py::
    # reload_kamailio() — dentro de Docker este proceso no tiene sudo/kamcmd,
    # un systemd path-unit en el host aplica el reload privilegiado.
    if os.getenv("VOXIKAM_SKIP_PRIVILEGED_RELOAD") == "1":
        print("  ⏭ VOXIKAM_SKIP_PRIVILEGED_RELOAD=1 — el watcher del host aplica el reload")
        return
    try:
        r = subprocess.run(
            ["sudo", "kamcmd", "htable.reload", "balance_block"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            print("  ✓ kamcmd htable.reload balance_block OK")
        else:
            print(f"  ⚠ kamcmd htable.reload balance_block: {r.stderr.strip()}")
    except FileNotFoundError:
        print("  ⚠ kamcmd no encontrado")
    except subprocess.TimeoutExpired:
        print("  ⚠ kamcmd htable.reload balance_block timeout")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    print(f"sync_balance_block.py — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    conn = get_db()
    try:
        blocked = fetch_blocked(conn)

        by_customer: dict = {}
        for row in blocked:
            by_customer.setdefault(row["customer_id"], {"name": row["customer_name"], "balance": row["balance"], "prefixes": []})
            by_customer[row["customer_id"]]["prefixes"].append(f"{row['techprefix']} ({row['ref']})")

        if not by_customer:
            print("  Ningún cliente prepago con saldo agotado ahora mismo.")
        else:
            print(f"  {len(by_customer)} cliente(s) prepago con saldo <= 0:")
            for c in by_customer.values():
                print(f"    - {c['name']}: saldo {c['balance']} — {', '.join(c['prefixes'])}")

        if not args.apply:
            print("\nModo diagnóstico (sin --apply, no se tocó nada — ni la tabla ni Kamailio).")
            return

        prefixes = [row["techprefix"] for row in blocked]
        sync_balance_block(conn, prefixes)
        print(f"  ✓ balance_block_map actualizado ({len(prefixes)} prefijos bloqueados)")
        reload_kamailio()
    except Exception as e:
        print(f"  ✗ Error: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
