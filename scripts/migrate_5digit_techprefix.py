#!/usr/bin/env python3
# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Convierte a 4 dígitos cualquier techprefix de sub-cliente de reseller que
haya quedado en 5 dígitos (rango viejo, arrancaba en 10000). La regla de la
plataforma es SIEMPRE 4 dígitos, sin excepción, justamente para no romper
herramientas alrededor de Kamailio que asumen ese largo fijo (ver el propio
historial de cron_dlg_stats.py). El generador (reseller.py::
_next_techprefix) ya se corrigió para arrancar en 5000 — este script es el
que arregla lo que YA se haya creado con el generador viejo.

Invocado automáticamente por deploy.sh en cada `--update`/`--upgrade`
(detecta si hay algo que migrar; si no hay nada, es un no-op). deploy.sh
regenera scripts/gen_dispatcher.py más adelante en el mismo run, así que el
ruteo Kamailio queda al día con el prefijo nuevo al terminar ese deploy.

*** ADVERTENCIA — ESTO NO ES SOLO UN CAMBIO DE BASE DE DATOS ***
El techprefix de un sub-cliente está grabado en SU marcador/Vicidial/PBX —
así arma el número que le manda a este SBC. En cuanto este script corre (y
deploy.sh regenera el dispatcher), ese cliente necesita reconfigurar su lado
con el prefijo nuevo — antes de eso, sus llamadas fallan. Avisarle es
responsabilidad de quien opera el deploy, este script no lo hace.

Uso manual (fuera de deploy.sh):
    venv/bin/python3 scripts/migrate_5digit_techprefix.py
    venv/bin/python3 scripts/migrate_5digit_techprefix.py --apply
"""
import argparse
import sys
from pathlib import Path

import pymysql

sys.path.insert(0, str(Path(__file__).parent))
from cron_summary import get_db  # reusa la conexión ya probada, no reimplementarla


def _techprefix_conflicts(cur, techprefix: str, exclude_id: int | None = None) -> bool:
    """Mismo criterio que reseller.py::_techprefix_conflicts() — colisión por
    substring bidireccional, contra customers.techprefix + customer_prefixes."""
    excl = "AND id != %s" if exclude_id is not None else ""
    params = [techprefix, techprefix]
    q = f"""
        SELECT 1 FROM (
            SELECT techprefix FROM customers WHERE techprefix != '' {excl}
            UNION ALL
            SELECT techprefix FROM customer_prefixes
        ) x
        WHERE %s LIKE CONCAT(x.techprefix, '%%') OR x.techprefix LIKE CONCAT(%s, '%%')
    """
    if exclude_id is not None:
        params = [exclude_id, techprefix, techprefix]
        q = q.replace("%s FROM customers WHERE techprefix != '' AND id != %s",
                       "FROM customers WHERE techprefix != '' AND id != %s")
    cur.execute(q, params if exclude_id is None else [exclude_id, techprefix, techprefix])
    return cur.fetchone() is not None


def _next_4digit_techprefix(cur, exclude_id: int) -> str:
    """Misma búsqueda que reseller.py::_next_techprefix(), arrancando en
    5000 — el sub-cliente que se está migrando se excluye de su propio
    chequeo de colisión (todavía tiene el valor viejo de 5 dígitos en esa
    fila mientras se decide el nuevo)."""
    n = 5000
    while _techprefix_conflicts(cur, str(n), exclude_id=exclude_id):
        n += 1
    return str(n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    conn = get_db()
    cur = conn.cursor(pymysql.cursors.DictCursor)

    cur.execute("""
        SELECT id, name, techprefix, parent_customer_id
        FROM customers
        WHERE techprefix IS NOT NULL AND LENGTH(techprefix) > 4
        ORDER BY id
    """)
    rows = cur.fetchall()

    if not rows:
        print("Nada para migrar — ningún cliente tiene techprefix de más de 4 dígitos.")
        return

    print(f"{len(rows)} cliente(s) con techprefix > 4 dígitos:\n")
    plan = []
    for r in rows:
        new_tp = _next_4digit_techprefix(cur, exclude_id=r["id"])
        plan.append((r["id"], r["name"], r["techprefix"], new_tp))
        tipo = "sub-cliente de reseller" if r["parent_customer_id"] else "cliente directo (¡raro, revisar!)"
        print(f"  id={r['id']} {r['name']!r} ({tipo}): {r['techprefix']} → {new_tp}")

    if not args.apply:
        print(f"\nModo diagnóstico (sin --apply, no se tocó nada).")
        print("Antes de aplicar: coordinar con cada cliente el cambio de prefijo en su lado, "
              "y correr scripts/gen_dispatcher.py apenas se aplique acá (no lo hace este script).")
        return

    print("\nAplicando...")
    ucur = conn.cursor()
    for cid, name, old_tp, new_tp in plan:
        ucur.execute("UPDATE customers SET techprefix=%s WHERE id=%s", (new_tp, cid))
        print(f"  ✓ id={cid} {name!r}: {old_tp} → {new_tp}")
    conn.commit()
    ucur.close()

    print("\n✓ Migración completa en la base de datos.")
    print("⚠ deploy.sh regenera scripts/gen_dispatcher.py más adelante en este mismo run — "
          "avisar a cada cliente afectado de su nuevo prefijo cuanto antes: "
          "sus llamadas fallan apenas ese ruteo quede activo si su lado sigue mandando el prefijo viejo.")


if __name__ == "__main__":
    main()
