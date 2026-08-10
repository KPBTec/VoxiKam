#!/usr/bin/env python3
# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Lee DB → genera/actualiza:
  1. /etc/kamailio/dispatcher.list — destinos por grupo (carrier host:port),
     recargado en caliente con `kamcmd dispatcher.reload`.
  2. Tabla MySQL techprefix_map — techprefix → "grupo:cliente:algoritmo",
     respalda el htable "techmap" de Kamailio (ver templates/kamailio.cfg.j2),
     recargado en caliente con `kamcmd htable.reload techmap`.

Reemplaza el viejo voxikam-routes.cfg (bloques if/else compilados vía
#!include_file, que Kamailio solo releía al REINICIAR el proceso — bug real
encontrado en producción, vd1sbc2: un cliente con override a un grupo
round_robin/percent recién creado seguía ruteando 100% al carrier viejo
hasta un restart manual, aunque el archivo ya estuviera regenerado bien en
disco). El htable SÍ soporta recarga en caliente real — validado contra
Kamailio 5.6.3 real en Docker antes de este cambio.

Ejecutado por FastAPI cada vez que se modifica un carrier, cliente o grupo.
"""
import os
import subprocess
import sys
from collections import defaultdict
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

DISPATCHER_LIST  = os.getenv("DISPATCHER_LIST", "/etc/kamailio/dispatcher.list")

# Offset del número de grupo de dispatcher para Grupos de ruteo — el número
# de grupo ES DIRECTAMENTE carrier_groups.id + este offset (ya no hay
# aritmética por customer_id ni distinción default/override, ver el
# rediseño "solo grupos"). El offset existe solo para nunca colisionar con
# el grupo 1 (LAN peers, gestionado aparte desde Settings > LAN Peers).
GROUP_NUMBER_OFFSET = 1000

# $var(alg) por algoritmo del grupo — ver route[OUTBOUND_TO_CARRIER] en
# kamailio.cfg.j2. 'priority' no tiene entrada — cae al $shv(carrier_alg)
# global (campo vacío en el htable, $var(alg) se queda en 0).
ALG_BY_ALGORITHM = {"percent": "11", "round_robin": "4"}


def _safe_comment(text: str) -> str:
    """
    customers.name/carrier_groups.name se embeben SIN escapar en una línea
    de comentario '#' de dispatcher.list — un cliente/reseller con permisos
    de admin podría poner un salto de línea en el nombre y usar eso para
    escaparse del comentario e inyectar directivas Kamailio arbitrarias. El
    validador de Pydantic en customers.py/reseller.py/carrier_groups.py ya
    bloquea esto en altas/ediciones nuevas — esto es la segunda capa,
    defensa en profundidad. Reemplaza cualquier carácter de control (\\n,
    \\r, tabs, etc.) por un espacio — nunca hace falta ninguno en un
    nombre real.
    """
    return "".join(c if ord(c) >= 32 and ord(c) != 127 else " " for c in text)


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
    """
    lan_peers (tabla, CRUD real vía /api/admin/lan-peers — página "Entrante"
    del panel) reemplaza el viejo settings.lan_peers (CSV suelto sin
    endpoint ni pantalla). Devuelve "host:puerto" — mismo formato que
    build_dispatcher_list() ya espera.
    """
    cur = conn.cursor()
    cur.execute("SELECT host, port FROM lan_peers ORDER BY host")
    rows = cur.fetchall()
    cur.close()
    return [f"{host}:{port}" for host, port in rows]


def fetch_customers(conn) -> list[dict]:
    """
    Ya NO hace falta pasar por customer_carriers (no existe más, ver
    rediseño "solo grupos") — el único dato que gen_dispatcher.py necesita
    de cada cliente es su routing_group_id (backend/routers/customers.py::
    assign_carrier lo crea/actualiza solo, la primera vez que se le asigna
    un carrier).
    """
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT id AS customer_id, name AS customer_name, techprefix, routing_group_id
        FROM customers WHERE status = 'active'
    """)
    rows = cur.fetchall()
    cur.close()
    return rows


def fetch_customer_prefixes(conn) -> dict:
    """
    Prefijos de campaña ADICIONALES por cliente (ver customer_prefixes) — se
    suman al techprefix principal para armar la lista completa de prefijos
    que rutean a cada cliente. Un cliente sin campañas simplemente no
    aparece acá.
    """
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        "SELECT id, customer_id, techprefix, label, routing_group_id "
        "FROM customer_prefixes"
    )
    rows = cur.fetchall()
    cur.close()
    by_customer: dict = defaultdict(list)
    for row in rows:
        by_customer[row["customer_id"]].append(row)
    return by_customer


def fetch_carrier_groups(conn) -> dict:
    """
    Grupos de ruteo — ÚNICA fuente de destinos de dispatcher.list, keyed
    por carrier_groups.id. Cada grupo trae sus miembros ya resueltos con
    host/port/outbound_prefix/cps_limit (mismos campos que
    _dispatcher_line() necesita) — la membresía del grupo ES la lista
    autoritativa, no se vuelve a cruzar contra nada más.
    """
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT
            g.id AS group_id,
            g.name AS group_name,
            g.algorithm,
            ca.id AS carrier_id,
            ca.host,
            ca.port,
            ca.outbound_prefix,
            ca.cps_limit,
            m.priority,
            m.weight
        FROM carrier_groups g
        JOIN carrier_group_members m ON m.group_id = g.id
        JOIN carriers ca ON ca.id = m.carrier_id AND ca.status = 'active'
        ORDER BY g.id, m.priority DESC
    """)
    rows = cur.fetchall()
    cur.close()

    groups: dict = {}
    for row in rows:
        gid = row["group_id"]
        if gid not in groups:
            groups[gid] = {"name": row["group_name"], "algorithm": row["algorithm"], "members": []}
        groups[gid]["members"].append({
            "carrier_id": row["carrier_id"],
            "host": row["host"],
            "port": row["port"],
            "outbound_prefix": row["outbound_prefix"],
            "cps_limit": row["cps_limit"],
            "customer_priority": row["priority"],
            "customer_weight": row["weight"],
        })
    return groups


def _dispatcher_line(group: int, row: dict, public_ip: str, weighted: bool = False) -> str:
    pfx  = row["outbound_prefix"] or ""
    attr = f"socket=udp:{public_ip}:5060;carid={row['carrier_id']}"
    if pfx:
        attr += f";prefix={pfx}"
    # cps= — límite de CPS hacia este carrier, leído por kamailio.cfg.j2
    # (route[OUTBOUND_TO_CARRIER]) para encolar en vez de rechazar el
    # excedente. NULL/0 = sin límite, mismo comportamiento de siempre.
    if row.get("cps_limit"):
        attr += f";cps={row['cps_limit']}"
    # rweight= — SOLO si el grupo tiene algorithm='percent' (weighted=True).
    # Nunca se omite en ese caso aunque customer_weight sea NULL: un
    # carrier sin peso seteado se volvería invisible para el algoritmo 11
    # (0% de tráfico silencioso) en vez de repartirse parejo — 1 es el
    # default seguro.
    if weighted:
        attr += f";rweight={row.get('customer_weight') or 1}"
    return f"{group} sip:{row['host']}:{row['port']}  0 {row['customer_priority']} {attr}"


def build_dispatcher_list(lan_peers: list[str], groups: dict) -> str:
    """
    Un grupo es una unidad atómica reusable (varios clientes/prefijos
    pueden apuntar al mismo carrier_groups.id) — se emite UNA sola vez por
    grupo, con TODOS sus miembros, sin importar cuántos prefijos lo usan.
    """
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

    lines.append("# GRUPOS DE RUTEO")
    for gid, group_def in groups.items():
        dispatcher_group = GROUP_NUMBER_OFFSET + gid
        weighted = group_def["algorithm"] == "percent"
        lines.append(
            f"# Grupo id={gid} {_safe_comment(group_def['name'])} "
            f"({group_def['algorithm']}) → dispatcher {dispatcher_group}"
        )
        for row in group_def["members"]:
            lines.append(_dispatcher_line(dispatcher_group, row, public_ip, weighted=weighted))
        lines.append("")

    return "\n".join(lines)


def build_techprefix_rows(
    customers: list[dict], customer_prefixes: dict, groups: dict
) -> list[tuple[str, int, int, str]]:
    """
    Arma las filas para techprefix_map: (techprefix, dispatcher_group,
    customer_id, alg). Un prefijo sin grupo resuelto (cliente sin carriers
    asignados todavía, o apuntando a un grupo que quedó sin miembros
    activos) simplemente NO aparece — Kamailio no lo matchea, cae a
    INBOUND_TO_ASTERISK (mismo comportamiento que "sin ruteo" de siempre).
    """
    def _resolve(routing_group_id):
        if not routing_group_id:
            return None
        group_def = groups.get(routing_group_id)
        if not group_def or not group_def["members"]:
            return None
        return group_def

    rows: list[tuple[str, int, int, str]] = []

    for cust in customers:
        if not cust["techprefix"]:
            continue
        group_def = _resolve(cust["routing_group_id"])
        if group_def is None:
            continue
        alg = ALG_BY_ALGORITHM.get(group_def["algorithm"], "")
        dispatcher_group = GROUP_NUMBER_OFFSET + cust["routing_group_id"]
        rows.append((cust["techprefix"], dispatcher_group, cust["customer_id"], alg))

    by_cid = {c["customer_id"]: c for c in customers}
    for cid, prefixes in customer_prefixes.items():
        parent = by_cid.get(cid)
        parent_gid = parent["routing_group_id"] if parent else None
        for cp in prefixes:
            if not cp["techprefix"]:
                continue
            effective_gid = cp["routing_group_id"] or parent_gid
            group_def = _resolve(effective_gid)
            if group_def is None:
                continue
            alg = ALG_BY_ALGORITHM.get(group_def["algorithm"], "")
            dispatcher_group = GROUP_NUMBER_OFFSET + effective_gid
            rows.append((cp["techprefix"], dispatcher_group, cid, alg))

    return rows


def sync_techprefix_map(conn, rows: list[tuple[str, int, int, str]]) -> None:
    """
    Reemplaza TODO el contenido de techprefix_map en una transacción —
    mismo criterio "regenerar todo, no parchear" que ya usa dispatcher.list.
    key_type/value_type fijos en 0 (simple key, string value) — formato que
    exige el módulo htable de Kamailio para auto-cargar/recargar desde DB,
    ver comentario en db/schema.sql.
    """
    cur = conn.cursor()
    cur.execute("DELETE FROM techprefix_map")
    if rows:
        cur.executemany(
            "INSERT INTO techprefix_map (key_name, key_type, value_type, key_value, expires) "
            "VALUES (%s, 0, 0, %s, 0)",
            [(techprefix, f"{grp}:{cid}:{alg}") for techprefix, grp, cid, alg in rows],
        )
    conn.commit()
    cur.close()


def reload_kamailio():
    # Dentro de Docker este proceso no tiene sudo/kamcmd — solo escribe
    # dispatcher.list/techprefix_map a rutas/tablas accesibles desde el
    # host (ver backend/Dockerfile). Un systemd path-unit en el host
    # (fuera de Docker, junto a Kamailio/RTPEngine) detecta el cambio y
    # aplica el reload privilegiado — separación real de privilegios, el
    # container nunca toca nada del SBC directamente.
    if os.getenv("VOXIKAM_SKIP_PRIVILEGED_RELOAD") == "1":
        print("  ⏭ VOXIKAM_SKIP_PRIVILEGED_RELOAD=1 — el watcher del host aplica el reload")
        return
    for cmd, label in (
        (["sudo", "kamcmd", "dispatcher.reload"], "dispatcher.reload"),
        (["sudo", "kamcmd", "htable.reload", "techmap"], "htable.reload techmap"),
    ):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                print(f"  ✓ kamcmd {label} OK")
            else:
                print(f"  ⚠ kamcmd {label}: {r.stderr.strip()}")
        except FileNotFoundError:
            print("  ⚠ kamcmd no encontrado")
        except subprocess.TimeoutExpired:
            print(f"  ⚠ kamcmd {label} timeout")


def main():
    # Mismo problema que tenía gen_nftables.py: dispatcher.log era una pared de
    # líneas "✓" sin timestamp, imposible de correlacionar con un incidente.
    print(f"gen_dispatcher.py — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    conn = get_db()
    failed = False
    try:
        lan_peers     = fetch_lan_peers(conn)
        customers     = fetch_customers(conn)
        cust_prefixes = fetch_customer_prefixes(conn)
        groups        = fetch_carrier_groups(conn)

        # dispatcher.list (recarga en caliente vía dispatcher.reload) y
        # techprefix_map (htable, recarga en caliente vía htable.reload) son
        # independientes — antes vivían en el mismo try/except y un error
        # escribiendo dispatcher.list (ej. permisos, disco lleno) abortaba
        # ANTES de llegar a sync_techprefix_map(), dejando un cambio de grupo
        # de ruteo sin aplicarse en caliente aunque el htable sí soporte
        # hacerlo — solo un reinicio completo de Kamailio lo reflejaba.
        # Encontrado en producción (vd1sbc2): ProtectSystem=full sin
        # ReadWritePaths=/etc/kamailio (ver systemd/voxikam-backend.service)
        # hacía fallar el write SIEMPRE, bloqueando el htable también.
        try:
            disp = build_dispatcher_list(lan_peers, groups)
            Path(DISPATCHER_LIST).write_text(disp)
            print(f"  ✓ {DISPATCHER_LIST} actualizado ({len(groups)} grupos)")
        except Exception as e:
            print(f"  ✗ Error escribiendo {DISPATCHER_LIST}: {e}")
            failed = True

        try:
            rows = build_techprefix_rows(customers, cust_prefixes, groups)
            sync_techprefix_map(conn, rows)
            print(f"  ✓ techprefix_map actualizado ({len(rows)} prefijos)")
        except Exception as e:
            print(f"  ✗ Error actualizando techprefix_map: {e}")
            failed = True

        reload_kamailio()
    except Exception as e:
        print(f"  ✗ Error: {e}")
        failed = True
    finally:
        conn.close()

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
