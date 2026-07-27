#!/usr/bin/env python3
# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Resuelve automáticamente customers.techprefix DUPLICADOS (valor exacto
repetido) antes de que deploy.sh pueda agregar el UNIQUE KEY real
(uq_techprefix) — sin esto, el ADD UNIQUE falla con "Duplicate entry" y
la protección a nivel DB nunca queda puesta.

Encontrado en producción real: una condición de carrera en
reseller.py::_next_techprefix() (check-then-insert sin lock) dejó 2
sub-clientes con el mismo techprefix — Kamailio (substr match, primero
que matchea en el dispatcher generado gana) le enrutaba TODAS las
llamadas al mismo, el otro no recibía nada.

Criterio de resolución: el cliente MÁS VIEJO (id más chico, el que se
creó primero) se queda con el prefijo — es el que efectivamente viene
enrutando bien en producción hasta ahora. Los demás de ese grupo se
reasignan al siguiente prefijo de 4 dígitos libre, mismo generador que
reseller.py::_next_techprefix() (arranca en 5000).

Invocado automáticamente por deploy.sh en cada `--update`/`--upgrade`,
ANTES de intentar el ADD UNIQUE KEY. Si no hay duplicados, es un no-op.

*** ADVERTENCIA — ESTO NO ES SOLO UN CAMBIO DE BASE DE DATOS ***
Igual que migrate_5digit_techprefix.py: el cliente reasignado necesita
reconfigurar su lado (Vicidial/PBX/marcador) con el prefijo nuevo antes
de que deploy.sh regenere el dispatcher más adelante en el mismo run —
avisarle es responsabilidad de quien opera el deploy.

Uso manual (fuera de deploy.sh):
    venv/bin/python3 scripts/migrate_dedupe_techprefix.py
    venv/bin/python3 scripts/migrate_dedupe_techprefix.py --apply
"""
import argparse
import sys
from pathlib import Path

import pymysql

sys.path.insert(0, str(Path(__file__).parent))
from cron_summary import get_db  # reusa la conexión ya probada, no reimplementarla


def _techprefix_conflicts(cur, techprefix: str, exclude_id: int) -> bool:
    """Mismo criterio que reseller.py::_techprefix_conflicts() — colisión por
    substring bidireccional, contra customers.techprefix + customer_prefixes."""
    cur.execute("""
        SELECT 1 FROM (
            SELECT techprefix FROM customers WHERE techprefix IS NOT NULL AND id != %s
            UNION ALL
            SELECT techprefix FROM customer_prefixes
        ) x
        WHERE %s LIKE CONCAT(x.techprefix, '%%') OR x.techprefix LIKE CONCAT(%s, '%%')
    """, (exclude_id, techprefix, techprefix))
    return cur.fetchone() is not None


def _next_4digit_techprefix(cur, exclude_id: int, reserved: set[str]) -> str:
    """Misma búsqueda que reseller.py::_next_techprefix(), arrancando en 5000.
    `reserved` son prefijos ya asignados EN ESTE MISMO LOTE, todavía sin
    UPDATE/commit en la DB — sin esto, dos duplicados del mismo grupo (o de
    grupos distintos) podían recibir el mismo prefijo nuevo entre sí, porque
    la query de colisión no ve un cambio que todavía no se aplicó."""
    n = 5000
    while str(n) in reserved or _techprefix_conflicts(cur, str(n), exclude_id=exclude_id):
        n += 1
    return str(n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    conn = get_db()
    cur = conn.cursor(pymysql.cursors.DictCursor)

    cur.execute("""
        SELECT techprefix FROM customers
        WHERE techprefix IS NOT NULL
        GROUP BY techprefix HAVING COUNT(*) > 1
    """)
    dupes = [r["techprefix"] for r in cur.fetchall()]

    if not dupes:
        print("Nada para migrar — ningún techprefix duplicado.")
        return

    plan = []
    reserved: set[str] = set()  # prefijos ya elegidos en este lote, aún sin UPDATE
    for tp in dupes:
        cur.execute(
            "SELECT id, name, parent_customer_id FROM customers WHERE techprefix = %s ORDER BY id",
            (tp,),
        )
        rows = cur.fetchall()
        keeper, dupes_rows = rows[0], rows[1:]
        print(f"techprefix '{tp}' duplicado en {len(rows)} clientes:")
        print(f"  id={keeper['id']} {keeper['name']!r} — se queda con '{tp}' (el más viejo, id menor)")
        for r in dupes_rows:
            new_tp = _next_4digit_techprefix(cur, exclude_id=r["id"], reserved=reserved)
            reserved.add(new_tp)
            plan.append((r["id"], r["name"], tp, new_tp))
            tipo = "sub-cliente de reseller" if r["parent_customer_id"] else "cliente directo (¡raro, revisar!)"
            print(f"  id={r['id']} {r['name']!r} ({tipo}): {tp} → {new_tp}")

    if not args.apply:
        print(f"\nModo diagnóstico (sin --apply, no se tocó nada).")
        print("Antes de aplicar: coordinar con cada cliente reasignado el cambio de prefijo en su "
              "lado, y correr scripts/gen_dispatcher.py apenas se aplique acá.")
        return

    print("\nAplicando...")
    ucur = conn.cursor()
    for cid, name, old_tp, new_tp in plan:
        ucur.execute("UPDATE customers SET techprefix=%s WHERE id=%s", (new_tp, cid))
        print(f"  ✓ id={cid} {name!r}: {old_tp} → {new_tp}")
    conn.commit()
    ucur.close()

    print("\n✓ Duplicados resueltos en la base de datos.")
    print("⚠ deploy.sh regenera scripts/gen_dispatcher.py más adelante en este mismo run — "
          "avisar a cada cliente reasignado de su nuevo prefijo cuanto antes: sus llamadas "
          "fallan apenas ese ruteo quede activo si su lado sigue mandando el prefijo viejo.")


if __name__ == "__main__":
    main()
