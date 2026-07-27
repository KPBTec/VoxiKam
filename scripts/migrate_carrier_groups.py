#!/usr/bin/env python3
# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Backfill de Grupos de ruteo — consolida en UN SOLO grupo "Principal" por
cliente tanto lo que tenía asignado en customer_carriers (su pool de
carriers, con prioridad) como el pin viejo (active_carrier_id/
carrier_failover_enabled) si lo tenía. customers.routing_group_id pasa a
ser el ÚNICO mecanismo — ya no hay distinción "default" (customer_carriers)
vs "override" (active_carrier_id): un cliente con carriers asignados
SIEMPRE tiene UN grupo, full stop (ver backend/routers/customers.py::
_ensure_own_group, que hace lo mismo en vivo desde el panel).

*** LA PARTE DELICADA — LEER ANTES DE CORRER CON --apply EN PRODUCCIÓN ***
Si el cliente tenía carrier_failover_enabled=True (el default — la mayoría
de los pines reales en vd1sbc2) para su pin viejo, NO alcanza con migrar
el carrier pineado solo: el mecanismo viejo (gen_dispatcher.py::
_override_destinations(), ya eliminado del código pero vigente en el
comportamiento hasta este corte) armaba el grupo de override con el pin
en primer lugar MÁS todos los demás carriers asignados como fallback
dinámico. Migrar solo el pin le sacaría ese fallback en el corte — bug
real encontrado al diseñar la primera versión de este script, corregido
acá: para failover_enabled=True se snapshotea la lista COMPLETA de
customer_carriers de ese cliente en el momento de migrar (el pin
boosteado a la prioridad más alta, el resto en su orden de prioridad
actual). Para failover_enabled=False, el grupo migrado tiene un solo
miembro (el pin) — sin cambio de comportamiento en ningún caso. Un
cliente SIN pin (la mayoría) simplemente se lleva su pool de
customer_carriers tal cual, en su mismo orden de prioridad — el
comportamiento por defecto de siempre.

Prefijos de campaña (customer_prefixes) con SU PROPIO active_carrier_id
puntual siguen migrando a un grupo de override separado, exactamente igual
que antes — un prefijo de campaña SIN pin propio queda con
routing_group_id NULL, que hereda el grupo del cliente automáticamente
(ver gen_dispatcher.py::build_techprefix_rows) — mismo comportamiento que
tenía antes (caía al pool del cliente sin necesitar nada explícito).

Sin dedup a propósito: un grupo nuevo por cliente/campaña migrada, aunque
compartan carriers — ver el plan (fizzy-greeting-minsky.md, sección "Fuera
de alcance"). Nombre `"{cliente} — Principal"` / `"{cliente} — {campaña}"`.
owner_customer_id del grupo nuevo = parent_customer_id del cliente migrado
(si es sub-cliente de un reseller, el reseller pasa a administrar ese
grupo) o NULL (plataforma/admin) si no tiene reseller.

Idempotente: solo procesa clientes/prefijos con routing_group_id IS NULL —
una vez migrada una fila (routing_group_id seteado), correr el script de
nuevo la deja intacta. Invocado automáticamente por deploy.sh en cada
--update/--upgrade (con --apply), ANTES de borrar customer_carriers/
active_carrier_id/carrier_failover_enabled (ver deploy.sh) — necesita esas
columnas/tabla intactas para leer el estado viejo.

Uso manual:
    venv/bin/python3 scripts/migrate_carrier_groups.py            # diagnóstico, no toca nada
    venv/bin/python3 scripts/migrate_carrier_groups.py --apply    # aplica
"""
import argparse
import sys
from pathlib import Path

import pymysql

sys.path.insert(0, str(Path(__file__).parent))
from cron_summary import get_db  # reusa la conexión ya probada, no reimplementarla


def _customer_carriers_pool(cur, cid: int) -> list[dict]:
    cur.execute(
        "SELECT carrier_id, priority FROM customer_carriers WHERE customer_id = %s ORDER BY priority DESC",
        (cid,),
    )
    return cur.fetchall()


def _build_members(pool: list[dict], active_carrier_id, failover_enabled: bool) -> list[dict]:
    """
    Sin pin (active_carrier_id NULL o ya no está en el pool): el pool tal
    cual, en su orden de prioridad actual — comportamiento default de
    siempre. Con pin: ver advertencia grande arriba.
    """
    pinned = next((c for c in pool if c["carrier_id"] == active_carrier_id), None) if active_carrier_id else None
    if pinned is None:
        return [{"carrier_id": c["carrier_id"], "priority": c["priority"]} for c in pool]
    if not failover_enabled:
        return [{"carrier_id": pinned["carrier_id"], "priority": pinned["priority"]}]
    max_priority = max(c["priority"] for c in pool)
    members = [{"carrier_id": pinned["carrier_id"], "priority": max_priority + 1}]
    for c in pool:
        if c["carrier_id"] != active_carrier_id:
            members.append({"carrier_id": c["carrier_id"], "priority": c["priority"]})
    return members


def _next_display_label(cur, cid: int) -> str:
    cur.execute("SELECT COUNT(*) AS n FROM customer_carrier_groups WHERE customer_id = %s", (cid,))
    return f"Grupo {cur.fetchone()['n'] + 1}"


def build_plan(cur) -> list[dict]:
    plan = []

    # ── Principal: un grupo por cliente, consolidando pool + pin viejo ──
    cur.execute("""
        SELECT id, name, parent_customer_id, active_carrier_id, carrier_failover_enabled
        FROM customers
        WHERE routing_group_id IS NULL
    """)
    for row in cur.fetchall():
        pool = _customer_carriers_pool(cur, row["id"])
        if not pool:
            continue  # sin carriers asignados nunca — nada para migrar, queda NULL (correcto)
        members = _build_members(pool, row["active_carrier_id"], bool(row["carrier_failover_enabled"]))
        tag = "con pin viejo" if row["active_carrier_id"] else "pool tal cual (sin pin)"
        group_name = f"{row['name']} — Principal"
        print(f"  [principal] cliente id={row['id']} {row['name']!r}: grupo nuevo {group_name!r} "
              f"con {len(members)} miembro(s) ({tag})")
        for m in members:
            print(f"      carrier_id={m['carrier_id']} priority={m['priority']}")
        plan.append({
            "kind": "principal", "customer_id": row["id"], "ref": None,
            "group_name": group_name, "owner_customer_id": row["parent_customer_id"], "members": members,
        })

    # ── Campañas: solo las que tenían su PROPIO pin puntual (sin cambios de criterio) ──
    cur.execute("""
        SELECT cp.id, cp.customer_id, cp.label, cp.techprefix, cp.active_carrier_id,
               cp.carrier_failover_enabled, c.name AS customer_name, c.parent_customer_id
        FROM customer_prefixes cp JOIN customers c ON cp.customer_id = c.id
        WHERE cp.routing_group_id IS NULL AND cp.active_carrier_id IS NOT NULL
    """)
    for row in cur.fetchall():
        pool = _customer_carriers_pool(cur, row["customer_id"])
        pinned_in_pool = any(c["carrier_id"] == row["active_carrier_id"] for c in pool)
        if not pinned_in_pool:
            print(f"  [campaña] cliente id={row['customer_id']} {row['customer_name']!r}: "
                  f"active_carrier_id={row['active_carrier_id']} ya no está en el pool — override inefectivo, se ignora")
            continue
        members = _build_members(pool, row["active_carrier_id"], bool(row["carrier_failover_enabled"]))
        label = row["label"] or row["techprefix"]
        group_name = f"{row['customer_name']} — {label}"
        print(f"  [campaña] cliente id={row['customer_id']} {row['customer_name']!r}, {label}: "
              f"grupo nuevo {group_name!r} con {len(members)} miembro(s)")
        for m in members:
            print(f"      carrier_id={m['carrier_id']} priority={m['priority']}")
        plan.append({
            "kind": "campaña", "customer_id": row["customer_id"], "ref": row["id"],
            "group_name": group_name, "owner_customer_id": row["parent_customer_id"], "members": members,
        })

    return plan


def apply_plan(conn, cur, plan: list[dict]) -> None:
    for entry in plan:
        cur.execute(
            "INSERT INTO carrier_groups (name, algorithm, owner_customer_id) VALUES (%s, 'priority', %s)",
            (entry["group_name"], entry["owner_customer_id"]),
        )
        group_id = cur.lastrowid
        for m in entry["members"]:
            cur.execute(
                "INSERT INTO carrier_group_members (group_id, carrier_id, priority) VALUES (%s, %s, %s)",
                (group_id, m["carrier_id"], m["priority"]),
            )
        label = "Principal" if entry["kind"] == "principal" else _next_display_label(cur, entry["customer_id"])
        cur.execute(
            "INSERT INTO customer_carrier_groups (customer_id, group_id, display_label) VALUES (%s, %s, %s)",
            (entry["customer_id"], group_id, label),
        )
        if entry["kind"] == "principal":
            cur.execute(
                "UPDATE customers SET routing_group_id = %s WHERE id = %s",
                (group_id, entry["customer_id"]),
            )
        else:
            cur.execute(
                "UPDATE customer_prefixes SET routing_group_id = %s WHERE id = %s",
                (group_id, entry["ref"]),
            )
        conn.commit()
        print(f"  ✓ grupo id={group_id} {entry['group_name']!r} ({label}) creado y asignado")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    conn = get_db()
    cur = conn.cursor(pymysql.cursors.DictCursor)

    plan = build_plan(cur)

    if not plan:
        print("Nada para migrar — ningún cliente/prefijo pendiente (routing_group_id IS NULL con datos que migrar).")
        return

    print(f"\n{len(plan)} grupo(s) para crear.")

    if not args.apply:
        print("\nModo diagnóstico (sin --apply, no se tocó nada).")
        print("Antes de aplicar en un servidor con datos reales: correr "
              "scripts/verify_carrier_groups_migration.py contra una copia de esa DB y comparar "
              "el ruteo viejo vs. nuevo — es el gate real, no este resumen.")
        return

    print("\nAplicando...")
    apply_plan(conn, cur, plan)
    cur.close()

    print(f"\n✓ {len(plan)} grupo(s) migrado(s). Correr scripts/gen_dispatcher.py para regenerar "
          "dispatcher.list/techprefix_map con los grupos nuevos (deploy.sh ya lo hace más adelante en el mismo run).")


if __name__ == "__main__":
    main()
