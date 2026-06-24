#!/usr/bin/env python3
# la plataforma anterior — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2025 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2025 – Todos los derechos reservados.

"""
Lee DB → regenera /etc/nftables.d/carriers.nft y customers.nft → nft -f
Ejecutado por FastAPI al cambiar IPs de clientes o reglas de firewall.
También corre en cron cada 5 minutos como safety net.
"""
import os
import subprocess
from datetime import datetime
from pathlib import Path

import pymysql
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader

# Leer INSTALL_DIR desde el marcador del sistema si existe,
# sino usar la ubicación relativa a este script (fallback)
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

BASE_DIR    = Path(__file__).parent.parent
TMPL_DIR    = BASE_DIR / "templates"
NFTABLES_D  = Path(os.getenv("NFTABLES_D", "/etc/nftables.d"))
NFTABLES_CONF = Path(os.getenv("NFTABLES_CONF", "/etc/nftables.conf"))
DOMAIN      = os.getenv("DOMAIN", "localhost")
WEB_PORT    = os.getenv("WEB_PORT", "7666")

j2 = Environment(loader=FileSystemLoader(str(TMPL_DIR)))


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


def render_dynamic(set_name: str, ips: list[str]) -> str:
    tpl = j2.get_template("nftables-dynamic.j2")
    return tpl.render(
        set_name=set_name,
        ips=ips,
        domain=DOMAIN,
        web_port=WEB_PORT,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def apply_nftables():
    # nft requiere root — kaplabilling tiene NOPASSWD para /usr/sbin/nft via sudoers
    result = subprocess.run(
        ["sudo", "nft", "-f", str(NFTABLES_CONF)],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode == 0:
        print("  ✓ nftables recargado")
    else:
        print(f"  ✗ nft error: {result.stderr.strip()}")


SSH_PORT = os.getenv("SSH_PORT", "22")

# Mapeo servicio → reglas nft
_SVC_RULES = {
    "sip": ["udp dport 5060 accept", "tcp dport 5060 accept"],
    "rtp": ["udp dport 20000-40000 accept"],
    "ssh": [f"tcp dport {SSH_PORT} accept"],
}


def render_manual_rules(
    deny_ips: list[str],
    service_rules: list[tuple[str, str]],  # (ip, service)
) -> str:
    lines = ["# AUTO-GENERADO por gen_nftables.py — NO editar manualmente", ""]
    if deny_ips:
        lines.append("# DENY — bloqueo explícito (prevalece sobre accepts)")
        for ip in deny_ips:
            lines.append(f"ip saddr {ip} drop")
        lines.append("")
    if service_rules:
        lines.append("# ALLOW por servicio específico")
        for ip, svc in service_rules:
            for rule in _SVC_RULES.get(svc, []):
                lines.append(f"ip saddr {ip} {rule}")
        lines.append("")
    return "\n".join(lines)


def main():
    conn = get_db()
    cur = conn.cursor()

    # IPs de carriers activos
    cur.execute("SELECT DISTINCT host FROM carriers WHERE status = 'active'")
    carrier_ips = [row[0] for row in cur.fetchall()]

    # IPs de clientes activos
    cur.execute("""
        SELECT DISTINCT ci.ip
        FROM customer_ips ci
        JOIN customers c ON ci.customer_id = c.id AND c.status = 'active'
    """)
    customer_ips = [row[0] for row in cur.fetchall()]

    # Reglas manuales ALLOW — service='all' van al set genérico (todos los puertos SIP/RTP)
    cur.execute("""
        SELECT ip FROM firewall_rules
        WHERE action = 'allow' AND jail = 0
          AND (service = 'all' OR service IS NULL)
    """)
    extra_allow = [row[0] for row in cur.fetchall()]

    # Reglas manuales ALLOW con servicio específico
    cur.execute("""
        SELECT ip, service FROM firewall_rules
        WHERE action = 'allow' AND jail = 0
          AND service IN ('sip','rtp','ssh')
    """)
    service_rules = [(row[0], row[1]) for row in cur.fetchall()]

    # Reglas DENY y jails
    cur.execute("SELECT ip FROM firewall_rules WHERE action = 'deny' OR jail = 1")
    deny_ips = [row[0] for row in cur.fetchall()]

    # SSH_PORT desde settings (override del env)
    try:
        cur.execute("SELECT value FROM settings WHERE key_name = 'ssh_port'")
        row = cur.fetchone()
        if row:
            _SVC_RULES["ssh"] = [f"tcp dport {row[0]} accept"]
    except Exception:
        pass

    cur.close()
    conn.close()

    NFTABLES_D.mkdir(parents=True, exist_ok=True)

    # manual_rules.nft — deny + reglas con puerto específico (se incluye PRIMERO en nftables.conf)
    (NFTABLES_D / "manual_rules.nft").write_text(
        render_manual_rules(deny_ips, service_rules)
    )
    print(f"  ✓ manual_rules.nft ({len(deny_ips)} deny, {len(service_rules)} allow/svc)")

    # Carriers — IPs sin restricción de puerto + reglas 'all' del panel
    (NFTABLES_D / "carriers.nft").write_text(
        render_dynamic("carrier_ips", carrier_ips + extra_allow)
    )
    print(f"  ✓ carriers.nft ({len(carrier_ips)} carrier + {len(extra_allow)} global)")

    # Clientes
    (NFTABLES_D / "customers.nft").write_text(
        render_dynamic("customer_ips", customer_ips)
    )
    print(f"  ✓ customers.nft ({len(customer_ips)} IPs)")

    apply_nftables()


if __name__ == "__main__":
    main()
