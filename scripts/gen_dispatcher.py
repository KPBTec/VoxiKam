#!/usr/bin/env python3
# la plataforma anterior — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2025 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2025 – Todos los derechos reservados.

"""
Lee DB → genera dos archivos para Kamailio y recarga:
  1. /etc/kamailio/dispatcher.list      — destinos por grupo (carrier host:port)
  2. /etc/kamailio/kaplabilling-routes.cfg — reglas de techprefix (incluido en kamailio.cfg)

Ejecutado por FastAPI cada vez que se modifica un carrier o cliente.
"""
import os
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path

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

DISPATCHER_LIST  = os.getenv("DISPATCHER_LIST", "/etc/kamailio/dispatcher.list")
ROUTES_CFG       = str(Path(DISPATCHER_LIST).parent / "kaplabilling-routes.cfg")


def get_db():
    url = os.getenv("DATABASE_URL_SYNC", "")
    parts     = url.replace("mysql+pymysql://", "").split("@")
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


def fetch_lan_peers(conn) -> list[str]:
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key_name = 'lan_peers' LIMIT 1")
    row = cur.fetchone()
    cur.close()
    if not row or not row[0]:
        return []
    return [p.strip() for p in row[0].split(",") if p.strip()]


def fetch_customer_carriers(conn):
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT
            c.id          AS customer_id,
            c.name        AS customer_name,
            c.techprefix  AS techprefix,
            ca.id         AS carrier_id,
            ca.host,
            ca.port,
            ca.outbound_prefix,
            cc.priority   AS customer_priority
        FROM customer_carriers cc
        JOIN customers c  ON cc.customer_id = c.id  AND c.status = 'active'
        JOIN carriers  ca ON cc.carrier_id  = ca.id AND ca.status = 'active'
        ORDER BY c.id, cc.priority DESC
    """)
    rows = cur.fetchall()
    cur.close()

    by_customer: dict = defaultdict(list)
    for row in rows:
        by_customer[row["customer_id"]].append(row)
    return by_customer


def build_dispatcher_list(by_customer: dict, lan_peers: list[str]) -> str:
    public_ip  = os.getenv("PUBLIC_IP", "")
    private_ip = os.getenv("PRIVATE_IP", "")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# AUTO-GENERADO por gen_dispatcher.py",
        f"# Última actualización: {ts}",
        "# NO editar manualmente — gestionar desde el panel admin",
        "",
        "# GRUPO 1: Asterisk/ViciBox (LAN) — gestionado desde Settings > LAN Peers",
    ]
    if lan_peers:
        for peer in lan_peers:
            host_port = peer if ":" in peer else f"{peer}:5060"
            attr = f"socket=udp:{private_ip}:5060" if private_ip else ""
            lines.append(f"1 sip:{host_port}  0 0 {attr}".rstrip())
    else:
        lines.append("# (sin peers LAN configurados — agregar desde Settings > LAN Peers)")
    lines.append("")

    # Grupos por cliente: 100 + customer_id
    for cid, carriers in by_customer.items():
        group = 100 + cid
        lines.append(f"# Cliente ID={cid}: {carriers[0]['customer_name']} → grupo {group}")
        for row in carriers:
            pfx  = row["outbound_prefix"] or ""
            attr = f"socket=udp:{public_ip}:5060;carid={row['carrier_id']}"
            if pfx:
                attr += f";prefix={pfx}"
            lines.append(f"{group} sip:{row['host']}:{row['port']}  0 {row['customer_priority']} {attr}")
        lines.append("")

    return "\n".join(lines)


def build_routes_cfg(by_customer: dict) -> str:
    """
    Genera fragmento Kamailio incluido en request_route (antes del split dirección).
    Por cada cliente activo con techprefix:
      1. Compara inicio de $rU con su techprefix
      2. Quita el techprefix del R-URI ($rU limpio)
      3. Asigna $var(grp) = 100 + customer_id
    El caller (request_route) decide la ruta según $var(grp) != 0.
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"# AUTO-GENERADO por gen_dispatcher.py — {ts}",
        "# NO editar manualmente",
        "",
    ]

    if not by_customer:
        lines.append("# (sin clientes activos con carriers asignados)")
        return "\n".join(lines)

    for cid, carriers in by_customer.items():
        pfx   = carriers[0]["techprefix"] or ""
        name  = carriers[0]["customer_name"]
        group = 100 + cid
        if not pfx:
            lines.append(f"# Cliente ID={cid} ({name}): sin techprefix — omitido")
            lines.append("")
            continue

        pfx_len = len(pfx)
        lines.append(f"# Cliente ID={cid}: {name} — techprefix={pfx} → grupo {group}")
        lines.append(f'if ($(rU{{s.substr,0,{pfx_len}}}) == "{pfx}") {{')
        lines.append(f'    $rU = $(rU{{s.substr,{pfx_len},0}});')
        lines.append(f"    $var(grp) = {group};")
        lines.append( "}")
        lines.append("")

    return "\n".join(lines)


def reload_kamailio():
    try:
        r = subprocess.run(
            ["sudo", "kamcmd", "dispatcher.reload"],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0:
            print("  ✓ kamcmd dispatcher.reload OK")
        else:
            print(f"  ⚠ kamcmd dispatcher.reload: {r.stderr.strip()}")
    except FileNotFoundError:
        print("  ⚠ kamcmd no encontrado")
    except subprocess.TimeoutExpired:
        print("  ⚠ kamcmd timeout")


def main():
    conn = get_db()
    try:
        lan_peers   = fetch_lan_peers(conn)
        by_customer = fetch_customer_carriers(conn)

        disp = build_dispatcher_list(by_customer, lan_peers)
        Path(DISPATCHER_LIST).write_text(disp)
        print(f"  ✓ {DISPATCHER_LIST} actualizado ({len(by_customer)} clientes)")

        routes = build_routes_cfg(by_customer)
        Path(ROUTES_CFG).write_text(routes)
        print(f"  ✓ {ROUTES_CFG} actualizado")

        reload_kamailio()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
