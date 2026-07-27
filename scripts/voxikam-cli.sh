#!/bin/bash
# voxikam — atajo de administración para los servicios de VoxiKam.
# Evita tener que acordarse de los nombres reales de las unidades systemd
# (voxikam-backend, voxikam-frontend, etc.) para las tareas del día a día.
# Instalado como symlink en /usr/local/bin/voxikam por deploy.sh.
set -euo pipefail

_usage() {
    cat <<'EOF'
voxikam — administración rápida de servicios VoxiKam

Uso:
  voxikam -s [servicio]         Ver estado
  voxikam -r [servicio]         Reiniciar
  voxikam -p [servicio]         Detener
  voxikam -l [servicio] [-n N]  Ver logs (en vivo por defecto; -n N = últimas N líneas)

Servicios (si no se indica, usa "app"):
  back  front  hep  kamailio  rtpengine  autotune  app  all
    app = back + front (la aplicación web, sin el SBC)
    all = todos, incluido Kamailio/RTPEngine

Ejemplos:
  voxikam -s app
  voxikam -r back
  voxikam -l kamailio -n 100
  voxikam -s all

Nota: -r y -p necesitan sudo/root (systemctl restart/stop). -s y -l no.
El panel web (Sistema → Salud) muestra el mismo estado y las últimas líneas
de log de solo lectura — para reiniciar o seguir logs en vivo, usar esta CLI.
EOF
}

declare -A SVC_MAP=(
    [back]=voxikam-backend      [backend]=voxikam-backend
    [front]=voxikam-frontend    [frontend]=voxikam-frontend
    [hep]=voxikam-hep
    [autotune]=voxikam-autotune
    [kamailio]=kamailio         [kam]=kamailio
    [rtpengine]=rtpengine       [rtp]=rtpengine
    [clickhouse]=clickhouse-server [ch]=clickhouse-server
)

_units_for() {
    case "$1" in
        app) echo "voxikam-backend voxikam-frontend" ;;
        all) echo "voxikam-backend voxikam-frontend voxikam-hep kamailio rtpengine clickhouse-server" ;;
        *)   echo "${SVC_MAP[$1]:-}" ;;
    esac
}

_as_root() { if [[ $EUID -eq 0 ]]; then "$@"; else sudo "$@"; fi; }

if [[ $# -eq 0 ]]; then _usage; exit 1; fi
ACTION="$1"; shift || true
if [[ "$ACTION" == "-h" || "$ACTION" == "--help" ]]; then _usage; exit 0; fi

TARGET="app"
LINES=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        -n) LINES="${2:-}"; shift 2 ;;
        *)  TARGET="$1"; shift ;;
    esac
done

UNITS=$(_units_for "$TARGET")
if [[ -z "$UNITS" ]]; then
    echo "Servicio desconocido: '$TARGET'" >&2
    _usage
    exit 1
fi

case "$ACTION" in
    -s)
        for u in $UNITS; do
            echo "── $u ──────────────────────────────"
            systemctl status "$u" --no-pager -l 2>&1 | head -n 10
            echo
        done
        ;;
    -r)
        for u in $UNITS; do
            printf 'Reiniciando %s... ' "$u"
            if _as_root systemctl restart "$u"; then echo "OK"; else echo "FALLÓ"; fi
        done
        ;;
    -p)
        for u in $UNITS; do
            printf 'Deteniendo %s... ' "$u"
            if _as_root systemctl stop "$u"; then echo "OK"; else echo "FALLÓ"; fi
        done
        ;;
    -l)
        JARGS=()
        for u in $UNITS; do JARGS+=(-u "$u"); done
        if [[ -n "$LINES" ]]; then
            journalctl "${JARGS[@]}" -n "$LINES" --no-pager
        else
            journalctl "${JARGS[@]}" -f
        fi
        ;;
    *)
        echo "Acción desconocida: '$ACTION'" >&2
        _usage
        exit 1
        ;;
esac
