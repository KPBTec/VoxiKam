#!/usr/bin/env python3
# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
cron_timeseries.py — snapshot de llamadas contestadas por minuto.

Lee el snapshot que cron_dlg_stats.py actualiza cada 10s en:
  /var/lib/voxikam/live_snapshot.json

Usa DATE_FORMAT(NOW(),...) de MySQL para el timestamp — así el backend
que también usa NOW() siempre encuentra los datos sin importar la zona
horaria del servidor Python.

Retención: 25 horas (auto-purge).

Resolución de carrier (v2.41.1): antes se grababa carrier_id=0 hardcodeado
— el dashboard en vivo mostraba "Sin nombre" en el gráfico "Por carrier"
porque nunca se resolvía de verdad. Kamailio SÍ sabe el carrier real por
llamada ($dlg_var(carrier_id) en kamailio.cfg.j2), pero el RPC liviano que
usa cron_dlg_stats.py (kamcmd dlg.briefing) solo trae campos fijos
(from/to/callid/estado/tiempos) — no puede traer variables custom, y el
RPC que sí las trae (dlg.list) ya reventó en producción con "reply too big"
al dumpear todos los diálogos con el volumen real de este SBC (v2.24.15).
En vez de tocar el routing SIP en vivo, se resuelve el carrier desde
sip_traces (ClickHouse, HEP): cada paquete SIP ya trae dst_ip real — para
un INVITE saliente hacia el carrier, dst_ip = la IP pública del carrier
(carriers.host). Se cruza call_id (de dlg.briefing) → dst_ip (ClickHouse)
→ carrier_id (MariaDB), sin ninguna llamada nueva a Kamailio.
"""
import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pymysql
from dotenv import load_dotenv

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

SNAPSHOT_FILE = Path("/var/lib/voxikam/live_snapshot.json")


def get_db():
    url       = os.getenv("DATABASE_URL_SYNC", "")
    parts     = url.replace("mysql+pymysql://", "").split("@")
    user_pass = parts[0].split(":")
    host_db   = parts[1].split("/")
    host_port = host_db[0].split(":")
    return pymysql.connect(
        host=host_port[0],
        port=int(host_port[1]) if len(host_port) > 1 else 3306,
        user=user_pass[0],
        password=user_pass[1],
        database=host_db[1],
        charset="utf8mb4",
        autocommit=False,
    )


def get_ch():
    """None si no hay CLICKHOUSE_URL configurado o falla la conexión — la
    resolución de carrier es best-effort, nunca debe tumbar el snapshot de
    clientes (que siempre funcionó sin ClickHouse)."""
    url = os.getenv("CLICKHOUSE_URL", "")
    if not url:
        return None
    try:
        import clickhouse_connect
        from urllib.parse import urlparse
        u = urlparse(url)
        return clickhouse_connect.get_client(
            host=u.hostname or "127.0.0.1",
            port=u.port or 8123,
            username=u.username or "voxikam",
            password=u.password or "",
            database=(u.path or "/sip_platform").lstrip("/"),
        )
    except Exception as e:
        print(f"  ⚠ ClickHouse no disponible ({e}) — carrier quedará sin resolver")
        return None


def _resolve_carriers(ch, call_ids: list[str], carrier_by_host: dict[str, int]) -> dict[str, int]:
    """call_id → carrier_id, cruzando contra el dst_ip real de sip_traces."""
    if not ch or not call_ids or not carrier_by_host:
        return {}
    hosts = list(carrier_by_host.keys())
    try:
        result = ch.query(
            "SELECT call_id, dst_ip FROM sip_traces "
            "WHERE call_id IN {call_ids:Array(String)} AND dst_ip IN {hosts:Array(String)} "
            "AND captured_at >= now() - INTERVAL 2 HOUR",
            parameters={"call_ids": call_ids, "hosts": hosts},
        )
    except Exception as e:
        print(f"  ⚠ query sip_traces falló: {e}")
        return {}
    mapping: dict[str, int] = {}
    for call_id, dst_ip in result.result_rows:
        mapping.setdefault(call_id, carrier_by_host[dst_ip])
    return mapping


def run(conn, ch=None):
    # ── 1) Leer snapshot (generado por cron_dlg_stats.py cada 10s) ──────────
    try:
        snap = json.loads(SNAPSHOT_FILE.read_text())
    except Exception as e:
        print(f"  ⚠ no se pudo leer snapshot: {e}")
        return

    # llamadas: detalle state=4 (confirmadas) — trae call_id por llamada,
    # necesario para cruzar contra sip_traces y resolver el carrier real.
    llamadas = snap.get("llamadas", [])
    if not llamadas:
        ts_snap = snap.get("ts", "?")
        print(f"  ✓ {ts_snap}: sin llamadas activas en snapshot")
        return

    # ── 2) Resolver prefijo → customer_id, host → carrier_id ────────────────
    # prefix_map incluye tanto el techprefix principal (customers.techprefix)
    # como los de campaña (customer_prefixes) — cron_dlg_stats.py ya resuelve
    # el `prefijo` exacto contra la misma unión, con longest-prefix-match.
    cur = conn.cursor()
    cur.execute(
        "SELECT id, techprefix FROM customers "
        "WHERE techprefix IS NOT NULL AND techprefix != ''"
    )
    prefix_map = {row[1]: row[0] for row in cur.fetchall()}
    cur.execute("SELECT customer_id, techprefix FROM customer_prefixes")
    prefix_map.update({row[1]: row[0] for row in cur.fetchall()})

    cur.execute("SELECT id, host FROM carriers WHERE host IS NOT NULL AND host != ''")
    carrier_by_host = {row[1]: row[0] for row in cur.fetchall()}

    call_ids = [c["call_id"] for c in llamadas if c.get("call_id")]
    call_carrier = _resolve_carriers(ch, call_ids, carrier_by_host)

    # ── 3) Agrupar llamadas activas por (customer_id, carrier_id) ───────────
    counts: dict[tuple, int] = defaultdict(int)
    for c in llamadas:
        cust_id = prefix_map.get(c.get("prefijo", ""))
        if not cust_id:
            continue
        carrier_id = call_carrier.get(c.get("call_id", ""), 0)
        counts[(cust_id, carrier_id)] += 1

    # ── 4) Insertar usando NOW() de MySQL (sin depender de la TZ del servidor) ─
    rows_saved = 0
    total_calls = 0
    for (cust_id, carrier_id), count in counts.items():
        cur.execute("""
            INSERT INTO calls_timeseries
                (ts, customer_id, carrier_id, call_count, answered_count, failed_count)
            VALUES (DATE_FORMAT(NOW(), %s), %s, %s, %s, %s, 0)
            ON DUPLICATE KEY UPDATE
                call_count     = VALUES(call_count),
                answered_count = VALUES(answered_count)
        """, ("%Y-%m-%d %H:%i:00", cust_id, carrier_id, count, count))
        rows_saved  += 1
        total_calls += count

    # ── 5) Purgar registros > 25 horas ──────────────────────────────────────
    cur.execute("DELETE FROM calls_timeseries WHERE ts < NOW() - INTERVAL 25 HOUR")
    purged = cur.rowcount

    conn.commit()
    cur.close()

    ts_snap = snap.get("ts", "?")
    unresolved = sum(1 for c in llamadas if not call_carrier.get(c.get("call_id", "")))
    print(f"  ✓ {ts_snap}: {total_calls} contestadas en {rows_saved} fila(s)"
          + (f" — {unresolved} sin carrier resuelto" if unresolved else "")
          + (f" — purge: {purged}" if purged else ""))


def main():
    print(f"cron_timeseries.py — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    conn = get_db()
    ch = get_ch()
    try:
        run(conn, ch)
    except Exception as e:
        print(f"  ✗ Error: {e}")
        raise
    finally:
        conn.close()
        if ch is not None:
            try:
                ch.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
