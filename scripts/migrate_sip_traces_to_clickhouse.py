#!/usr/bin/env python3
# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Migración manual, única: backfill de las últimas 48h de sip_traces (MariaDB)
hacia ClickHouse + corte de escritura de backend/hep_listener.py.

Motivo: sip_traces crecía ~8.5GB/día con 90 días de retención configurados
(settings.sip_traces_retention_hours) — insostenible en el disco del server.
Se decidió mover la tabla completa a ClickHouse (TTL nativo, compresión
columnar). Del histórico ya acumulado en MariaDB solo se conservan las
últimas 48h (decisión explícita del usuario) — el resto se descarta con
TRUNCATE en la fase --truncate, nunca DELETE.

Requiere que backend/hep_listener.py y backend/routers/traces.py YA estén
desplegados con el código que apunta a ClickHouse antes de correr --cutover
(el servicio arranca de nuevo escribiendo al destino correcto).

Diseño en DOS fases separadas a propósito — nunca combinar lo reversible con
lo irreversible bajo un mismo flag:

  1. --cutover   Backfill de 48h + detiene voxikam-hep + copia final + valida
                 conteo MySQL == ClickHouse (gate obligatorio, aborta si no
                 coincide) + reinicia voxikam-hep apuntando a ClickHouse.
                 MariaDB queda INTACTA — nada destructivo todavía.

  2. --truncate  Solo TRUNCATE TABLE sip_traces en MariaDB (recupera el disco
                 al instante). Correr ÚNICAMENTE después de confirmar a mano
                 que el panel /traces funciona contra ClickHouse (buscar una
                 llamada de las últimas 48h, forzar una llamada nueva y verla
                 en vivo, exportar un .pcap) — este script no lo verifica por
                 vos, es una decisión humana con datos reales en pantalla.

Uso:
    venv/bin/python3 scripts/migrate_sip_traces_to_clickhouse.py             # diagnóstico
    venv/bin/python3 scripts/migrate_sip_traces_to_clickhouse.py --cutover
    venv/bin/python3 scripts/migrate_sip_traces_to_clickhouse.py --truncate
"""
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import clickhouse_connect
import pymysql
from dotenv import load_dotenv
import os

_marker = Path("/etc/voxikam.conf")
if _marker.exists():
    for _line in _marker.read_text().splitlines():
        if _line.startswith("INSTALL_DIR="):
            _install = Path(_line.split("=", 1)[1].strip()); break
    else:
        _install = Path(__file__).parent.parent
else:
    _install = Path(__file__).parent.parent
load_dotenv(_install / "backend" / ".env")

BACKFILL_HOURS = 48
BATCH_SIZE = 50_000

_COLUMNS = (
    "id", "call_id", "captured_at", "src_ip", "src_port", "dst_ip", "dst_port",
    "sip_method", "sip_status", "from_uri", "to_uri",
    "request_uri", "user_agent", "via_branch", "cseq", "reason", "raw_message",
)
_SELECT_COLS = ", ".join(_COLUMNS)
_FROM_URI_IDX = _COLUMNS.index("from_uri")
_TO_URI_IDX = _COLUMNS.index("to_uri")


def _sanitize(row: tuple) -> tuple:
    """from_uri/to_uri son String no-nullable en ClickHouse (ver
    db/clickhouse_schema.sql) pero sí son NULL-ables en MySQL — sin esto,
    insertar un NULL de MySQL en una columna no-nullable de ClickHouse falla."""
    row = list(row)
    if row[_FROM_URI_IDX] is None:
        row[_FROM_URI_IDX] = ""
    if row[_TO_URI_IDX] is None:
        row[_TO_URI_IDX] = ""
    return tuple(row)


def get_mysql():
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


def get_clickhouse():
    u = urlparse(os.getenv("CLICKHOUSE_URL", ""))
    return clickhouse_connect.get_client(
        host=u.hostname or "127.0.0.1",
        port=u.port or 8123,
        username=u.username or "voxikam",
        password=u.password or "",
        database=(u.path or "/sip_platform").lstrip("/"),
    )


def _min_id_last_48h(mysql) -> int | None:
    cur = mysql.cursor()
    cur.execute(
        "SELECT MIN(id) FROM sip_traces WHERE captured_at >= NOW() - INTERVAL %s HOUR",
        (BACKFILL_HOURS,),
    )
    (min_id,) = cur.fetchone()
    cur.close()
    return min_id


def _count_from(mysql, min_id: int) -> int:
    cur = mysql.cursor()
    cur.execute("SELECT COUNT(*) FROM sip_traces WHERE id >= %s", (min_id,))
    (n,) = cur.fetchone()
    cur.close()
    return n


def _ch_count_from(ch, min_id: int) -> int:
    return ch.query(
        "SELECT count() FROM sip_traces WHERE id >= {min_id:UInt64}",
        parameters={"min_id": min_id},
    ).result_rows[0][0]


def _copy_batches(mysql, ch, last_copied_id: int) -> int:
    """Copia en lotes desde last_copied_id (exclusivo) hasta agotar lo disponible.
    Devuelve el último id copiado. No asume nada sobre si hay escritura
    concurrente — un caller puede llamarla más de una vez (fase de catch-up)."""
    cur = mysql.cursor()
    total = 0
    while True:
        cur.execute(
            f"SELECT {_SELECT_COLS} FROM sip_traces WHERE id > %s ORDER BY id LIMIT %s",
            (last_copied_id, BATCH_SIZE),
        )
        batch = cur.fetchall()
        if not batch:
            break
        batch = [_sanitize(row) for row in batch]
        ch.insert(table="sip_traces", data=batch, column_names=_COLUMNS)
        last_copied_id = batch[-1][0]
        total += len(batch)
        print(f"    copiadas {len(batch):,} filas (hasta id={last_copied_id}) — acumulado {total:,}")
        if len(batch) < BATCH_SIZE:
            break  # lote parcial = ya no hay más filas pendientes en este punto
    cur.close()
    return last_copied_id


def cmd_diagnose():
    mysql = get_mysql()
    min_id = _min_id_last_48h(mysql)
    if min_id is None:
        print(f"No hay filas en sip_traces de las últimas {BACKFILL_HOURS}h — nada que migrar.")
        return
    n = _count_from(mysql, min_id)
    print(f"Backfill pendiente: {n:,} filas desde id={min_id} (últimas {BACKFILL_HOURS}h).")
    print(
        "\nModo diagnóstico (sin flags, no se aplicó nada). Pasos:\n"
        "  1) venv/bin/python3 scripts/migrate_sip_traces_to_clickhouse.py --cutover\n"
        "     (backfill + corte de voxikam-hep hacia ClickHouse — MariaDB queda intacta)\n"
        "  2) Verificar a mano en el panel /traces que todo funciona contra ClickHouse\n"
        "  3) venv/bin/python3 scripts/migrate_sip_traces_to_clickhouse.py --truncate\n"
        "     (recién ahí se libera el disco de MariaDB)"
    )


def cmd_cutover():
    mysql = get_mysql()
    ch = get_clickhouse()

    min_id = _min_id_last_48h(mysql)
    has_backfill = min_id is not None

    if has_backfill:
        print(f"→ Backfill inicial desde id={min_id} (voxikam-hep sigue escribiendo a MariaDB)...")
        last_id = _copy_batches(mysql, ch, min_id - 1)
    else:
        print(f"No hay filas en sip_traces de las últimas {BACKFILL_HOURS}h — nada que copiar, "
              "igual se corta la escritura hacia ClickHouse.")
        last_id = 0

    print("→ Deteniendo voxikam-hep (systemctl stop) — desde acá, cero escrituras nuevas a MariaDB...")
    subprocess.run(["systemctl", "stop", "voxikam-hep"], check=True)

    if has_backfill:
        print("→ Catch-up final (lo que se acumuló hasta el stop)...")
        last_id = _copy_batches(mysql, ch, last_id)

        print("→ Verificando conteo MariaDB == ClickHouse...")
        mysql_n = _count_from(mysql, min_id)
        ch_n = _ch_count_from(ch, min_id)
        if mysql_n != ch_n:
            print(f"  ✗ MISMATCH: MariaDB={mysql_n:,} ClickHouse={ch_n:,} — ABORTANDO, "
                  "MariaDB NO se toca, voxikam-hep sigue detenido. Revisar a mano antes de reintentar.")
            sys.exit(1)
        print(f"  ✓ Coinciden: {mysql_n:,} filas en ambos lados.")

    print("→ Arrancando voxikam-hep (ya con el código que escribe a ClickHouse)...")
    subprocess.run(["systemctl", "start", "voxikam-hep"], check=True)
    time.sleep(2)
    status = subprocess.run(["systemctl", "is-active", "voxikam-hep"],
                             capture_output=True, text=True).stdout.strip()
    print(f"  systemctl is-active voxikam-hep → {status}")

    print(
        "\n✓ Corte completo. MariaDB sigue con sus datos intactos (nada se borró).\n"
        "Verificar a mano antes de --truncate:\n"
        "  - journalctl -u voxikam-hep -n 20   (sin errores)\n"
        "  - cat /var/lib/voxikam/hep_stats.json   (timestamp avanzando)\n"
        "  - panel /traces: buscar una llamada de las últimas 48h (viene del backfill)\n"
        "  - forzar una llamada de prueba y confirmar que aparece en vivo\n"
        "  - exportar un .pcap y abrirlo en Wireshark\n"
        "Si algo falla: systemctl stop voxikam-hep && git checkout <commit-anterior> -- "
        "backend/hep_listener.py backend/routers/traces.py && systemctl restart voxikam-hep voxikam-backend"
    )


def cmd_truncate():
    mysql = get_mysql()
    confirm = input(
        "Esto va a TRUNCATE TABLE sip_traces en MariaDB — irreversible, borra TODO lo que "
        "quedó ahí (ya debería estar migrado a ClickHouse por --cutover).\n"
        "¿Ya verificaste el panel /traces contra ClickHouse? Escribí 'si' para continuar: "
    )
    if confirm.strip().lower() != "si":
        print("Cancelado — no se tocó nada.")
        return
    cur = mysql.cursor()
    cur.execute("TRUNCATE TABLE sip_traces")
    cur.close()
    print("✓ sip_traces truncada en MariaDB — espacio recuperado.")


def main():
    if "--cutover" in sys.argv:
        cmd_cutover()
    elif "--truncate" in sys.argv:
        cmd_truncate()
    else:
        cmd_diagnose()


if __name__ == "__main__":
    main()
