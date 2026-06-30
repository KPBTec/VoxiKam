#!/usr/bin/env python3
# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
cron_dlg_stats.py — Snapshot de Kamailio cada 10 segundos.

Ejecuta en un loop interno (5 × 10s = 50s) dentro del cron por-minuto.
Guarda en /var/lib/voxikam/live_snapshot.json el JSON completo con:
  - resumen:            totales (activas, timbrando, total)
  - resumen_por_prefijo: por techprefix (para el widget "Activas por cliente")
  - llamadas:           detalle state=4 (contestadas confirmadas)
"""
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

SNAPSHOT_FILE = Path("/var/lib/voxikam/live_snapshot.json")
INTERVAL      = 10   # segundos entre capturas
ITERATIONS    = 5    # 5 × 10s = 50s → deja 10s buffer antes del siguiente cron

# Awk que parsea dlg.briefing y emite JSON directo
AWK_DLG = r"""
BEGIN {
    llamadas_json=""
    first_llamada=1
    timbrando=0
    ongoing=0
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

    if (length(destino_completo) >= 4) {
        prefijo=substr(destino_completo, 1, 4)
        numero_destino=substr(destino_completo, 5)
    } else {
        prefijo="0000"
        numero_destino=destino_completo
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


def capture() -> dict:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        p1 = subprocess.Popen(
            ["kamcmd", "dlg.briefing", "ftcISs"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        p2 = subprocess.Popen(
            ["awk", AWK_DLG],
            stdin=p1.stdout, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        p1.stdout.close()
        out, _ = p2.communicate(timeout=10)
        snap = json.loads(out.decode())
        snap["ts"] = now
        return snap
    except Exception as e:
        print(f"  ⚠ capture: {e}", file=sys.stderr)
        return {"ts": now, "resumen": {"llamadas_activas": 0, "timbrando": 0, "total": 0},
                "resumen_por_prefijo": [], "llamadas": []}


def main():
    SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
    for i in range(ITERATIONS):
        t0 = time.time()
        try:
            snap = capture()
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
