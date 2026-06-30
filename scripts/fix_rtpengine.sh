#!/usr/bin/env bash
# fix_rtpengine.sh — Diagnóstico y reparación de RTPEngine para VoxiKam
#
# Uso:
#   sudo bash fix_rtpengine.sh          # fix completo
#   sudo bash fix_rtpengine.sh --check  # solo diagnóstico, sin cambios
#   sudo bash fix_rtpengine.sh --watch  # monitoreo en vivo
#
set -euo pipefail

source "$(dirname "$0")/_colors.sh" 2>/dev/null || {
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
    BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'
    info() { echo -e "${BLUE}[·]${NC} $*"; }
    ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
    warn() { echo -e "${YELLOW}[!]${NC} $*"; }
    die()  { echo -e "${RED}[✗]${NC} $*" >&2; exit 1; }
}

sep() { echo -e "\n${BLUE}── $* ──────────────────────────────────────────────────────${NC}"; }

MODE="${1:-fix}"
RTPENGINE_CONF="/etc/rtpengine/rtpengine.conf"


# ── Helper: sesiones activas ──────────────────────────────────────────────────
sessions_count() {
    local n
    n=$(rtpengine-ctl list calls 2>/dev/null | wc -l)
    echo $((n - 1))   # restar header
}


# ── 1. DIAGNÓSTICO ────────────────────────────────────────────────────────────
sep "Diagnóstico RTPEngine"

# Servicio
if systemctl is-active --quiet rtpengine; then
    ok "Servicio rtpengine: ACTIVO"
else
    warn "Servicio rtpengine: INACTIVO"
fi

# Versión y uptime
info "Versión: $(rtpengine --version 2>/dev/null | head -1 || echo 'desconocida')"

# Kernel module
if lsmod | grep -q xt_RTPENGINE; then
    ok "Kernel module xt_RTPENGINE: CARGADO"
    KERNEL_MODULE=true
else
    warn "Kernel module xt_RTPENGINE: NO cargado (modo userspace)"
    KERNEL_MODULE=false
fi

# max-sessions actual en config
CURRENT_MAX=$(grep -E "^max-sessions" "$RTPENGINE_CONF" 2>/dev/null \
    | awk '{print $NF}' | tr -d '#' || echo "sin límite")
if grep -qE "^max-sessions" "$RTPENGINE_CONF" 2>/dev/null; then
    warn "max-sessions configurado: $CURRENT_MAX"
else
    ok "max-sessions: sin límite (ilimitado)"
fi

# Sesiones y estadísticas actuales
echo ""
SESIONES=$(sessions_count)
info "Sesiones activas ahora: $SESIONES"

TOTALS=$(rtpengine-ctl list totals 2>/dev/null || echo "")
if [[ -n "$TOTALS" ]]; then
    _parse() { echo "$1" | grep "$2" | awk -F: '{print $NF}' | tr -d ' '; }
    OWNED=$(  _parse "$TOTALS" "Owned sessions")
    REJECTED=$(_parse "$TOTALS" "Total rejected sessions")
    UP_MODE=$( _parse "$TOTALS" "Userspace-only media streams")
    KN_MODE=$( _parse "$TOTALS" "Kernel-only media streams")
    UPTIME=$(  _parse "$TOTALS" "Uptime of rtpengine" | awk '{print $1}')

    echo -e "  ${CYAN}Owned sessions    :${NC} ${OWNED:-0}"
    echo -e "  ${CYAN}Rejected sessions :${NC} ${REJECTED:-0}"
    echo -e "  ${CYAN}Userspace streams :${NC} ${UP_MODE:-0}"
    echo -e "  ${CYAN}Kernel streams    :${NC} ${KN_MODE:-0}"
    echo -e "  ${CYAN}Uptime            :${NC} ${UPTIME:-?}s"

    if [[ "${REJECTED:-0}" -gt 100 ]]; then
        warn "¡ALERTA! $REJECTED sesiones rechazadas — el límite estuvo activo"
    fi
fi

[[ "$MODE" == "--check" ]] && { echo ""; info "Modo check — sin cambios."; exit 0; }
[[ "$MODE" == "--watch" ]] && {
    echo ""
    info "Modo watch — Ctrl+C para salir"
    watch -n 2 "
        echo '=== Sesiones activas ==='
        rtpengine-ctl list calls 2>/dev/null | wc -l
        echo ''
        echo '=== Totals ==='
        rtpengine-ctl list totals 2>/dev/null
        echo ''
        echo '=== Errores Kamailio (últimos 5) ==='
        journalctl -u kamailio -n 5 --no-pager 2>/dev/null | grep -i rtpengine || echo '(ninguno)'
    "
    exit 0
}


# ── 2. FIX max-sessions ───────────────────────────────────────────────────────
sep "Corrigiendo max-sessions"

if grep -qE "^max-sessions" "$RTPENGINE_CONF" 2>/dev/null; then
    cp "$RTPENGINE_CONF" "${RTPENGINE_CONF}.bak.$(date +%Y%m%d_%H%M%S)"
    sed -i 's/^max-sessions/#max-sessions/' "$RTPENGINE_CONF"
    ok "max-sessions comentado (sin límite). Backup: ${RTPENGINE_CONF}.bak.*"
else
    ok "max-sessions ya está sin límite — nada que cambiar"
fi


# ── 3. Kernel module ──────────────────────────────────────────────────────────
sep "Kernel module xt_RTPENGINE"

if $KERNEL_MODULE; then
    ok "Ya cargado"
else
    info "Intentando cargar módulo..."

    # ¿Existe el módulo para este kernel?
    if find /lib/modules/"$(uname -r)" -name "*rtpengine*" 2>/dev/null | grep -q .; then
        modprobe xt_RTPENGINE && ok "Módulo cargado" || warn "modprobe falló"
    else
        warn "Módulo no compilado para kernel $(uname -r)"
        warn "RTPEngine continuará en modo userspace — funciona correctamente."
        info "Para compilar el módulo manualmente:"
        info "  apt install linux-headers-\$(uname -r) build-essential"
        info "  git clone https://github.com/sipwise/rtpengine /tmp/rtpengine-src"
        info "  cd /tmp/rtpengine-src && make -C kernel"
        info "  insmod kernel/xt_RTPENGINE.ko"
    fi

    # Hacer persistente si se cargó
    if lsmod | grep -q xt_RTPENGINE; then
        echo "xt_RTPENGINE" > /etc/modules-load.d/rtpengine.conf
        ok "Módulo persistente configurado en /etc/modules-load.d/rtpengine.conf"
    fi
fi


# ── 4. Reiniciar RTPEngine ────────────────────────────────────────────────────
sep "Reiniciando RTPEngine"

SESIONES_ANTES=$(sessions_count)
if [[ "$SESIONES_ANTES" -gt 0 ]]; then
    warn "$SESIONES_ANTES sesiones activas — el restart cortará el RTP de esas llamadas"
    read -rp "  ¿Continuar de todas formas? [s/N] " RESP
    [[ "${RESP,,}" == "s" ]] || { info "Saltando restart — aplica manualmente cuando el tráfico baje"; }
fi

systemctl restart rtpengine
sleep 2

if systemctl is-active --quiet rtpengine; then
    ok "RTPEngine reiniciado correctamente"
else
    die "RTPEngine no levantó — revisa: journalctl -u rtpengine -n 30"
fi


# ── 5. Cron de monitoreo ──────────────────────────────────────────────────────
sep "Cron de alerta"

CRON_FILE="/etc/cron.d/voxikam-rtpengine-monitor"
cat > "$CRON_FILE" << 'CRON'
# VoxiKam — alerta si RTPEngine tiene >400 sesiones rechazadas en última hora
*/5 * * * * root /usr/bin/rtpengine-ctl list totals 2>/dev/null | grep "rejected" >> /var/log/voxikam-rtpengine.log
CRON
ok "Cron de monitoreo en $CRON_FILE"


# ── Resumen final ──────────────────────────────────────────────────────────────
sep "Estado final"

SESIONES_POST=$(sessions_count)
KERNEL_POST=$(lsmod | grep -q xt_RTPENGINE && echo "CARGADO" || echo "userspace")
MAX_POST=$(grep -E "^max-sessions" "$RTPENGINE_CONF" 2>/dev/null && echo "limitado" || echo "sin límite")

echo ""
echo -e "  ${GREEN}max-sessions  :${NC} $MAX_POST"
echo -e "  ${GREEN}Kernel module :${NC} $KERNEL_POST"
echo -e "  ${GREEN}Sesiones ahora:${NC} $SESIONES_POST"
echo ""
ok "Fix completado."
echo ""
info "Para monitorear en vivo:"
echo "    sudo bash scripts/fix_rtpengine.sh --watch"
echo ""
info "Para solo diagnosticar (sin cambios):"
echo "    sudo bash scripts/fix_rtpengine.sh --check"
echo ""
