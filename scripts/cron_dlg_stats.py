#!/usr/bin/env python3
# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
cron_dlg_stats.py — Snapshot de Kamailio cada 5 segundos.

Ejecuta en un loop interno (10 × 5s = 50s) dentro del cron por-minuto — mismos
50s/10s de margen que antes con INTERVAL=10/ITERATIONS=5, solo más granular.
Guarda en /var/lib/voxikam/live_snapshot.json el JSON completo con:
  - resumen:            totales (activas, timbrando, total)
  - resumen_por_prefijo: por techprefix (para el widget "Activas por cliente")
  - llamadas:           detalle state=4 (contestadas confirmadas)

Extracción de prefijo (v2.41.1): antes el AWK asumía un largo FIJO de 4
caracteres (`substr(destino_completo, 1, 4)`) — pero el techprefix real es
de largo VARIABLE por cliente, y el autogenerador de sub-clientes de
reseller arranca en 10000 (5 dígitos). Con un prefijo de 5 dígitos el
substr(1,4) truncaba mal y el resultado nunca matcheaba ningún
`customers.techprefix` real — este widget quedaba roto en silencio para
cualquier cliente de 5+ dígitos. Ahora se hace un longest-prefix-match real
contra la lista de prefijos conocidos (customers.techprefix +
customer_prefixes.techprefix), igual criterio que usa el billing por
tarifa — se resuelve una vez por minuto (no es necesario más seguido, un
prefijo nuevo tarda como máximo ~1 min en aparecer acá).
"""
import json
import os
import subprocess
import sys
import time
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
INTERVAL      = 5    # segundos entre capturas
ITERATIONS    = 10   # 10 × 5s = 50s → deja 10s buffer antes del siguiente cron


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
    )


def fetch_known_prefixes(conn) -> list[str]:
    """customers.techprefix (principal) + customer_prefixes.techprefix (campaña),
    ordenados por largo descendente para que el AWK haga longest-prefix-match.

    Filtro defensivo `isdigit()`: el modelo Pydantic (customers.py::CustomerIn)
    ya exige solo dígitos al crear/editar, pero esto son datos ya guardados en
    la DB (posiblemente de antes de esa validación) — un valor con coma
    rompería el join de abajo (se leería como dos prefijos), y cualquier otro
    carácter raro podría confundir al AWK. Mejor descartarlo silenciosamente
    acá (ese prefijo puntual no resuelve nombre en el snapshot) que dejar que
    ensucie la lista completa."""
    cur = conn.cursor()
    cur.execute("SELECT techprefix FROM customers WHERE techprefix != ''")
    prefixes = [row[0] for row in cur.fetchall()]
    cur.execute("SELECT techprefix FROM customer_prefixes")
    prefixes += [row[0] for row in cur.fetchall()]
    cur.close()
    return sorted({p for p in prefixes if p and p.isdigit()}, key=len, reverse=True)

# Awk que parsea dlg.briefing y emite JSON directo.
# known_str (-v, inyectado desde Python): prefijos conocidos separados por
# coma, ya ordenados por largo descendente — el primer match en el loop es
# el más largo, o sea el correcto (longest-prefix-match).
AWK_DLG = r"""
BEGIN {
    llamadas_json=""
    first_llamada=1
    timbrando=0
    ongoing=0
    n_known=split(known_str, known, ",")
}

/^\{/ {
    from=""
    to=""
    callid=""
    start=0
    state=0
}

/from_uri:/ {
    sub(/^[ \t]*from_uri:[ \t]*/, "")
    from=$0
}

/to_uri:/ {
    sub(/^[ \t]*to_uri:[ \t]*/, "")
    to=$0
}

/call-id:/ {
    sub(/^[ \t]*call-id:[ \t]*/, "")
    callid=$0
}

/start_ts:/ {
    start=$2
}

/state:/ {
    state=$2
}

/^\}/ {
    origen=from
    destino=to

    sub(/^sip:/, "", origen)
    sub(/^sip:/, "", destino)

    split(origen,   orig_p, "@")
    split(destino,  dest_p, "@")

    numero_origen=orig_p[1]
    ip_origen=orig_p[2]
    destino_completo=dest_p[1]

    prefijo=""
    for (k=1; k<=n_known; k++) {
        plen=length(known[k])
        if (plen > 0 && substr(destino_completo, 1, plen) == known[k]) {
            prefijo=known[k]
            break
        }
    }
    if (prefijo == "") {
        prefijo="0000"
        numero_destino=destino_completo
    } else {
        numero_destino=substr(destino_completo, length(prefijo)+1)
    }

    if (state == 1 || state == 2 || state == 3) {
        timbrando++
        prefijo_timbrando[prefijo]++
        prefijo_total[prefijo]++
    }
    else if (state == 4) {
        ongoing++
        prefijo_activas[prefijo]++
        prefijo_total[prefijo]++

        if (start > 0) {
            dur=systime()-start
            if (dur < 0) dur=0
            tiempo=sprintf("%02d:%02d:%02d", int(dur/3600), int((dur%3600)/60), dur%60)

            if (!first_llamada) llamadas_json=llamadas_json ",\n"

            llamadas_json=llamadas_json \
                "    {\n" \
                "      \"call_id\": \""   callid          "\",\n" \
                "      \"ip_origen\": \"" ip_origen       "\",\n" \
                "      \"origen\": \""    numero_origen   "\",\n" \
                "      \"destino\": \""   numero_destino  "\",\n" \
                "      \"prefijo\": \""   prefijo         "\",\n" \
                "      \"start_ts\": "    start           ",\n" \
                "      \"tiempo\": \""    tiempo          "\"\n" \
                "    }"
            first_llamada=0
        }
    }
}

END {
    total=timbrando+ongoing

    printf "{\n"
    printf "  \"resumen\": {\n"
    printf "    \"llamadas_activas\": %d,\n", ongoing
    printf "    \"timbrando\": %d,\n", timbrando
    printf "    \"total\": %d\n", total
    printf "  },\n"

    printf "  \"resumen_por_prefijo\": [\n"
    first_p=1
    for (p in prefijo_total) {
        if (!first_p) printf ",\n"
        printf "    {\n"
        printf "      \"prefijo\": \"%s\",\n", p
        printf "      \"llamadas_activas\": %d,\n", prefijo_activas[p]+0
        printf "      \"timbrando\": %d,\n", prefijo_timbrando[p]+0
        printf "      \"total\": %d\n", prefijo_total[p]+0
        printf "    }"
        first_p=0
    }
    printf "\n  ],\n"

    printf "  \"llamadas\": [\n"
    if (llamadas_json != "") printf "%s\n", llamadas_json
    printf "  ]\n"
    printf "}\n"
}
"""


def _kill(p) -> None:
    """Mata y reapea un proceso que quedó colgado — sin esto, un kamcmd que
    no responde queda vivo para siempre (invisible para el resto del script,
    pero sigue existiendo y compitiendo por el socket de control de Kamailio).
    Llamado cada 10s: si kamcmd empieza a colgarse, sin este cleanup se
    acumularían procesos zombie cada vez más rápido — empeorando lo mismo que
    causó el problema."""
    if p is None or p.poll() is not None:
        return
    try:
        p.kill()
        p.wait(timeout=2)
    except Exception:
        pass


def capture(known_prefixes: list[str]) -> dict | None:
    """None = falló la captura — el caller NO debe pisar el snapshot anterior
    con esto. Antes acá se devolvía un snapshot con todo en cero, que
    `live.py` no puede distinguir de "no hay llamadas activas de verdad" —
    un hipo transitorio de kamcmd hacía que el panel Live mostrara 0/0/0
    arriba mientras la tabla de llamadas (que lee de otra fuente) seguía
    mostrando las llamadas reales. Reportado por el usuario en producción.

    Segundo caso real encontrado (v2.24.15): con suficientes diálogos activos,
    `kamcmd dlg.briefing` responde "ERROR: reply too big" en vez del dump
    esperado — kamcmd tiene un límite de tamaño de respuesta y el dump
    completo (from_uri/to_uri/call-id por cada diálogo) ya lo supera con el
    volumen real de este SBC. Ese texto de error no lanza ninguna excepción
    en Python: antes se pasaba derecho a `awk`, que no matchea ninguno de sus
    patrones (`/^\\{/`, `/^\\}/`, etc.) contra una línea de error y termina
    "exitosamente" con 0 diálogos — indistinguible de que no hay tráfico.
    Por eso ahora se lee la salida de kamcmd por separado antes de pasarla a
    awk, y se trata "ERROR" como falla real."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    p1 = p2 = None
    try:
        p1 = subprocess.Popen(
            ["kamcmd", "dlg.briefing", "ftcISs"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        kam_out, _ = p1.communicate(timeout=10)
        if kam_out.strip().startswith(b"ERROR"):
            raise RuntimeError(f"kamcmd: {kam_out.decode(errors='replace').strip()}")

        known_str = ",".join(known_prefixes)
        p2 = subprocess.Popen(
            ["awk", "-v", f"known_str={known_str}", AWK_DLG],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        out, _ = p2.communicate(input=kam_out, timeout=10)
        snap = json.loads(out.decode())
        snap["ts"] = now
        return snap
    except Exception as e:
        print(f"  ⚠ capture: {e} — snapshot anterior se mantiene sin tocar", file=sys.stderr)
        return None
    finally:
        _kill(p1)
        _kill(p2)


def main():
    SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Se resuelve una vez por minuto (no hace falta más seguido) — si la DB
    # no responde, se sigue con la lista vacía en vez de abortar todo el
    # snapshot: mismo criterio best-effort que ya usa capture() con kamcmd.
    known_prefixes: list[str] = []
    try:
        conn = get_db()
        try:
            known_prefixes = fetch_known_prefixes(conn)
        finally:
            conn.close()
    except Exception as e:
        print(f"  ⚠ no se pudo leer prefijos conocidos de la DB: {e}", file=sys.stderr)

    for i in range(ITERATIONS):
        t0 = time.time()
        try:
            snap = capture(known_prefixes)
            if snap is None:
                pass  # no pisar el snapshot bueno anterior con uno falso
            else:
                SNAPSHOT_FILE.write_text(json.dumps(snap))
                SNAPSHOT_FILE.chmod(0o644)   # legible por voxikam (cron_timeseries)
                r = snap.get("resumen", {})
                print(f"  ✓ {snap['ts']} activas={r.get('llamadas_activas',0)} "
                      f"timbrando={r.get('timbrando',0)} total={r.get('total',0)}")
        except Exception as e:
            print(f"  ✗ {e}", file=sys.stderr)

        if i < ITERATIONS - 1:
            elapsed = time.time() - t0
            time.sleep(max(0, INTERVAL - elapsed))


if __name__ == "__main__":
    main()
