#!/usr/bin/env python3
# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Migra settings.lan_peers (CSV suelto "host:puerto,host:puerto", sin CRUD ni
pantalla propia) a la tabla lan_peers (CRUD real, página "Entrante" del
panel) — ver backend/routers/lan_peers.py. Nadie tuvo forma de setear este
campo salvo un UPDATE manual a la base (nunca existió un endpoint), así que
en la mayoría de los servers esto es un no-op — pero si alguien SÍ lo cargó
a mano en producción, no hay que perderlo en silencio.

Idempotente: no inserta duplicados (UNIQUE KEY host+port en lan_peers). No
borra la fila vieja de `settings` — queda como referencia inerte, gen_dispatcher.py
ya no la lee (ver fetch_lan_peers()).

Uso: venv/bin/python3 scripts/migrate_lan_peers.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cron_summary import get_db


def main():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key_name = 'lan_peers' LIMIT 1")
    row = cur.fetchone()
    if not row or not row[0]:
        print("Nada para migrar — settings.lan_peers vacío o inexistente.")
        return

    peers = [p.strip() for p in row[0].split(",") if p.strip()]
    if not peers:
        print("Nada para migrar — settings.lan_peers sin valores reales.")
        return

    added = 0
    for peer in peers:
        host, _, port = peer.partition(":")
        port = port or "5060"
        try:
            cur.execute(
                "INSERT IGNORE INTO lan_peers (host, port, description) VALUES (%s, %s, %s)",
                (host, int(port), "Migrado desde settings.lan_peers"),
            )
            if cur.rowcount:
                added += 1
                print(f"  ✓ {host}:{port}")
        except ValueError:
            print(f"  ⚠ '{peer}' no es un host:puerto válido — se ignora")
    conn.commit()
    print(f"\n✓ {added} peer(s) migrado(s) a la tabla lan_peers.")


if __name__ == "__main__":
    main()
