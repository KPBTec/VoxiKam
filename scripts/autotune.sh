#!/bin/bash
# VoxiKam — autotuneo de recursos (CPU/RAM reales del host).
#
# Corre en dos momentos, con distinto nivel de riesgo:
#   1. Desde deploy.sh (--no-restart): Kamailio puede tener llamadas en vivo
#      AHORA MISMO — solo actualiza los archivos de config y avisa, nunca
#      reinicia solo (mismo principio que el resto de esta sesión).
#   2. Desde voxikam-autotune.service, en cada arranque del sistema (sin
#      --no-restart): si el servidor se reinició (resize de CPU/RAM en el
#      proveedor cloud + reboot), no hay llamadas en vivo que proteger en ese
#      momento — ahí SÍ reinicia y valida automáticamente.
set -euo pipefail

NO_RESTART=0
[[ "${1:-}" == "--no-restart" ]] && NO_RESTART=1

log() { logger -t voxikam-autotune "$*"; echo "[voxikam-autotune] $*"; }

HOST_CPUS=$(nproc)
HOST_RAM_MB=$(awk '/^MemTotal:/{print int($2/1024)}' /proc/meminfo)
log "Host detectado: ${HOST_CPUS} vCPU, ${HOST_RAM_MB}MB RAM"

# ── Workers del backend (uvicorn) ────────────────────────────────────────────
WORKERS=$(( HOST_CPUS > 1 ? HOST_CPUS - 1 : 1 ))
[[ $WORKERS -gt 16 ]] && WORKERS=16

_BACKEND_UNIT="/etc/systemd/system/voxikam-backend.service"
_BACKEND_CHANGED=0
if [[ -f "$_BACKEND_UNIT" ]]; then
    _current_workers=$(grep -oP -- '--workers \K[0-9]+' "$_BACKEND_UNIT" || echo "")
    if [[ "$_current_workers" != "$WORKERS" ]]; then
        sed -i -E "s/--workers [0-9]+/--workers ${WORKERS}/" "$_BACKEND_UNIT"
        _BACKEND_CHANGED=1
        log "voxikam-backend: workers ${_current_workers:-?} → ${WORKERS}"
    fi
fi

# ── children= de Kamailio (procesos SIP, 1:1 con vCPU) ───────────────────────
KAMAILIO_CHILDREN=$HOST_CPUS
_KAMAILIO_CFG="/etc/kamailio/kamailio.cfg"
_KAMAILIO_CHANGED=0
if [[ -f "$_KAMAILIO_CFG" ]]; then
    _current_children=$(grep -oP '^children=\K[0-9]+' "$_KAMAILIO_CFG" || echo "")
    if [[ "$_current_children" != "$KAMAILIO_CHILDREN" ]]; then
        sed -i -E "s/^children=[0-9]+/children=${KAMAILIO_CHILDREN}/" "$_KAMAILIO_CFG"
        _KAMAILIO_CHANGED=1
        log "kamailio.cfg: children ${_current_children:-?} → ${KAMAILIO_CHILDREN}"
    fi
fi

# ── Memoria SHM/PKG de Kamailio ───────────────────────────────────────────────
# Hosts >4GB: 45% de la RAM total directo (margen de seguridad, decisión
# explícita — prioriza margen sobre ahorro). Hosts ≤4GB: fórmula conservadora
# (reservar 25% para MariaDB/RTPEngine/backend primero). Techo absoluto 8GB.
if [[ $HOST_RAM_MB -gt 4096 ]]; then
    KAMAILIO_SHM_MB=$(( HOST_RAM_MB * 45 / 100 ))
    [[ $KAMAILIO_SHM_MB -gt 8192 ]] && KAMAILIO_SHM_MB=8192
else
    _RESERVED_MB=$(( HOST_RAM_MB / 4 ))
    [[ $_RESERVED_MB -lt 1024 ]] && _RESERVED_MB=1024
    KAMAILIO_SHM_MB=$(( (HOST_RAM_MB - _RESERVED_MB) / 4 ))
    [[ $KAMAILIO_SHM_MB -lt 128 ]] && KAMAILIO_SHM_MB=128
fi
KAMAILIO_PKG_MB=$(( KAMAILIO_SHM_MB / 16 ))
[[ $KAMAILIO_PKG_MB -lt 16 ]] && KAMAILIO_PKG_MB=16

_MEM_CONF="/etc/default/kamailio.d/voxikam-memory.conf"
_current_shm=$(grep -oP '^SHM_MEMORY=\K[0-9]+' "$_MEM_CONF" 2>/dev/null || echo "")
if [[ "$_current_shm" != "$KAMAILIO_SHM_MB" ]]; then
    mkdir -p /etc/default/kamailio.d
    cat > "$_MEM_CONF" << EOF
# VoxiKam — recalculado por voxikam-autotune (deploy.sh o autotune.service)
SHM_MEMORY=$KAMAILIO_SHM_MB
PKG_MEMORY=$KAMAILIO_PKG_MB
EOF
    _KAMAILIO_CHANGED=1
    log "Kamailio memoria: SHM ${_current_shm:-?}MB → ${KAMAILIO_SHM_MB}MB (PKG ${KAMAILIO_PKG_MB}MB)"
fi

systemctl daemon-reload

# ── Reiniciar y validar (solo si NO se llamó con --no-restart) ──────────────
if [[ "$NO_RESTART" == "1" ]]; then
    [[ "$_BACKEND_CHANGED" == "1" || "$_KAMAILIO_CHANGED" == "1" ]] && \
        log "Config actualizada — reinicio manual pendiente (--no-restart, puede haber llamadas en vivo ahora)"
else
    if [[ "$_BACKEND_CHANGED" == "1" ]] && systemctl is-enabled --quiet voxikam-backend 2>/dev/null; then
        systemctl restart voxikam-backend
        sleep 2
        if systemctl is-active --quiet voxikam-backend; then
            log "voxikam-backend reiniciado OK"
        else
            log "ALERTA: voxikam-backend no quedó activo tras el reinicio — revisar journalctl -u voxikam-backend"
        fi
    fi

    # Segunda condición además de "cambió la config": si Kamailio quedó
    # muerto por la carrera de arranque con MariaDB (visto en vd1sbc2 — el
    # ExecStartPre nuevo del override de systemd reduce el riesgo pero no lo
    # elimina del todo), autotune corre DESPUÉS de Kamailio en el orden de
    # systemd (ver voxikam-autotune.service) — para cuando llega acá, MariaDB
    # ya lleva más tiempo arriba, así que un reintento a esta altura tiene
    # muchas más chances de funcionar. Sin esto, si la config de memoria no
    # cambió entre reboots (lo normal en un host estable), Kamailio se
    # quedaba muerto indefinidamente hasta que alguien lo reiniciara a mano.
    _kamailio_dead=0
    if systemctl is-enabled --quiet kamailio 2>/dev/null && ! systemctl is-active --quiet kamailio 2>/dev/null; then
        _kamailio_dead=1
        log "kamailio no está activo — reintentando (posible carrera de arranque con MariaDB)"
    fi

    if [[ "$_KAMAILIO_CHANGED" == "1" || "$_kamailio_dead" == "1" ]] && systemctl is-enabled --quiet kamailio 2>/dev/null; then
        systemctl restart kamailio
        sleep 2
        if systemctl is-active --quiet kamailio; then
            log "kamailio reiniciado OK (children=${KAMAILIO_CHILDREN}, SHM=${KAMAILIO_SHM_MB}MB)"
        else
            log "ALERTA: kamailio no quedó activo tras el reinicio — revisar journalctl -u kamailio"
        fi
    fi
fi

log "Autotuneo completo — workers=${WORKERS} kamailio_children=${KAMAILIO_CHILDREN} shm=${KAMAILIO_SHM_MB}MB pkg=${KAMAILIO_PKG_MB}MB"
