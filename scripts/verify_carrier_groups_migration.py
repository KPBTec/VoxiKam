#!/usr/bin/env python3
# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Gate MANUAL de pre-vuelo para el corte a Grupos de ruteo — NO se invoca
desde deploy.sh, se corre a mano contra una COPIA real de la base de un
servidor con datos de producción (ej. vd1sbc2), inmediatamente después de
`scripts/migrate_carrier_groups.py --apply` y ANTES de dejar que ningún
admin/reseller toque el feature nuevo.

Resuelve, para cada techprefix, la lista de destinos (carrier_id, host,
port, priority) que el mecanismo VIEJO (pin único active_carrier_id/
carrier_failover_enabled sobre customer_carriers — congelado acá tal cual
estaba en git HEAD antes de este cambio, commit 32f3ebf) y el mecanismo
NUEVO (routing_group_id/carrier_groups, importado en vivo desde
scripts/gen_dispatcher.py — nunca una copia, así nunca diverge del código
real que corre en producción) resolverían, contra la MISMA conexión de DB,
y compara técprefix por técprefix. NO compara texto/números de grupo
crudos (dispatcher.list/técprefix_map) — el nuevo esquema numera grupos
por carrier_groups.id, no por customer_id, así que los números NUNCA van a
coincidir aunque el ruteo resultante sea idéntico; lo único que importa es
a qué carriers, en qué orden, termina llegando cada prefijo.

Cualquier diferencia real (un techprefix que resuelve a otros carriers, en
otro orden, o que aparece en un lado y no en el otro) = NO cortar,
investigar antes. Salida sin diferencias = exit 0; con diferencias =
exit 1 (para poder usarlo como gate en un script de corte más grande si
hiciera falta).

Solo tiene sentido para pines simples (priority, migrados desde el pin
viejo) — un grupo round_robin/percent creado por un admin DESPUÉS de la
migración es funcionalidad nueva que el sistema viejo no podía expresar, y
correctamente va a aparecer como diferencia si se corre este chequeo
después de que alguien ya empezó a usar el feature nuevo. Este script es
para el momento exacto del corte, no para uso continuo. Debe correr
DESPUÉS de `migrate_carrier_groups.py --apply` pero ANTES de que
deploy.sh borre customer_carriers/active_carrier_id/carrier_failover_enabled
(ver deploy.sh) — sobre una COPIA de la DB, nunca la real.

Uso:
    venv/bin/python3 scripts/verify_carrier_groups_migration.py
"""
import sys
from collections import defaultdict
from pathlib import Path

import pymysql

sys.path.insert(0, str(Path(__file__).parent))
from cron_summary import get_db  # misma conexión que usa migrate_carrier_groups.py

import gen_dispatcher as new  # la lógica NUEVA se importa en vivo — nunca una copia


# ═══════════════════════════════════════════════════════════════════════════
# LÓGICA VIEJA — congelada tal cual estaba en git HEAD (commit 32f3ebf,
# scripts/gen_dispatcher.py) antes del rediseño a Grupos de ruteo. Existe
# SOLO para este chequeo de una sola vez — no editar para que siga
# reflejando el comportamiento real que estuvo en producción hasta el corte.
# ═══════════════════════════════════════════════════════════════════════════

def fetch_customer_carriers_old(conn):
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT
            c.id          AS customer_id,
            c.name        AS customer_name,
            c.techprefix  AS techprefix,
            c.active_carrier_id        AS customer_active_carrier_id,
            c.carrier_failover_enabled AS customer_failover_enabled,
            ca.id         AS carrier_id,
            ca.host,
            ca.port,
            ca.outbound_prefix,
            ca.cps_limit,
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


def fetch_customer_prefixes_old(conn) -> dict:
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        "SELECT id, customer_id, techprefix, label, active_carrier_id, "
        "carrier_failover_enabled FROM customer_prefixes"
    )
    rows = cur.fetchall()
    cur.close()
    by_customer: dict = defaultdict(list)
    for row in rows:
        by_customer[row["customer_id"]].append(row)
    return by_customer


def _override_destinations_old(carriers: list[dict], active_carrier_id, failover_enabled: bool):
    chosen = next((r for r in carriers if r["carrier_id"] == active_carrier_id), None)
    if not chosen:
        return None
    if not failover_enabled:
        return [chosen]
    max_priority = max(r["customer_priority"] for r in carriers)
    return [dict(chosen, customer_priority=max_priority + 1)] + \
           [r for r in carriers if r["carrier_id"] != active_carrier_id]


# ═══════════════════════════════════════════════════════════════════════════
# Resolución de ruteo — techprefix → destinos, sin pasar por números de
# grupo (esos son un detalle interno de cada esquema, no comparables 1:1).
# ═══════════════════════════════════════════════════════════════════════════

def _dest_key(carrier_id, host, port, priority) -> tuple:
    return (carrier_id, host, port, priority)


def resolve_old_routing(by_customer_old: dict, cust_prefixes_old: dict) -> dict[str, list[tuple]]:
    result: dict[str, list[tuple]] = {}
    for cid, carriers in by_customer_old.items():
        primary = carriers[0]["techprefix"] or ""
        if primary:
            active_id = carriers[0].get("customer_active_carrier_id")
            chosen = None
            if active_id:
                chosen = _override_destinations_old(
                    carriers, active_id, bool(carriers[0].get("customer_failover_enabled", 1))
                )
            chosen = chosen or carriers
            result[primary] = sorted(_dest_key(r["carrier_id"], r["host"], r["port"], r["customer_priority"]) for r in chosen)

        for cp in cust_prefixes_old.get(cid, []):
            if not cp["techprefix"]:
                continue
            active_id = cp.get("active_carrier_id")
            chosen = None
            if active_id:
                chosen = _override_destinations_old(carriers, active_id, bool(cp.get("carrier_failover_enabled", 1)))
            chosen = chosen or carriers
            result[cp["techprefix"]] = sorted(_dest_key(r["carrier_id"], r["host"], r["port"], r["customer_priority"]) for r in chosen)
    return result


def resolve_new_routing(customers_new: list[dict], cust_prefixes_new: dict, groups_new: dict) -> dict[str, list[tuple]]:
    result: dict[str, list[tuple]] = {}
    for techprefix, dispatcher_group, _cid, _alg in new.build_techprefix_rows(customers_new, cust_prefixes_new, groups_new):
        gid = dispatcher_group - new.GROUP_NUMBER_OFFSET
        members = groups_new[gid]["members"]
        result[techprefix] = sorted(_dest_key(m["carrier_id"], m["host"], m["port"], m["customer_priority"]) for m in members)
    return result


def _diff_routing(old_routing: dict[str, list[tuple]], new_routing: dict[str, list[tuple]]) -> bool:
    """Devuelve True si hay diferencias (y las imprime)."""
    has_diff = False
    all_prefixes = sorted(set(old_routing) | set(new_routing))
    for pfx in all_prefixes:
        old_dst = old_routing.get(pfx)
        new_dst = new_routing.get(pfx)
        if old_dst == new_dst:
            continue
        has_diff = True
        if old_dst is None:
            print(f"✗ techprefix {pfx!r}: NUEVO tiene ruteo pero VIEJO no tenía nada → {new_dst}")
        elif new_dst is None:
            print(f"✗ techprefix {pfx!r}: VIEJO ruteaba {old_dst} pero NUEVO no tiene nada")
        else:
            print(f"✗ techprefix {pfx!r}: destinos distintos")
            print(f"    viejo: {old_dst}")
            print(f"    nuevo: {new_dst}")
    if not has_diff:
        print(f"✓ {len(all_prefixes)} techprefix(es) comparados — ruteo resuelto idéntico en ambos esquemas")
    return has_diff


def main():
    conn = get_db()
    try:
        by_customer_old = fetch_customer_carriers_old(conn)
        cust_prefixes_old = fetch_customer_prefixes_old(conn)
        old_routing = resolve_old_routing(by_customer_old, cust_prefixes_old)

        customers_new = new.fetch_customers(conn)
        cust_prefixes_new = new.fetch_customer_prefixes(conn)
        groups_new = new.fetch_carrier_groups(conn)
        new_routing = resolve_new_routing(customers_new, cust_prefixes_new, groups_new)
    finally:
        conn.close()

    has_diff = _diff_routing(old_routing, new_routing)

    if has_diff:
        print("\n✗ Hay diferencias de comportamiento — NO cortar a producción todavía. Investigar antes.")
        sys.exit(1)
    print("\n✓ Comportamiento idéntico entre el mecanismo viejo y el nuevo (post-migración) — OK para cortar.")


if __name__ == "__main__":
    main()
