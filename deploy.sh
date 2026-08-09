#!/bin/bash
# =============================================================================
# VoxiKam — SIP Class 4 Billing & Monitoring Platform
#
# Copyright (c) 2026 KPBTec
# MIT License — https://github.com/KPBTec/VoxiKam/blob/main/LICENSE
# Contact & support: https://t.me/KPBTec
#
# By KPBTec
# =============================================================================
# Instalador
#
# Uso recomendado:
#   git clone <repo> /opt/voxikam
#   cd /opt/voxikam
#   sudo ./deploy.sh
#
# Flags opcionales (omitir para menú interactivo):
#   --update     Código + migraciones + frontend, SIN reiniciar Kamailio (rápido)
#   --upgrade    Actualizar código, schema, configs y Kamailio (completo)
#   --reinstall  Borrar todo y reinstalar desde cero
#
# El directorio de instalación es donde está este script.
# Queda guardado en /etc/voxikam.conf para referencia futura.
# =============================================================================
set -euo pipefail

INSTALL_START=$SECONDS   # timer global — se muestra en el resumen final

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$SCRIPT_DIR"             # puede cambiar si hay instalación previa en otra ruta
MARKER_FILE="/etc/voxikam.conf"   # ubicación fija — siempre encontrable

# Cargar metadatos del release (nombre, versión, defaults)
# Editar release.conf para cambiar nombre o versión — no tocar este script
if [[ ! -f "$INSTALL_DIR/release.conf" ]]; then
    echo "ERROR: release.conf no encontrado en $INSTALL_DIR" >&2; exit 1
fi
source "$INSTALL_DIR/release.conf"

# Alias interno para mantener compatibilidad con el resto del script
INSTALLER_VERSION="$PLATFORM_VERSION"

# Modo de ejecución — se determina automáticamente según instalación previa
# o se puede forzar con flags CLI
MODE="fresh"
for _arg in "$@"; do
    case "$_arg" in
        --update)    MODE="update"    ;;
        --upgrade)   MODE="upgrade"   ;;
        --reinstall) MODE="reinstall" ;;
    esac
done

source "$INSTALL_DIR/scripts/_colors.sh"

LOG_DIR="/voxikam-install/logs-configs"
CREDS_FILE="$LOG_DIR/credentials.conf"

[[ $EUID -ne 0 ]] && { err "Ejecutar como root: sudo ./deploy.sh"; exit 1; }

mkdir -p "$LOG_DIR"; chmod 700 "$LOG_DIR"
LOG_FILE="$LOG_DIR/install-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1

# ── Autotuneo de workers según CPU real del host ─────────────────────────────
# uvicorn --workers estaba fijo en 2 — no escala con el tamaño del host (un
# VPS de 2 vCPU y uno de 16 vCPU terminaban con el mismo valor). A diferencia
# de VoxiDet, aquí no hay un modelo pesado (ML) que compartir entre workers,
# así que el único límite real es CPU — se reserva 1 core para
# Kamailio/MySQL/RTPEngine, que corren en el mismo host.
HOST_CPUS=$(nproc)
WORKERS=$(( HOST_CPUS > 1 ? HOST_CPUS - 1 : 1 ))
[[ $WORKERS -gt 16 ]] && WORKERS=16   # techo razonable, evita valores absurdos en hosts enormes
ok "Workers backend: $WORKERS (según ${HOST_CPUS} vCPU detectados)"

# ── Autotuneo de memoria de ClickHouse según RAM real del host ───────────────
# Mismo criterio que WORKERS arriba: un tope fijo le queda mal a cualquier
# host que no sea exactamente el de referencia. Piso subido a 2GB — confirmado
# en producción (server de 7.8GB) que el RSS base de ClickHouse con los caches
# de fábrica (mark_cache_size, etc., pensados para clusters grandes) ya ronda
# los 2GB en reposo, ANTES de insertar nada — un tope más bajo que eso tira
# MEMORY_LIMIT_EXCEEDED en cada insert, no un límite razonable. Los caches se
# bajan explícitamente más abajo para que el uso real quede lejos del tope,
# en vez de subir el tope indefinidamente para compensar caches de sobra que
# esta tabla (chica, sip_traces) no necesita.
HOST_MEM_BYTES=$(awk '/MemTotal/{print $2 * 1024}' /proc/meminfo)
CH_MEM_CAP=$(( HOST_MEM_BYTES / 2 ))
[[ $CH_MEM_CAP -lt 2147483648 ]] && CH_MEM_CAP=2147483648
# Techo subido de 4GB a 8GB — encontrado en producción real (vd1sbc2, 16GB de
# RAM): el techo viejo de 4GB cortaba la fórmula (RAM/3≈5.3GB) igual, y el
# RSS real de ClickHouse ya estaba en 5.47GB — MEMORY_LIMIT_EXCEEDED hasta en
# un SELECT 1, tumbando el deploy. Con host grandes (>12GB) el techo viejo
# nunca dejaba que la RAM extra ayudara en nada. 8GB sigue dejando margen de
# sobra para MariaDB/app/OS incluso en un host de 16GB.
[[ $CH_MEM_CAP -gt 8589934592 ]] && CH_MEM_CAP=8589934592
ok "ClickHouse memory cap: $((CH_MEM_CAP / 1024 / 1024))MB (según $((HOST_MEM_BYTES / 1024 / 1024))MB RAM detectados)"

# Se llama en CADA corrida (update Y upgrade/fresh) — compara contra lo que ya
# está escrito en el host y solo toca el archivo/reinicia el servicio si el
# cap realmente cambió (ej: el VPS se resizeó después de instalar). Sin esto,
# un server que arranca con poca RAM y después se le sube memoria se queda
# para siempre con el tope viejo — visto en producción real: RSS ya por
# encima del tope congelado, ClickHouse rechazando toda query con
# MEMORY_LIMIT_EXCEEDED aunque el host tuviera memoria de sobra disponible.
sync_ch_memory_cap() {
    local _conf="/etc/clickhouse-server/config.d/99-voxikam.xml"
    [[ -f "$_conf" ]] || return 0
    local _current
    _current=$(grep -oP '(?<=<max_server_memory_usage>)[0-9]+' "$_conf" 2>/dev/null || echo 0)
    if [[ "$_current" != "$CH_MEM_CAP" ]]; then
        sed -i "s#<max_server_memory_usage>.*</max_server_memory_usage>#<max_server_memory_usage>${CH_MEM_CAP}</max_server_memory_usage>#" "$_conf"
        systemctl restart clickhouse-server
        ok "ClickHouse memory cap: $((_current / 1024 / 1024))MB → $((CH_MEM_CAP / 1024 / 1024))MB (RAM del host cambió desde la última corrida)"
    fi
}

# Leído ANTES de que nada en el script toque $MARKER_FILE (los sed que
# escriben VERSION= corren mucho más abajo, en el PASO de configuración) —
# así el banner puede mostrar "de dónde viene" el upgrade, no solo "a dónde
# va". Vacío en --reinstall/fresh sin marcador previo (no hay "antes" que
# mostrar).
_PREV_INSTALLED_VERSION=""
if [[ -f "$MARKER_FILE" ]]; then
    _PREV_INSTALLED_VERSION=$(grep "^VERSION=" "$MARKER_FILE" 2>/dev/null | cut -d= -f2 | tr -d '[:space:]')
fi

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  $PLATFORM_NAME v$PLATFORM_VERSION — un desarrollo de KPBTec${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
if [[ "$MODE" != "fresh" && -n "$_PREV_INSTALLED_VERSION" ]]; then
    if [[ "$_PREV_INSTALLED_VERSION" == "$PLATFORM_VERSION" ]]; then
        echo -e "  ${BOLD}Versión:${NC}           v$_PREV_INSTALLED_VERSION → v$PLATFORM_VERSION (sin cambio de versión, re-deploy del mismo código)"
    else
        echo -e "  ${BOLD}Versión:${NC}           v$_PREV_INSTALLED_VERSION → v$PLATFORM_VERSION"
    fi
elif [[ "$MODE" != "fresh" ]]; then
    echo -e "  ${BOLD}Versión:${NC}           (sin marcador previo) → v$PLATFORM_VERSION"
fi
echo -e "  ${BOLD}Directorio origen:${NC} $SCRIPT_DIR"
echo -e "  ${BOLD}Usuario:${NC}           voxikam  (sin shell, sin login — solo servicios)"
echo -e "  ${BOLD}Log:${NC}               $LOG_FILE"
echo ""

# =============================================================================
# VERIFICAR INSTALACIÓN PREVIA
# =============================================================================
OLD_DB_ROOT_PASS=""
OLD_DB_PORT=""

_drop_db() {
    local pass="$1"
    local args=(--user=root --socket=/run/mysqld/mysqld.sock)
    [[ -n "$pass" ]] && args+=(--password="$pass")
    mysql "${args[@]}" \
        -e "DROP DATABASE IF EXISTS sip_platform; \
            DROP USER IF EXISTS 'voxikam'@'127.0.0.1'; \
            DROP USER IF EXISTS 'voxikam'@'localhost'; \
            FLUSH PRIVILEGES;" 2>/dev/null
}

# =============================================================================
# MIGRACIONES DE SCHEMA VERSIONADAS — desde v2.53.0
# =============================================================================
# Reemplaza el patrón viejo de agregar un ALTER TABLE ... ADD COLUMN IF NOT
# EXISTS suelto en las ramas --update Y --upgrade cada vez que se agrega una
# columna — eso llevó a podar deploy.sh a mano contra dumps reales cada tanto
# (ver CHANGELOG v2.52.3/v2.52.4). La tabla schema_migrations (db/schema.sql)
# trackea qué versión ya corrió — un deploy futuro solo ejecuta lo pendiente,
# nunca vuelve a chequear algo ya aplicado.
#
# El SQL de cada migración vive en su propio archivo db/migrations/X.Y.Z.sql
# (no acá adentro) — separa contenido SQL de orquestación bash, permite ver
# el diff de una migración puntual sin scrollear deploy.sh entero, y da
# resaltado de sintaxis SQL real en el editor. deploy.sh solo sabe QUÉ
# versiones existen y en qué orden (el array MIGRATIONS) y CÓMO aplicarlas
# (run_pending_migrations) — nunca el contenido.
#
# CÓMO AGREGAR UNA MIGRACIÓN NUEVA (a partir de v2.53.0):
#   1. Crear db/migrations/X.Y.Z.sql con el ALTER/CREATE correspondiente.
#   2. Agregar esa versión al array MIGRATIONS de abajo, AL FINAL, en orden.
#   3. NO tocar código viejo de --update/--upgrade — ese ya corrió en todo el
#      parque real, se deja intacto (ver "Bootstrap" abajo).
#
# Las migraciones VIEJAS (show_*, connect_charge, ui_theme, etc. — todo lo
# que ya existía en deploy.sh antes de este mecanismo) NO se migran a este
# sistema — ya están aplicadas y son idempotentes, tocarlas no da ningún
# beneficio y sí agrega riesgo. Este mecanismo es solo para lo nuevo.
MIGRATIONS=(
    "2.54.0"
    "2.55.7"
)

# migration_sql <version> — imprime el SQL de db/migrations/<version>.sql, o
# falla (return 1) si el archivo no existe. $INSTALL_DIR ya apunta al repo
# recién sincronizado en este punto del deploy (--update y --upgrade lo
# setean antes de llegar acá), así que esto funciona igual en ambas ramas.
migration_sql() {
    local f="$INSTALL_DIR/db/migrations/$1.sql"
    [[ -f "$f" ]] || return 1
    cat "$f"
}

# run_pending_migrations <mysql_cmd> <db_name>
# <mysql_cmd> es el comando mysql completo con credenciales ya resueltas
# (ej. "$_UMC"/"$MC" según la rama que llame) — la función no asume ninguna
# variable global de conexión específica, así sirve desde --update y
# --upgrade por igual sin duplicar lógica de conexión.
run_pending_migrations() {
    local mc="$1" db="$2"
    # Bootstrap — primera vez que este mecanismo corre en una instalación
    # existente: siembra '2.53.0' sin ejecutar SQL (todo lo necesario para
    # llegar hasta acá ya corrió con el patrón ALTER...IF NOT EXISTS viejo,
    # que sigue intacto más arriba en este mismo archivo).
    local baseline
    baseline=$($mc "$db" -N -e "SELECT COUNT(*) FROM schema_migrations WHERE version='2.53.0'" 2>/dev/null || echo 0)
    if [[ "$baseline" == "0" ]]; then
        $mc "$db" -e "INSERT IGNORE INTO schema_migrations (version) VALUES ('2.53.0')" 2>/dev/null || true
    fi
    local v sql applied
    for v in "${MIGRATIONS[@]}"; do
        applied=$($mc "$db" -N -e "SELECT COUNT(*) FROM schema_migrations WHERE version='$v'" 2>/dev/null || echo 0)
        [[ "$applied" != "0" ]] && continue
        sql=$(migration_sql "$v") || continue
        if $mc "$db" -e "$sql" >>"$LOG_FILE" 2>&1; then
            $mc "$db" -e "INSERT INTO schema_migrations (version) VALUES ('$v')" 2>/dev/null
            ok "Migración de schema $v aplicada"
        else
            warn "Migración de schema $v falló — revisar $LOG_FILE (no se marcó como aplicada, se reintentará en el próximo deploy)"
        fi
    done
}

# =============================================================================
# PASOS COMPARTIDOS entre --update y --upgrade
# =============================================================================
# Podado 2026-08-02: hasta acá, cada uno de estos pasos vivía escrito DOS
# veces (uno en la rama rápida --update, otro en el pipeline completo que usa
# --upgrade/fresh) — mismo resultado, texto copiado y evolucionado por
# separado. Costo real, no solo estético: el fix del módulo xt_RTPENGINE
# (modprobe antes de arrancar, ver setup_rtpengine_systemd_override) se
# agregó en algún momento a la copia de --upgrade y NUNCA se backporteó a la
# de --update — cualquiera que solo usara --update se perdía ese fix sin
# enterarse. Con una sola función por paso, eso ya no puede pasar.

# setup_rtpengine_systemd_override — corrige el drop-in que apuntaba a la
# unidad systemd equivocada (rtpengine.service.d en vez de
# rtpengine-daemon.service.d, real desde v2.0), quita -E del ExecStart
# (si no, nunca loguea a syslog pase lo que pase en rtpengine.conf), y
# precarga el módulo kernel xt_RTPENGINE (si no, en un boot en frío
# RTPEngine cae a modo userspace-only sin avisar más que un error suelto).
setup_rtpengine_systemd_override() {
    if [[ -f /lib/systemd/system/rtpengine-daemon.service ]]; then
        mkdir -p /etc/systemd/system/rtpengine-daemon.service.d
        cat > /etc/systemd/system/rtpengine-daemon.service.d/voxikam-limits.conf << 'EOF'
[Service]
# LimitNOFILE: NO se fija acá — el paquete ya trae 150000 (más alto que
# nuestro estándar de 65536 para otros servicios); fijarlo más bajo sería
# una regresión real, no una mejora.
LimitMEMLOCK=infinity
LimitCORE=infinity
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_RAW CAP_SYS_NICE
# "FAILED TO DELETE KERNEL TABLE 0 (Permission denied), KERNEL FORWARDING
# DISABLED" en cada reboot en frío (visto en vd1sbc2) — el módulo kernel
# xt_RTPENGINE está compilado vía DKMS (confirmado en v2.24.14) pero nada lo
# cargaba automáticamente al arrancar, así que en un boot recién hecho no
# está listo cuando RTPEngine intenta usarlo (cae a modo userspace-only sin
# avisar más que ese error). El ExecStartPre empaquetado
# (rtpengine-iptables-setup) queda igual, se agrega el modprobe ANTES —
# `-` al inicio: si el módulo no existiera por algún motivo, no debe romper
# el arranque de RTPEngine, solo se queda en modo userspace como hasta ahora.
ExecStartPre=
ExecStartPre=-/sbin/modprobe -q xt_RTPENGINE
ExecStartPre=/usr/sbin/rtpengine-iptables-setup start
# Mismos argumentos que trae el paquete rtpengine-daemon, sin -E — si una
# versión futura del paquete cambia esos flags, hay que revisar este override.
ExecStart=
ExecStart=/usr/bin/rtpengine -f --no-log-timestamps --pidfile /run/rtpengine/rtpengine-daemon.pid --config-file /etc/rtpengine/rtpengine.conf
EOF
        ok "RTPEngine systemd override → limits (antes nunca se aplicaban) + quitado -E (ahora sí loguea a syslog/local1) + modprobe xt_RTPENGINE antes de arrancar"
        warn "RTPEngine: log-facility=local1 + override sin -E — hace falta 'systemctl restart rtpengine' a mano (ventana de mantenimiento, corta audio en curso) para que todo esto tome efecto"
    fi
    systemctl daemon-reload 2>/dev/null || true
}

# setup_kamailio_rtpengine_syslog — rsyslog + logrotate para separar los logs
# de Kamailio (facility LOCAL0) y RTPEngine (facility LOCAL1) del syslog
# general, más el tope de tamaño/retención de journald (único canal donde
# sobreviven los WARNING/ERROR reales del backend — ver logging.basicConfig
# en main.py).
setup_kamailio_rtpengine_syslog() {
    mkdir -p /etc/rsyslog.d /etc/logrotate.d
    cat > /etc/rsyslog.d/40-kamailio.conf << 'EOF'
# VoxiKam — captura logs de Kamailio (facility LOCAL0)
# kamailio.cfg: log_facility=LOG_LOCAL0 log_stderror=no
if $syslogfacility-text == 'local0' then /var/log/kamailio.log
& stop
EOF
    touch /var/log/kamailio.log
    chown root:adm /var/log/kamailio.log 2>/dev/null || chown root:root /var/log/kamailio.log
    chmod 640 /var/log/kamailio.log

    # logrotate: solo el día actual, sin compresión (fácil de leer en vivo)
    cat > /etc/logrotate.d/kamailio << 'EOF'
/var/log/kamailio.log {
    daily
    rotate 1
    missingok
    notifempty
    nocreate
    postrotate
        /usr/bin/systemctl -s HUP kill rsyslog.service 2>/dev/null || true
    endscript
}
EOF

    # ── RTPEngine logging — mismo esquema, facility LOCAL1 (rtpengine.conf:
    # log-facility=local1) para no mezclarse con Kamailio (LOCAL0) en el mismo
    # archivo ─────────────────────────────────────────────────────────────────
    cat > /etc/rsyslog.d/41-rtpengine.conf << 'EOF'
# VoxiKam — captura logs de RTPEngine (facility LOCAL1)
# rtpengine.conf: log-facility=local1
if $syslogfacility-text == 'local1' then /var/log/rtpengine.log
& stop
EOF
    touch /var/log/rtpengine.log
    chown root:adm /var/log/rtpengine.log 2>/dev/null || chown root:root /var/log/rtpengine.log
    chmod 640 /var/log/rtpengine.log

    # logrotate: solo el día actual, igual que kamailio.log
    cat > /etc/logrotate.d/rtpengine << 'EOF'
/var/log/rtpengine.log {
    daily
    rotate 1
    missingok
    notifempty
    nocreate
    postrotate
        /usr/bin/systemctl -s HUP kill rsyslog.service 2>/dev/null || true
    endscript
}
EOF

    # logrotate para los logs de cron (logs/*.log en INSTALL_DIR + los root-only
    # en LOG_DIR) — antes crecían sin límite, nada los rotaba nunca. 14 días
    # comprimido: no son logs de tráfico por-llamada como kamailio/rtpengine
    # (una línea por corrida de cron, no por llamada), no hace falta el esquema
    # agresivo de esos. dlg_stats.log es la excepción (una línea por minuto,
    # forever) — mismo esquema corto que kamailio/rtpengine.
    cat > /etc/logrotate.d/voxikam-cron << EOF
$INSTALL_DIR/logs/*.log {
    daily
    rotate 14
    compress
    missingok
    notifempty
    nocreate
}
$LOG_DIR/dlg_stats.log $LOG_DIR/infra_alert.log {
    daily
    rotate 3
    compress
    missingok
    notifempty
    nocreate
}
EOF
    ok "logrotate configurado para logs de cron (14 días) y dlg_stats/infra_alert (3 días)"

    # journald sin límite gestionado — es el único canal donde sobreviven los
    # WARNING/ERROR reales del backend, y sin tope de retención dependía 100%
    # del default de la distro, no auditado.
    mkdir -p /etc/systemd/journald.conf.d
    cat > /etc/systemd/journald.conf.d/voxikam.conf << 'EOF'
[Journal]
SystemMaxUse=1G
MaxRetentionSec=30day
EOF
    systemctl restart systemd-journald 2>/dev/null && ok "journald: tope 1GB / retención 30 días" || warn "No se pudo reiniciar systemd-journald — el límite quedó escrito pero no aplicado hasta el próximo reinicio"

    systemctl enable rsyslog 2>/dev/null || true
    systemctl restart rsyslog \
        && ok "rsyslog instalado: Kamailio → /var/log/kamailio.log, RTPEngine → /var/log/rtpengine.log (rotate diario, 1 día)" \
        || warn "rsyslog no pudo iniciarse — revisar: journalctl -u rsyslog"
    warn "rtpengine.conf cambió log-facility a local1 — hace falta 'systemctl restart rtpengine' a mano (en ventana de mantenimiento, corta audio en curso) para que empiece a loguear a /var/log/rtpengine.log"
}

# _run_spinner <label> <comando...> — corre un comando en background con un
# spinner en pantalla; si falla, muestra las últimas líneas del log para
# diagnóstico inmediato. Antes existía duplicada como _spinner (pipeline
# principal) y _uspinner (rama --update) — mismo cuerpo, dos nombres.
_run_spinner() {
    local label="$1"; shift
    info "${label}..."
    "$@" >>"$LOG_FILE" 2>&1 &
    local _PID=$! _T=0
    while kill -0 $_PID 2>/dev/null; do
        printf "\r  → %s ... %ds" "$label" "$_T"
        sleep 3; _T=$((_T + 3))
    done
    printf "\r%-60s\r" " "
    if wait $_PID; then
        ok "${label} (${_T}s)"
    else
        err "${label} falló (${_T}s) — últimas líneas del log:"
        echo ""; tail -25 "$LOG_FILE"; echo ""
        exit 1
    fi
}

# setup_backend_venv [fresh] — instala/actualiza dependencias del backend.
# "fresh" crea el virtualenv desde cero (fresh install / --upgrade); sin
# argumento asume que ya existe (rama --update, más rápida). Redirigir la
# salida al log queda a cargo del que llama (--update lo hace quieto,
# igual que siempre; el resto lo deja visible en pantalla).
setup_backend_venv() {
    [[ "${1:-}" == "fresh" ]] && python3 -m venv "$INSTALL_DIR/venv"
    "$INSTALL_DIR/venv/bin/pip" install -q --upgrade pip
    "$INSTALL_DIR/venv/bin/pip" install -q -r "$INSTALL_DIR/backend/requirements.txt"
}

# build_frontend — npm install (con fallback del binding nativo de
# @tailwindcss/oxide) + build de Next.js, con backup/restore automático del
# build anterior si el nuevo falla (para no dejar el frontend caído). Antes
# vivía escrito dos veces (rama --update y pipeline principal), idéntico
# salvo el nombre del spinner — unificado acá.
build_frontend() {
    hdr "Frontend Next.js"
    cd "$INSTALL_DIR/frontend"
    # Limpiar node_modules previo — evita bug de npm con optional deps
    # (github.com/npm/cli/issues/4828)
    rm -rf node_modules package-lock.json
    _run_spinner "Instalando paquetes npm" npm install --include=optional

    # npm en entorno no-interactivo omite optional deps aunque se pida
    # --include=optional — si el binding nativo de @tailwindcss/oxide no
    # quedó instalado, instalar el paquete específico de la plataforma actual.
    local _OXIDE_ARCH=""
    case "$(uname -m)" in
        x86_64)  _OXIDE_ARCH="linux-x64-gnu"   ;;
        aarch64) _OXIDE_ARCH="linux-arm64-gnu"  ;;
    esac
    if [[ -n "$_OXIDE_ARCH" && ! -d "node_modules/@tailwindcss/oxide-${_OXIDE_ARCH}" ]]; then
        npm install --no-save "@tailwindcss/oxide-${_OXIDE_ARCH}" >>"$LOG_FILE" 2>&1 \
            && ok "Binding @tailwindcss/oxide-${_OXIDE_ARCH} instalado" \
            || { err "No se pudo instalar @tailwindcss/oxide-${_OXIDE_ARCH}"; exit 1; }
    fi

    # Backup del build anterior — si el build nuevo falla (ej. un error de
    # TypeScript), sin esto el frontend quedaba roto hasta el próximo deploy
    # exitoso. Con esto, un build fallido restaura el que sí funcionaba y el
    # resto del deploy (backend/DB) igual queda aplicado.
    local _BUILD_BACKUP=""
    if [[ -d ".next/standalone" && -d ".next/static" ]]; then
        _BUILD_BACKUP="$(mktemp -d)"
        cp -r .next/standalone "$_BUILD_BACKUP/standalone"
        cp -r .next/static     "$_BUILD_BACKUP/static"
    fi

    # rm -rf .next — el rsync excluye .next/ del --delete a propósito (evita
    # borrar el build corriendo mientras se despliega el nuevo), pero eso deja
    # el cache incremental de TypeScript (tsconfig "incremental": true) pegado
    # entre deploys — puede servir errores de tipos ya resueltos en el código
    # fuente actual. Limpiar acá, justo antes del build, es obligatorio.
    rm -rf .next
    info "Compilando frontend Next.js..."
    if ! npm run build >>"$LOG_FILE" 2>&1; then
        err "Compilando frontend Next.js falló — últimas líneas del log:"
        echo ""; tail -25 "$LOG_FILE"; echo ""
        if [[ -n "$_BUILD_BACKUP" ]]; then
            warn "Restaurando el build anterior que funcionaba — este deploy del frontend NO se aplicó (backend/DB sí quedaron actualizados)."
            mkdir -p .next
            cp -r "$_BUILD_BACKUP/standalone" .next/standalone
            cp -r "$_BUILD_BACKUP/static"     .next/static
            rm -rf "$_BUILD_BACKUP"
            ok "Build anterior restaurado — corregir el error de arriba y reintentar cuando quieras"
        else
            err "No había un build anterior para restaurar (primera compilación) — el frontend queda caído hasta corregir el error y reintentar."
        fi
        exit 1
    fi
    [[ -n "$_BUILD_BACKUP" ]] && rm -rf "$_BUILD_BACKUP"
    ok "Compilando frontend Next.js"

    # Next.js standalone no incluye los estáticos — copiarlos manualmente
    cp -r .next/static  .next/standalone/.next/static
    cp -r public        .next/standalone/public 2>/dev/null || true
    cd "$INSTALL_DIR"
    ok "Frontend construido"
}

# setup_voxikam_crontab — genera /etc/cron.d/voxikam desde la plantilla del
# repo, sustituyendo INSTALL_DIR/LOG_DIR. Antes vivía escrito dos veces
# (rama --update y pipeline principal), idéntico salvo el título del hdr.
setup_voxikam_crontab() {
    hdr "Tareas programadas"
    mkdir -p "$INSTALL_DIR/logs"
    chown voxikam:voxikam "$INSTALL_DIR/logs"
    chmod 755 "$INSTALL_DIR/logs"
    rm -f /etc/cron.d/sip-platform   # limpiar nombre anterior
    sed \
        -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" \
        -e "s|__LOG_DIR__|$LOG_DIR|g"         \
        "$INSTALL_DIR/cron/voxikam" > /etc/cron.d/voxikam
    chmod 644 /etc/cron.d/voxikam
    ok "Crontab configurado — logs voxikam en $INSTALL_DIR/logs/"
}

# sync_systemd_service_files — escribe los .service de voxikam-{backend,
# frontend,hep} desde la plantilla del repo (sustituyendo INSTALL_DIR/WORKERS)
# y limpia los .service de nombres viejos (sip-*, kaplabilling-*) si vienen de
# una instalación v1. NO hace daemon-reload ni (re)inicia nada — eso queda a
# cargo de quien llama, porque --update y el pipeline principal difieren en
# cómo y cuándo reinician los servicios.
sync_systemd_service_files() {
    hdr "Servicios systemd"
    for svc in voxikam-backend voxikam-frontend voxikam-hep; do
        sed -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" -e "s|__WORKERS__|$WORKERS|g" \
            "$INSTALL_DIR/systemd/${svc}.service" \
            > "/etc/systemd/system/${svc}.service"
        ok "/etc/systemd/system/${svc}.service"
    done
    # Limpiar servicios viejos silenciosamente si existen
    for old in sip-backend sip-frontend sip-hep kaplabilling-backend kaplabilling-frontend kaplabilling-hep; do
        systemctl stop    "$old" 2>/dev/null || true
        systemctl disable "$old" 2>/dev/null || true
        rm -f "/etc/systemd/system/${old}.service"
    done
}

# ── Migración automática desde una instalación previa de KaplaBilling ───────
# VoxiKam es la evolución de KaplaBilling (mismo proyecto, nombre nuevo) — si
# se detecta una instalación vieja y todavía no hay marcador de VoxiKam, se
# REUSA su base de datos y credenciales de MySQL tal cual (mismo usuario/
# password/DB — cero objetos nuevos, cero riesgo de permisos mal dados) y se
# fuerza modo "upgrade" para que el resto del flujo ya probado (que NO toca
# la DB en modo upgrade, ver PASO 6 más abajo) haga el resto solo.
# No se mueve ni se borra /opt/kaplabilling — queda intacto como respaldo de
# rollback. Solo aplica si el usuario no pidió explícitamente otro modo
# (--update/--upgrade/--reinstall) — un flag explícito siempre gana.
_LEGACY_ENV="/opt/kaplabilling/backend/.env"
_LEGACY_CREDS="/kaplabilling-install/logs-configs/credentials.conf"
if [[ "$MODE" == "fresh" && ! -f "$MARKER_FILE" ]] \
   && { [[ -f "$_LEGACY_ENV" ]] || [[ -f "$_LEGACY_CREDS" ]] \
        || systemctl list-units --full -all 2>/dev/null | grep -q "kaplabilling-backend"; }; then
    hdr "Instalación previa de KaplaBilling detectada"

    if [[ -f "$_LEGACY_CREDS" ]]; then
        # Preferido: KaplaBilling ya usaba este mismo formato credentials.conf
        # (VoxiKam evolucionó de este proyecto) — trae TODOS los datos de una,
        # incluido root_password de MariaDB, que el .env de la app nunca tuvo
        # (DATABASE_URL solo trae credenciales de nivel aplicación). Sin
        # root_password, PASO 7 (carga de schema) falla con "Access denied"
        # incluso en modo upgrade, aunque PASO 6 (creación de DB) esté deshabilitado.
        _kcred() { (grep -m1 "^\s*$1\s*=" "$_LEGACY_CREDS" 2>/dev/null || true) | awk -F'= ' '{print $2}' | tr -d '[:space:]'; }
        DB_USER=$(      _kcred "user")
        DB_PASS=$(      _kcred "password")
        DB_PORT=$(      _kcred "port")
        DB_NAME=$(      _kcred "database")
        DB_ROOT_PASS=$( _kcred "root_password")
        PUBLIC_IP=$(    _kcred "public_ip")
        PRIVATE_IP=$(   _kcred "private_ip")
        PRIVATE_NET=$(  _kcred "private_net")
        MGMT_IP=$(      _kcred "mgmt_ip")
        SSH_PORT=$(     _kcred "ssh_port")
        DOMAIN=$(       _kcred "domain")
        WEB_PORT=$(     _kcred "web_port")
        JWT_SECRET=$(   _kcred "jwt_secret")
        ADMIN_EMAIL=$(  _kcred "admin_email")
        ok "Credenciales completas recuperadas de $_LEGACY_CREDS (incluye root_password)"
    elif [[ -f "$_LEGACY_ENV" ]]; then
        _legacy_db_url=$(grep -m1 '^DATABASE_URL=' "$_LEGACY_ENV" | cut -d= -f2-)
        if [[ "$_legacy_db_url" =~ mysql\+aiomysql://([^:]+):([^@]+)@([^:]+):([0-9]+)/([a-zA-Z0-9_]+) ]]; then
            DB_USER="${BASH_REMATCH[1]}"
            DB_PASS="${BASH_REMATCH[2]}"
            DB_PORT="${BASH_REMATCH[4]}"
            DB_NAME="${BASH_REMATCH[5]}"
        else
            err "No se pudo leer DATABASE_URL de $_LEGACY_ENV — migración automática no disponible, revisar manualmente."
            exit 1
        fi
        # No disponible desde el .env de la app (solo tiene credenciales de nivel
        # aplicación, no root de MariaDB) — sin $_LEGACY_CREDS no hay forma
        # automática de conseguirlo. Advertir en vez de fallar en silencio más
        # adelante en PASO 7.
        DB_ROOT_PASS=""

        PUBLIC_IP=$( grep -m1 '^PUBLIC_IP='  "$_LEGACY_ENV" | cut -d= -f2- || true)
        PRIVATE_IP=$(grep -m1 '^PRIVATE_IP=' "$_LEGACY_ENV" | cut -d= -f2- || true)
        DOMAIN=$(    grep -m1 '^DOMAIN='     "$_LEGACY_ENV" | cut -d= -f2- || true)
        WEB_PORT=$(  grep -m1 '^WEB_PORT='   "$_LEGACY_ENV" | cut -d= -f2- || true)
        JWT_SECRET=$(grep -m1 '^JWT_SECRET=' "$_LEGACY_ENV" | cut -d= -f2- || true)
        ADMIN_EMAIL=""
        SSH_PORT=""
        PRIVATE_NET=""
        MGMT_IP=""
        warn "No se encontró $_LEGACY_CREDS — root_password de MariaDB no disponible automáticamente."
        warn "PASO 7 (carga de schema) va a fallar con 'Access denied' sin esto."
        warn "Alternativas: /etc/mysql/debian.cnf (cuenta debian-sys-maint), o ingresarlo a mano en $LOG_DIR/credentials.conf antes de continuar."
    else
        err "Hay servicios kaplabilling-* activos pero no existe ni $_LEGACY_ENV ni $_LEGACY_CREDS — migración automática no disponible, revisar manualmente."
        exit 1
    fi

    echo -e "  Base de datos existente: ${BOLD}$DB_NAME${NC} en puerto ${BOLD}$DB_PORT${NC} (usuario ${BOLD}$DB_USER${NC})"
    echo -e "  Se va a REUSAR tal cual — no se crea ni se modifica ningún objeto de MySQL."
    echo -e "  /opt/kaplabilling queda intacto (respaldo de rollback, no se toca ni se borra)."
    echo ""

    mkdir -p "$LOG_DIR"; chmod 700 "$LOG_DIR"
    cat > "$LOG_DIR/credentials.conf" <<CREDSEOF
[app]
domain        = $DOMAIN
web_port      = $WEB_PORT
public_ip     = $PUBLIC_IP
private_ip    = $PRIVATE_IP
private_net   = $PRIVATE_NET
mgmt_ip       = $MGMT_IP
ssh_port      = $SSH_PORT

[mariadb]
host          = 127.0.0.1
port          = $DB_PORT
root_password = $DB_ROOT_PASS
database      = $DB_NAME
user          = $DB_USER
password      = $DB_PASS

[platform]
admin_email   = $ADMIN_EMAIL
jwt_secret    = $JWT_SECRET
url           = http://$DOMAIN:$WEB_PORT
CREDSEOF
    chmod 600 "$LOG_DIR/credentials.conf"
    ok "Credenciales de KaplaBilling reusadas → $LOG_DIR/credentials.conf"

    MODE="upgrade"
    ok "Modo forzado a 'upgrade' — la base de datos existente se reusa sin tocarla"

    # Detener servicios viejos YA (mismos puertos que voxikam-*, si no se
    # detienen ahora el arranque de los nuevos falla por puerto ocupado)
    for _old in kaplabilling-backend kaplabilling-frontend kaplabilling-hep; do
        if systemctl is-active --quiet "$_old" 2>/dev/null; then
            systemctl stop "$_old" && ok "Detenido: $_old"
        fi
        systemctl disable "$_old" 2>/dev/null || true
    done
    echo ""
    warn "Este deploy va a reiniciar Kamailio — corta TODAS las llamadas activas en el momento del restart."
    echo ""
fi

if [[ -f "$MARKER_FILE" && "$MODE" == "fresh" ]]; then
    # Cargar versión instalada desde el marker
    _INSTALLED_VERSION=$(grep "^VERSION=" "$MARKER_FILE" 2>/dev/null | cut -d= -f2 | tr -d '[:space:]' || echo "desconocida")
    _INSTALLED_DATE=$(grep "^INSTALL_DATE=" "$MARKER_FILE" 2>/dev/null | cut -d= -f2 | tr -d '[:space:]' || echo "")
    # LAST_DEPLOY_DATE — pedido explícito: mostrar cuándo fue la última vez
    # que se corrió update/upgrade (no la fecha de instalación original, que
    # queda fija para siempre). Instalaciones de antes de este campo no lo
    # tienen todavía en el marker — no se muestra la línea en ese caso, en
    # vez de mostrar una fecha vacía o inventada.
    _LAST_DEPLOY_DATE=$(grep "^LAST_DEPLOY_DATE=" "$MARKER_FILE" 2>/dev/null | cut -d= -f2 | tr -d '[:space:]' || echo "")

    hdr "Instalación existente detectada"
    echo -e "  ${BOLD}Versión instalada:${NC}  v${_INSTALLED_VERSION:-?}"
    echo -e "  ${BOLD}Versión en repo:${NC}    v${INSTALLER_VERSION}"
    [[ -n "$_INSTALLED_DATE" ]] && echo -e "  ${BOLD}Instalado el:${NC}      $(echo "$_INSTALLED_DATE" | cut -dT -f1)"
    if [[ -n "$_LAST_DEPLOY_DATE" ]]; then
        echo -e "  ${BOLD}Última actualización:${NC} $(date -d "$_LAST_DEPLOY_DATE" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo "$_LAST_DEPLOY_DATE")"
    else
        echo -e "  ${BOLD}Última actualización:${NC} nunca (instalación original, sin update/upgrade todavía)"
    fi
    echo ""

    if [[ "$_INSTALLED_VERSION" != "$INSTALLER_VERSION" ]]; then
        echo -e "  Hay una versión nueva disponible (v${_INSTALLED_VERSION} → v${INSTALLER_VERSION})."
    else
        echo -e "  Ya tienes la versión más reciente (v${INSTALLER_VERSION})."
    fi
    echo ""
    echo -e "  ${BOLD}1)${NC} Actualizar — código + migraciones + frontend, ${BOLD}SIN reiniciar Kamailio${NC} (rápido, recomendado)"
    echo -e "  ${BOLD}2)${NC} Upgrade    — actualizar código, schema y configs ${BOLD}(conserva datos y contraseñas)${NC}"
    echo -e "  ${BOLD}3)${NC} Reinstalar — eliminar TODO y empezar desde cero (borra la base de datos)"
    echo -e "  ${BOLD}4)${NC} Cancelar"
    echo ""
    read -r -p "  Opción [1/2/3/4]: " _OPT
    case "${_OPT:-4}" in
        1) MODE="update"    ;;
        2) MODE="upgrade"   ;;
        3) MODE="reinstall" ;;
        *) info "Cancelado."; exit 0 ;;
    esac
    echo ""
fi

# Para reinstalación: eliminar DB anterior antes de proceder
if [[ "$MODE" == "reinstall" && -f "$LOG_DIR/credentials.conf" ]]; then
    OLD_DB_ROOT_PASS=$(grep -m1 "root_password" "$LOG_DIR/credentials.conf" \
                       | awk -F'= ' '{print $2}' | tr -d '[:space:]')
    OLD_DB_PORT=$(grep -m1 "^\s*port\s*=" "$LOG_DIR/credentials.conf" \
                  | awk -F'= ' '{print $2}' | tr -d '[:space:]')
    if [[ -n "$OLD_DB_PORT" ]]; then
        info "Eliminando base de datos anterior (puerto $OLD_DB_PORT)..."
        if _drop_db "" || _drop_db "$OLD_DB_ROOT_PASS"; then
            ok "Base de datos anterior eliminada"
        else
            warn "No se pudo autenticar con MariaDB automáticamente."
            echo ""
            read -r -s -p "  Password root de MariaDB (vacío = sin contraseña): " _MANUAL_ROOT; echo ""
            if _drop_db "$_MANUAL_ROOT"; then
                ok "Base de datos anterior eliminada"
            else
                warn "No se pudo eliminar DB anterior — continuando de todas formas"
            fi
            unset _MANUAL_ROOT
        fi
    fi
    warn "Reinstalando..."
    echo ""
fi

# =============================================================================
# RESOLVER DIRECTORIO DESTINO — PARAR SERVICIOS — SINCRONIZAR CÓDIGO
# =============================================================================
if [[ "$MODE" == "upgrade" || "$MODE" == "reinstall" || "$MODE" == "update" ]]; then
    # Leer el directorio donde está la instalación anterior
    _MARKER_DIR=$(grep "^INSTALL_DIR=" "$MARKER_FILE" 2>/dev/null \
                  | cut -d= -f2 | tr -d '[:space:]' || true)

    if [[ -n "$_MARKER_DIR" && -d "$_MARKER_DIR" ]]; then
        INSTALL_DIR="$_MARKER_DIR"
        if [[ "$SCRIPT_DIR" != "$INSTALL_DIR" ]]; then
            echo -e "  ${BOLD}Directorio instalado:${NC} $INSTALL_DIR"
            echo -e "  ${BOLD}Directorio origen:${NC}    $SCRIPT_DIR"
            echo ""
        else
            echo -e "  ${BOLD}Directorio:${NC} $INSTALL_DIR (en sitio)"
        fi
    else
        # Sin marker previo (típico de una migración KaplaBilling: es la
        # primera instalación de VoxiKam aunque la DB se reuse en modo
        # upgrade) — NUNCA usar $SCRIPT_DIR a ciegas: si el usuario subió el
        # código a /root/algo (común al subir manual como root, sin git), el
        # servicio voxikam-backend/frontend/hep corre como usuario sin
        # privilegios y jamás va a poder ni entrar a /root (permisos 700 del
        # propio /root, sin importar qué permisos tenga la subcarpeta) — el
        # CHDIR de systemd falla con "Permission denied" pase lo que pase.
        # Mismo destino fijo que usa el modo fresh: /opt/voxikam.
        warn "No se encontró instalación previa en el marker — usando /opt/voxikam"
        INSTALL_DIR="/opt/voxikam"
    fi

    # Detener servicios ANTES de tocar archivos (solo upgrade/reinstall — update hace hot-reload)
    if [[ "$MODE" != "update" ]]; then
        hdr "Deteniendo servicios"
        for _svc in voxikam-backend voxikam-frontend voxikam-hep; do
            if systemctl is-active --quiet "$_svc" 2>/dev/null; then
                systemctl stop "$_svc" && ok "Detenido: $_svc"
            else
                info "$_svc — no estaba activo"
            fi
        done
        echo ""
    fi

    # Sincronizar código si el origen es distinto al directorio instalado
    if [[ "$SCRIPT_DIR" != "$INSTALL_DIR" ]]; then
        hdr "Sincronizando código → $INSTALL_DIR"
        info "Origen:  $SCRIPT_DIR"
        info "Destino: $INSTALL_DIR"
        mkdir -p "$INSTALL_DIR"
        command -v rsync &>/dev/null || apt-get install -y rsync -qq
        # '/invoices/' y '/logs/' con barra inicial a propósito — sin ella,
        # rsync excluye CUALQUIER carpeta con ese nombre en cualquier nivel
        # del árbol, no solo $INSTALL_DIR/invoices/ y $INSTALL_DIR/logs/ (los
        # storages reales que esto necesita proteger). Dos bugs reales
        # encontrados en producción: excluía también frontend/app/(admin)/
        # invoices/, frontend/app/(client)/my/invoices/ Y frontend/app/
        # (admin)/system/logs/ — esas tres páginas nunca se actualizaban en
        # ningún --update/--upgrade, solo en un install fresh, sin importar
        # qué tan actualizado estuviera el código fuente (system/logs daba
        # 404 en el panel real). Confirmado con `find` sin límite de
        # profundidad que no hay más colisiones de este tipo — venv/,
        # node_modules/ y .next/ SÍ necesitan matchear anidado (backend/
        # venv/, frontend/node_modules/, frontend/.next/) y no tienen ningún
        # otro homónimo en el repo, así que esos quedan como estaban.
        rsync -a --delete \
            --exclude='.env' \
            --exclude='.env.local' \
            --exclude='venv/' \
            --exclude='node_modules/' \
            --exclude='.next/' \
            --exclude='standalone/' \
            --exclude='/invoices/' \
            --exclude='/logs/' \
            "$SCRIPT_DIR/" "$INSTALL_DIR/"
        ok "Código sincronizado"
        echo ""
    fi
else
    # Fresh: el destino SIEMPRE es /opt/voxikam, independientemente de donde
    # se ejecutó el install. Si el origen es distinto, se copia antes de continuar.
    INSTALL_DIR="/opt/voxikam"
    if [[ "$SCRIPT_DIR" != "$INSTALL_DIR" ]]; then
        hdr "Copiando archivos → $INSTALL_DIR"
        info "Origen:  $SCRIPT_DIR"
        info "Destino: $INSTALL_DIR"
        mkdir -p "$INSTALL_DIR"
        command -v rsync &>/dev/null || apt-get install -y rsync -qq
        rsync -a \
            --exclude='.env' \
            --exclude='.env.local' \
            --exclude='venv/' \
            --exclude='node_modules/' \
            --exclude='.next/' \
            --exclude='standalone/' \
            --exclude='/invoices/' \
            --exclude='/logs/' \
            "$SCRIPT_DIR/" "$INSTALL_DIR/"
        ok "Archivos copiados a $INSTALL_DIR"
        echo ""
    fi
fi

# Bit +x de scripts/*.sh — en TODOS los modos, justo después del rsync.
# Bug real encontrado en producción: scripts/autotune.sh quedó trackeado en
# git como 100644 (no ejecutable) mientras sus hermanos (_colors.sh,
# fix_rtpengine.sh) sí tenían 100755 — nadie lo notó hasta que
# voxikam-autotune.service falló con "Permission denied" al arrancar. El
# único chmod +x que existía para él vivía DENTRO del bloque exclusivo de
# --upgrade (ver más abajo), así que --update (que SÍ vuelve a correr este
# mismo rsync de arriba, preservando el modo del git de origen) lo dejaba
# no-ejecutable de nuevo aunque un --upgrade previo lo hubiera arreglado.
# Esta línea es la red de seguridad real — no depende de acordarse de
# marcar +x antes de cada commit para cualquier script nuevo.
chmod +x "$INSTALL_DIR/scripts/"*.sh 2>/dev/null || true
chmod +x "$INSTALL_DIR/scripts/setup/"*.sh 2>/dev/null || true

# CLI de administración (voxikam -s/-r/-p/-l) — se instala/actualiza en
# TODOS los modos (a diferencia de los pasos de systemd más abajo, que
# --update se salta) porque es solo un script + un symlink, no toca units
# activas ni corta llamadas.
if [[ -f "$INSTALL_DIR/scripts/voxikam-cli.sh" ]]; then
    ln -sf "$INSTALL_DIR/scripts/voxikam-cli.sh" /usr/local/bin/voxikam
    ok "CLI 'voxikam' instalado/actualizado (voxikam -s|-r|-p|-l back|front|hep|kamailio|rtpengine|app|all)"
fi

# sudoers de voxikam — se sincroniza en TODOS los modos (mismo criterio que
# el CLI de arriba: es un cp + chmod + validación, no toca servicios activos
# ni corta llamadas). Encontrado en la auditoría global v2.38.0: antes esto
# solo vivía en la sección exclusiva de fresh/upgrade (ver más abajo) — si se
# agregaba una línea nueva a sudoers/voxikam (ej. al sumar un servicio a
# system_services.py::ACTIONABLE) y el deploy diario es --update, el sudoers
# real del servidor quedaba desactualizado hasta el próximo --upgrade, sin
# ningún aviso (mismo patrón de bug que ya se corrigió esta sesión para el
# bit +x de los scripts).
if [[ -f "$INSTALL_DIR/sudoers/voxikam" ]]; then
    cp "$INSTALL_DIR/sudoers/voxikam" /etc/sudoers.d/voxikam
    chmod 440 /etc/sudoers.d/voxikam
    visudo -c -f /etc/sudoers.d/voxikam && ok "Sudoers sincronizado — voxikam puede: nft, kamcmd, fail2ban-client, systemctl (allowlist)" \
        || { err "Error en sudoers — revisar $INSTALL_DIR/sudoers/voxikam"; exit 1; }
fi

# =============================================================================
# UPDATE — actualización rápida: código + deps + DB + frontend, sin Kamailio
# =============================================================================
if [[ "$MODE" == "update" ]]; then
    hdr "Actualización rápida (Kamailio permanece activo)"

    if [[ ! -f "$LOG_DIR/credentials.conf" ]]; then
        err "No se encontraron credenciales en $LOG_DIR/credentials.conf"; exit 1
    fi
    _ucred() { (grep -m1 "^\s*$1\s*=" "$LOG_DIR/credentials.conf" 2>/dev/null || true) | awk -F'= ' '{print $2}' | tr -d '[:space:]'; }

    _UDB_ROOT=$(_ucred "root_password")
    _UDB_PORT=$(_ucred "port")
    _UDB_NAME=$(_ucred "database")
    _UMC="mysql --user=root --password=$_UDB_ROOT --host=127.0.0.1 --port=$_UDB_PORT"
    ok "Credenciales cargadas"

    # ── Python: actualizar dependencias ────────────────────────────────────────
    # setup_backend_venv/build_frontend/_run_spinner — funciones compartidas
    # con el pipeline principal, ver definición cerca del inicio de este
    # archivo. Acá van con salida redirigida al log (quieto), igual que
    # siempre en esta rama rápida.
    hdr "Dependencias Python"
    setup_backend_venv >>"$LOG_FILE" 2>&1
    ok "Dependencias actualizadas"

    # ── Migraciones DB ─────────────────────────────────────────────────────────
    hdr "Migraciones DB"
    $_UMC "$_UDB_NAME" < "$INSTALL_DIR/db/schema.sql" >>"$LOG_FILE" 2>&1

    # Migraciones versionadas (desde v2.53.0) — ver run_pending_migrations()
    # más arriba en este archivo. Nada que agregar acá a mano nunca más.
    run_pending_migrations "$_UMC" "$_UDB_NAME"

    # Backfill único de prefix_matched para TODO el histórico anterior al
    # trigger (recién agregado en schema.sql arriba) — el trigger solo cubre
    # inserts nuevos desde que existe; esto completa lo viejo una sola vez.
    # Background porque con millones de CDRs puede tardar minutos — no
    # bloquea el resto del deploy. Marcado en el marcador para no relanzarlo
    # en cada deploy futuro; si hiciera falta reintentar, "Recalcular
    # histórico" en Áreas sigue disponible manualmente desde el panel.
    if ! grep -q "^PREFIX_BACKFILL_TRIGGERED=1" "$MARKER_FILE" 2>/dev/null; then
        mkdir -p "$INSTALL_DIR/logs"
        nohup "$INSTALL_DIR/venv/bin/python3" "$INSTALL_DIR/scripts/backfill_prefix_matched.py" --yes \
            >>"$INSTALL_DIR/logs/backfill_prefix_matched.log" 2>&1 &
        if grep -q "^PREFIX_BACKFILL_TRIGGERED=" "$MARKER_FILE" 2>/dev/null; then
            sed -i "s/^PREFIX_BACKFILL_TRIGGERED=.*/PREFIX_BACKFILL_TRIGGERED=1/" "$MARKER_FILE"
        else
            echo "PREFIX_BACKFILL_TRIGGERED=1" >> "$MARKER_FILE"
        fi
        info "Backfill histórico de prefix_matched lanzado en background (una sola vez, no bloquea este deploy)"
    fi

    # ── Migraciones DB (rama --update) ──────────────────────────────────────
    # Podado 2026-08-01: con schema_migrations (run_pending_migrations, más
    # arriba) se estableció v2.53.0 como línea base — todo el parque real ya
    # está confirmado en esa versión o posterior. Lo que vivía acá (migración
    # show_* → profile_permissions, y el rename connect_charge→connectcharge
    # más abajo) ya corrió para siempre en cualquier instalación que llegó
    # hasta 2.53.0 — de acá en más son operaciones sobre columnas que
    # schema.sql ya no define, así que quedaron sin destino. Si algún día
    # hace falta reconstruirlas, están en el historial de git de este archivo.
    ok "Migraciones aplicadas"

    # Backfill de cdr_summary_day_area — acotado a partir del último día ya
    # cubierto en la DB, con tope de 31 días. Mecanismo permanente (no
    # migración vieja) — corre en cada deploy para ponerse al día con
    # cualquier día que el cron nocturno se haya salteado. Solo
    # cdr_summary_day_area (no day_reseller, que puede quedar permanentemente
    # vacía sin resellers configurados).
    _last_covered=$($_UMC "$_UDB_NAME" -N -e "
        SELECT COALESCE((SELECT MAX(summary_date) FROM cdr_summary_day_area), '1970-01-01')
    " 2>/dev/null || echo "1970-01-01")
    _rday="$(date -d "$_last_covered +1 day" +%Y-%m-%d)"
    _ryesterday="$(date -d yesterday +%Y-%m-%d)"
    _cap_date="$(date -d "-31 days" +%Y-%m-%d)"
    if [[ "$_rday" < "$_cap_date" ]]; then
        warn "Backfill de resumen: hueco de datos más viejo que 31 días (desde $_rday) — se acota al último mes. Correr scripts/cron_summary.py a mano en ventana de mantenimiento para completar el resto."
        _rday="$_cap_date"
    fi
    if [[ "$_rday" > "$_ryesterday" ]]; then
        info "Resumen de reseller/área ya al día — nada que backfillear"
    else
        while [[ ! "$_rday" > "$_ryesterday" ]]; do
            "$INSTALL_DIR/venv/bin/python3" "$INSTALL_DIR/scripts/cron_summary.py" "$_rday" >>"$LOG_FILE" 2>&1 || true
            _rday="$(date -d "$_rday +1 day" +%Y-%m-%d)"
        done
    fi

    # Bloqueo de llamadas nuevas para prepago sin saldo — primera corrida ya
    # con --apply (el cron de cron/voxikam queda habilitado por defecto, cada
    # 1 min, así que no tiene sentido dejarla en modo diagnóstico acá).
    hdr "Bloqueo de saldo (prepago)"
    "$INSTALL_DIR/venv/bin/python3" "$INSTALL_DIR/scripts/sync_balance_block.py" --apply >>"$LOG_FILE" 2>&1 || true
    ok "sync_balance_block.py --apply corrido — ver $LOG_FILE para el detalle de a quién afectó"

    # ── ClickHouse (sip_traces) — solo si ya se aprovisionó en un --upgrade
    # previo (instala el motor, crea el usuario/DB). Claves con prefijo ch_
    # a propósito: _ucred() no entiende secciones del ini, un "port"/"password"
    # bare chocaría con los de [mariadb] (siempre gana el primero que aparece
    # en el archivo).
    _UCH_PASS=$(_ucred "ch_password")
    _UCH_PORT=$(_ucred "ch_port")
    _UCH_NATIVE_PORT=$(_ucred "ch_native_port")
    if [[ -n "$_UCH_PASS" && -n "$_UCH_NATIVE_PORT" ]]; then
        # ch_native_port — protocolo NATIVO que habla clickhouse-client, NO
        # ch_port (ese es el puerto HTTP que usa clickhouse-connect desde Python).
        clickhouse-client --host 127.0.0.1 --port "$_UCH_NATIVE_PORT" --user voxikam --password "$_UCH_PASS" \
            < "$INSTALL_DIR/db/clickhouse_schema.sql" >>"$LOG_FILE" 2>&1 \
            && ok "Schema ClickHouse verificado" \
            || warn "No se pudo aplicar db/clickhouse_schema.sql — revisar $LOG_FILE"
    else
        info "ClickHouse no aprovisionado todavía en este install — correr --upgrade una vez para instalarlo"
    fi

    # ── Frontend Next.js ───────────────────────────────────────────────────────
    build_frontend

    # ── Crontab ────────────────────────────────────────────────────────────────
    setup_voxikam_crontab

    # ── Directorio de datos runtime ────────────────────────────────────────────
    # voxikam:voxikam (no root:root) — hep_listener.py corre como voxikam y
    # necesita escribir hep_stats.json ahí; cron_dlg_stats.py corre como root
    # (cron) y puede escribir en un directorio de otro dueño sin problema.
    mkdir -p /var/lib/voxikam
    chown voxikam:voxikam /var/lib/voxikam
    # Generar snapshot inicial de dlg.stats_active para que la API live no arranque en blanco
    "$INSTALL_DIR/venv/bin/python3" "$INSTALL_DIR/scripts/cron_dlg_stats.py" 2>/dev/null || true

    # Kamailio/RTPEngine: logging (rsyslog+logrotate+journald) y el override de
    # systemd de RTPEngine — antes escrito acá a mano, ahora funciones
    # compartidas con el pipeline --upgrade (ver definición cerca del inicio
    # de este archivo). Corregido de paso: esta rama nunca tenía el tope de
    # journald ni el fix de modprobe xt_RTPENGINE que sí tenía --upgrade.
    setup_kamailio_rtpengine_syslog
    setup_rtpengine_systemd_override

    # ── Permisos scripts ───────────────────────────────────────────────────────
    chown -R voxikam:voxikam "$INSTALL_DIR"
    chmod +x "$INSTALL_DIR/scripts/"*.py
    # Grupo kamailio: voxikam necesita acceder al socket kamcmd para timeseries
    getent group kamailio > /dev/null 2>&1 && usermod -aG kamailio voxikam && \
        ok "voxikam → grupo kamailio (kamcmd accessible)" || true
    ok "Permisos aplicados"

    # ── Actualizar service files (rename sip- → voxikam-) ───────────────
    sync_systemd_service_files

    # ── Reiniciar servicios de aplicación (Kamailio NO se toca) ───────────────
    hdr "Reiniciando servicios"
    systemctl daemon-reload
    systemctl enable voxikam-backend voxikam-frontend voxikam-hep 2>/dev/null || true
    for _svc in voxikam-backend voxikam-frontend voxikam-hep; do
        systemctl restart "$_svc" \
            && ok "Reiniciado: $_svc" \
            || warn "$_svc falló — revisar: journalctl -u $_svc -n 20"
    done
    nginx -t >>"$LOG_FILE" 2>&1 && systemctl reload nginx && ok "Nginx recargado"

    # ── Marcador de versión ────────────────────────────────────────────────────
    # Esta rama (MODE=="update") hace `exit 0` al final sin pasar nunca por el
    # bloque que escribe $MARKER_FILE (ese solo corre para fresh/upgrade/reinstall
    # — ver más abajo). Sin esto, "Actualizar" (la opción "rápida, recomendada"
    # del menú) sincroniza el código y reinicia los servicios correctamente, pero
    # el próximo `./deploy.sh` seguía mostrando la versión vieja en "Versión
    # instalada" — el marcador nunca se actualizaba aunque la actualización sí
    # se hubiera aplicado.
    if [[ -f "$MARKER_FILE" ]]; then
        sed -i "s/^VERSION=.*/VERSION=${INSTALLER_VERSION}/" "$MARKER_FILE"
        # LAST_DEPLOY_DATE — igual criterio que VERSION arriba: sin esto no
        # queda ningún registro de "cuándo fue la última vez que se corrió
        # update/upgrade", pedido explícito para verlo en el log de cada corrida.
        # grep+sed (no append ciego) — marcadores de instalaciones de antes de
        # este campo no lo tienen todavía, hay que agregarlo la primera vez.
        if grep -q "^LAST_DEPLOY_DATE=" "$MARKER_FILE"; then
            sed -i "s/^LAST_DEPLOY_DATE=.*/LAST_DEPLOY_DATE=$(date -Iseconds)/" "$MARKER_FILE"
        else
            echo "LAST_DEPLOY_DATE=$(date -Iseconds)" >> "$MARKER_FILE"
        fi
        ok "Marcador actualizado → v${INSTALLER_VERSION}"
    fi

    # ── ClickHouse: reevaluar cap de memoria (ver sync_ch_memory_cap arriba) ──
    sync_ch_memory_cap

    # ── Health check ───────────────────────────────────────────────────────────
    sleep 4
    echo ""
    _ALL_OK=true
    for _svc in voxikam-backend voxikam-frontend voxikam-hep; do
        systemctl is-active --quiet "$_svc" \
            && ok "$_svc activo" \
            || { err "$_svc no está corriendo — journalctl -u $_svc -n 20"; _ALL_OK=false; }
    done

    _ELAPSED=$(( SECONDS - INSTALL_START ))
    _ELAPSED_FMT="$(( _ELAPSED / 60 ))m $(( _ELAPSED % 60 ))s"

    echo ""
    if $_ALL_OK; then
        echo -e "  ${BOLD}${GREEN}✓ Actualización completada — Kamailio no fue tocado${NC}"
    else
        echo -e "  ${BOLD}${YELLOW}⚠ Actualización con advertencias — revisar servicios${NC}"
    fi
    echo -e "  ${BOLD}Tiempo total:${NC} $_ELAPSED_FMT"
    echo -e "  ${BOLD}Log:${NC}          $LOG_FILE"
    echo ""
    echo -e "  ${BOLD}Visítanos en:${NC} github.com/KPBTec/VoxiKam"
    echo ""
    exit 0
fi

# =============================================================================
# PASO 1-3 — Validaciones y dependencias (delegado a scripts)
# =============================================================================
bash "$INSTALL_DIR/scripts/setup/01_check_os.sh"
bash "$INSTALL_DIR/scripts/setup/02_disable_fw.sh"
bash "$INSTALL_DIR/scripts/setup/03_install_deps.sh"
bash "$INSTALL_DIR/scripts/setup/04_install_sip_stack.sh"
bash "$INSTALL_DIR/scripts/setup/05_install_clickhouse.sh"

# Helpers de input (disponibles tanto para fresh como para upgrade si se re-preguntan)
ask() {
    local txt="$1" def="$2" var="$3" val=""
    if [[ -n "$def" ]]; then
        read -r -p "  $txt [$def]: " val
        printf -v "$var" "%s" "${val:-$def}"
    else
        while [[ -z "$val" ]]; do read -r -p "  $txt (requerido): " val; done
        printf -v "$var" "%s" "$val"
    fi
}
ask_secret() {
    local txt="$1" var="$2" v1="" v2=""
    while true; do
        read -r -s -p "  $txt: " v1; echo ""
        read -r -s -p "  Confirmar: " v2; echo ""
        [[ "$v1" == "$v2" && ${#v1} -ge 8 ]] && { printf -v "$var" "%s" "$v1"; break; }
        [[ ${#v1} -lt 8 ]] && warn "Mínimo 8 caracteres." || warn "No coinciden."
    done
}

# =============================================================================
# PASO 4 — Configuración
# =============================================================================
hdr "Configuración"

if [[ "$MODE" == "upgrade" ]]; then
    # ── UPGRADE: cargar valores desde credentials.conf ────────────────────────
    if [[ ! -f "$LOG_DIR/credentials.conf" ]]; then
        err "No se encontraron credenciales en $LOG_DIR/credentials.conf"
        err "Para instalar desde cero usa: ./deploy.sh --fresh"
        exit 1
    fi
    ln -sf "$LOG_DIR/credentials.conf" "$INSTALL_DIR/credentials.conf"
    _cred() { (grep -m1 "^\s*$1\s*=" "$LOG_DIR/credentials.conf" 2>/dev/null || true) | awk -F'= ' '{print $2}' | tr -d '[:space:]'; }

    DOMAIN=$(      _cred "domain")
    WEB_PORT=$(    _cred "web_port")
    PUBLIC_IP=$(   _cred "public_ip")
    PRIVATE_IP=$(  _cred "private_ip")
    PRIVATE_NET=$( _cred "private_net")
    MGMT_IP=$(     _cred "mgmt_ip")
    SSH_PORT=$(    _cred "ssh_port")
    DB_PORT=$(     _cred "port")
    DB_ROOT_PASS=$(_cred "root_password")
    DB_USER=$(     _cred "user")
    DB_PASS=$(     _cred "password")
    DB_NAME=$(     _cred "database")
    JWT_SECRET=$(  _cred "jwt_secret")
    ADMIN_EMAIL=$( _cred "admin_email")
    CH_PORT=$(        _cred "ch_port")
    CH_NATIVE_PORT=$( _cred "ch_native_port")
    CH_PASS=$(        _cred "ch_password")

    # Fallbacks para campos no presentes en instalaciones antiguas.
    # sshd_config primero (autoritativo) — "ss | grep sshd" puede matchear un
    # socket de X11 forwarding de una sesión SSH activa (ej. puerto 6010 =
    # 6000+display de `ssh -X`), no el puerto real de sshd.
    if [[ -z "$SSH_PORT" ]]; then
        SSH_PORT=$(grep -E '^\s*Port\s+[0-9]' /etc/ssh/sshd_config 2>/dev/null | awk '{print $2}' | head -1 || true)
        [[ -z "$SSH_PORT" ]] && SSH_PORT=$(ss -tlnp 2>/dev/null | grep sshd | awk '{print $4}' | grep -oP '\d+$' | head -1 || true)
        [[ -z "$SSH_PORT" ]] && SSH_PORT=22
    fi
    # Nombre real del unit systemd (ssh.service en Debian/Ubuntu, sshd.service
    # en RHEL/CentOS) — necesario para journalmatch del jail sshd de fail2ban.
    SSH_SERVICE=$(systemctl list-unit-files --type=service 2>/dev/null \
        | awk '{print $1}' | grep -E '^sshd?\.service$' | head -1 || true)
    [[ -z "$SSH_SERVICE" ]] && SSH_SERVICE="ssh.service"
    [[ -z "$MGMT_IP"    ]] && MGMT_IP="10.100.254.1"
    [[ -z "$PRIVATE_NET" ]] && PRIVATE_NET="10.0.0.0/8"
    # ClickHouse: instalaciones que venían de antes de esta migración no
    # tienen [clickhouse] en credentials.conf todavía — se genera una vez acá
    # y PASO 6b (más abajo) crea el usuario/DB con este mismo valor. Puertos
    # random (no los de fábrica 8123/9000), mismo criterio que MariaDB arriba.
    [[ -z "$CH_PORT" ]]        && CH_PORT=$(shuf -i 38100-38999 -n 1)
    [[ -z "$CH_NATIVE_PORT" ]] && CH_NATIVE_PORT=$(shuf -i 39100-39999 -n 1)
    [[ -z "$CH_PASS" ]] && CH_PASS=$(openssl rand -base64 24 | tr -d '/+=' | head -c 28)
    # PASO 5 (guardar credentials.conf) se salta en modo upgrade — sin esto,
    # el CH_PASS recién generado arriba se perdería al terminar esta corrida
    # y la siguiente --upgrade generaría OTRO distinto sin encontrar nunca el
    # anterior, dejando a ClickHouse con un usuario creado con un password que
    # ya no coincide con ningún backend/.env. Se agrega la sección UNA sola
    # vez (append, no se reescribe el resto del archivo) si todavía no existe.
    if ! grep -q '^\[clickhouse\]' "$LOG_DIR/credentials.conf" 2>/dev/null; then
        cat >> "$LOG_DIR/credentials.conf" <<EOF

[clickhouse]
ch_host        = 127.0.0.1
ch_port        = $CH_PORT
ch_native_port = $CH_NATIVE_PORT
ch_database    = sip_platform
ch_user        = voxikam
ch_password    = $CH_PASS
EOF
        ok "Sección [clickhouse] agregada a $LOG_DIR/credentials.conf (primera vez tras esta migración)"
    elif ! grep -q '^ch_native_port' "$LOG_DIR/credentials.conf" 2>/dev/null; then
        # Sección [clickhouse] de una corrida intermedia (versión de este
        # parche previa a agregar el puerto nativo random) — se repara sin
        # tocar el resto de la sección.
        sed -i "/^\[clickhouse\]/a ch_native_port = $CH_NATIVE_PORT" "$LOG_DIR/credentials.conf"
        ok "ch_native_port agregado a la sección [clickhouse] existente"
    fi

    ok "Credenciales cargadas de $LOG_DIR/credentials.conf"
    ok "Dominio: $DOMAIN | Puerto web: $WEB_PORT | DB puerto: $DB_PORT"
    echo ""

    # MC disponible para PASO 7 (schema) sin re-crear la DB
    MC="mysql --user=root --password=$DB_ROOT_PASS --host=127.0.0.1 --port=$DB_PORT"

else
    # ── FRESH/REINSTALL: preguntas interactivas, defaults auto-detectados ─────
    # Misma UX que VoxiKam ya tenía: se pregunta UNA vez en esta misma corrida
    # (nada de editar archivos ni volver a correr el script), con lo detectable
    # ya pre-llenado como default — ENTER acepta, o se edita ahí mismo. Una vez
    # guardado en credentials.conf, las corridas futuras (--upgrade/--update)
    # ya no vuelven a preguntar nada, leen del archivo directo.
    echo ""
    info "Detectando IPs del sistema..."
    DETECTED_PUBLIC=""
    for svc in "https://api.ipify.org" "https://ifconfig.me" "https://icanhazip.com"; do
        DETECTED_PUBLIC=$(curl -s --max-time 4 "$svc" 2>/dev/null | tr -d '[:space:]')
        [[ -n "$DETECTED_PUBLIC" ]] && break
    done

    DETECTED_PRIVATE=$(ip -4 addr show \
        | grep -oP '(?<=inet\s)\d+(\.\d+){3}' \
        | grep -E '^(10\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.)' \
        | head -1)
    [[ -z "$DETECTED_PRIVATE" ]] && DETECTED_PRIVATE=$(ip -4 addr show \
        | grep -oP '(?<=inet\s)\d+(\.\d+){3}' \
        | grep -v '^127\.' \
        | head -1)

    DETECTED_NET=""
    [[ -n "$DETECTED_PRIVATE" ]] && DETECTED_NET=$(ip -4 addr show \
        | grep -oP "inet \d+(\.\d+){3}/\d+" | grep "${DETECTED_PRIVATE}" | head -1 \
        | awk '{print $2}' \
        | python3 -c "import sys,ipaddress; n=ipaddress.IPv4Interface(sys.stdin.read().strip()); print(n.network)" 2>/dev/null || true)

    # sshd_config primero (autoritativo) — "ss | grep sshd" puede matchear un
    # socket de X11 forwarding de una sesión SSH activa (ej. puerto 6010 =
    # 6000+display de `ssh -X`), no el puerto real de sshd.
    SSH_PORT=$(grep -E '^\s*Port\s+[0-9]' /etc/ssh/sshd_config 2>/dev/null | awk '{print $2}' | head -1 || true)
    [[ -z "$SSH_PORT" ]] && SSH_PORT=$(ss -tlnp 2>/dev/null | grep sshd | awk '{print $4}' | grep -oP '\d+$' | head -1 || true)
    [[ -z "$SSH_PORT" ]] && SSH_PORT=22

    # Nombre real del unit systemd (ssh.service en Debian/Ubuntu, sshd.service
    # en RHEL/CentOS) — necesario para journalmatch del jail sshd de fail2ban.
    SSH_SERVICE=$(systemctl list-unit-files --type=service 2>/dev/null \
        | awk '{print $1}' | grep -E '^sshd?\.service$' | head -1 || true)
    [[ -z "$SSH_SERVICE" ]] && SSH_SERVICE="ssh.service"

    [[ -n "$DETECTED_PUBLIC"  ]] && ok "IP pública:  $DETECTED_PUBLIC"  || warn "No se detectó IP pública"
    [[ -n "$DETECTED_PRIVATE" ]] && ok "IP privada:  $DETECTED_PRIVATE" || warn "No se detectó IP privada"
    [[ -n "$DETECTED_NET"     ]] && ok "Red privada: $DETECTED_NET"
    ok "Puerto SSH:  $SSH_PORT"
    echo ""
    echo "  Presiona ENTER para aceptar el valor detectado."
    echo ""

    ask "IP pública  (WAN / hacia carriers)"  "$DETECTED_PUBLIC"                   PUBLIC_IP
    ask "IP privada  (LAN / hacia Asterisks)" "$DETECTED_PRIVATE"                  PRIVATE_IP
    ask "Red privada (CIDR)"                   "${DETECTED_NET:-10.100.10.0/24}"    PRIVATE_NET
    ask "IP gestión  (SSH permitido desde)"    "${DEFAULT_MGMT_IP:-10.100.254.1}"   MGMT_IP
    ask "Puerto SSH  (regla nftables)"         "$SSH_PORT"                          SSH_PORT
    ask "Puerto web  (admin + portal)"         "${DEFAULT_WEB_PORT:-7666}"          WEB_PORT
    ask "Dominio     (ej: $DEFAULT_DOMAIN)"    "${DEFAULT_DOMAIN:-sip.example.com}" DOMAIN
    echo ""
    ask "Email admin" "" ADMIN_EMAIL
    ask_secret "Password admin (mín. 8 chars)" ADMIN_PASS

    DB_PORT=$(shuf -i 33100-33999 -n 1)
    DB_ROOT_PASS=$(openssl rand -base64 24 | tr -d '/+=' | head -c 28)
    DB_USER="voxikam"
    DB_PASS=$(openssl rand -base64 24 | tr -d '/+=' | head -c 28)
    DB_NAME="sip_platform"
    JWT_SECRET=$(openssl rand -hex 32)
    CH_PORT=$(shuf -i 38100-38999 -n 1)
    CH_NATIVE_PORT=$(shuf -i 39100-39999 -n 1)
    CH_PASS=$(openssl rand -base64 24 | tr -d '/+=' | head -c 28)

    ok "Configuración lista — MariaDB usará puerto aleatorio $DB_PORT"
fi

# =============================================================================
# PASO 5 — Guardar credenciales (solo fresh/reinstall)
# =============================================================================
if [[ "$MODE" != "upgrade" ]]; then
    hdr "Guardando credenciales"
    cat > "$CREDS_FILE" <<EOF
# KPBTec VoxiKam — Credenciales
# Generado: $(date)
# MANTENER SEGURO — NO COMPARTIR

[general]
install_dir   = $INSTALL_DIR
domain        = $DOMAIN
web_port      = $WEB_PORT
public_ip     = $PUBLIC_IP
private_ip    = $PRIVATE_IP
private_net   = $PRIVATE_NET
mgmt_ip       = $MGMT_IP
ssh_port      = $SSH_PORT

[mariadb]
host          = 127.0.0.1
port          = $DB_PORT
root_password = $DB_ROOT_PASS
database      = $DB_NAME
user          = $DB_USER
password      = $DB_PASS

[clickhouse]
ch_host        = 127.0.0.1
ch_port        = $CH_PORT
ch_native_port = $CH_NATIVE_PORT
ch_database    = sip_platform
ch_user        = voxikam
ch_password    = $CH_PASS

[platform]
admin_email   = $ADMIN_EMAIL
jwt_secret    = $JWT_SECRET
url           = http://$DOMAIN:$WEB_PORT
EOF
    chmod 600 "$CREDS_FILE"
    ok "Credenciales → $CREDS_FILE"

    # Symlink visible en la carpeta del proyecto — mismo espíritu que el .env
    # de VoxiDet (ahí, a la vista), sin mover el archivo real de $LOG_DIR
    # (evita romper el path que ya usa el modo --upgrade y la migración KaplaBilling).
    ln -sf "$CREDS_FILE" "$INSTALL_DIR/credentials.conf"

    cat > "$MARKER_FILE" <<EOF
# KPBTec VoxiKam — archivo de configuración del sistema
# Generado por deploy.sh — no editar manualmente
INSTALL_DIR=$INSTALL_DIR
LOG_DIR=$LOG_DIR
VENV=$INSTALL_DIR/venv
SCRIPTS=$INSTALL_DIR/scripts
INSTALL_DATE=$(date -Iseconds)
LAST_DEPLOY_DATE=$(date -Iseconds)
VERSION=$INSTALLER_VERSION
EOF
    chmod 644 "$MARKER_FILE"
    ok "Marcador del sistema → $MARKER_FILE (v${INSTALLER_VERSION})"
fi

# Para upgrade: actualizar VERSION en el marker existente
if [[ "$MODE" == "upgrade" && -f "$MARKER_FILE" ]]; then
    sed -i "s/^VERSION=.*/VERSION=${INSTALLER_VERSION}/" "$MARKER_FILE"
    if grep -q "^LAST_DEPLOY_DATE=" "$MARKER_FILE"; then
        sed -i "s/^LAST_DEPLOY_DATE=.*/LAST_DEPLOY_DATE=$(date -Iseconds)/" "$MARKER_FILE"
    else
        echo "LAST_DEPLOY_DATE=$(date -Iseconds)" >> "$MARKER_FILE"
    fi
    ok "Marcador actualizado → v${INSTALLER_VERSION}"
fi

# Migración KaplaBilling: MODE se fuerza a "upgrade" pero todavía no existe
# $MARKER_FILE (nunca se creó, porque el bloque de arriba solo escribe
# credenciales/marker cuando MODE != upgrade, y el de actualización de VERSION
# requiere que el marker YA exista). Sin esto, cada corrida futura de
# deploy.sh sin flags volvería a detectar "instalación previa de KaplaBilling"
# y forzar upgrade de nuevo, en vez de mostrar el menú normal update/upgrade.
if [[ "$MODE" == "upgrade" && ! -f "$MARKER_FILE" ]]; then
    cat > "$MARKER_FILE" <<EOF
# KPBTec VoxiKam — archivo de configuración del sistema
# Generado por deploy.sh — no editar manualmente
INSTALL_DIR=$INSTALL_DIR
LOG_DIR=$LOG_DIR
VENV=$INSTALL_DIR/venv
SCRIPTS=$INSTALL_DIR/scripts
INSTALL_DATE=$(date -Iseconds)
LAST_DEPLOY_DATE=$(date -Iseconds)
VERSION=$INSTALLER_VERSION
EOF
    chmod 644 "$MARKER_FILE"
    ok "Marcador del sistema → $MARKER_FILE (v${INSTALLER_VERSION}) — primera vez tras migración"
fi

# =============================================================================
# PASO 6 — MariaDB (solo fresh/reinstall — upgrade reutiliza la existente)
# =============================================================================
if [[ "$MODE" != "upgrade" ]]; then
    hdr "Configurando MariaDB"

    cat > /etc/mysql/mariadb.conf.d/99-voxikam.cnf <<EOF
[mysqld]
port                    = $DB_PORT
bind-address            = 127.0.0.1
character-set-server    = utf8mb4
collation-server        = utf8mb4_unicode_ci
max_connections         = 200
innodb_buffer_pool_size = 256M
slow_query_log          = 1
slow_query_log_file     = /var/log/mysql/slow.log
long_query_time         = 2

[client]
port = $DB_PORT
EOF

    systemctl stop mariadb 2>/dev/null || true
    systemctl enable mariadb
    systemctl start mariadb
    sleep 3
    ok "MariaDB arrancado en puerto $DB_PORT"

    MSOCK="mysql --user=root --socket=/run/mysqld/mysqld.sock --connect-expired-password"

    if $MSOCK -e "SELECT 1" 2>/dev/null; then
        info "MariaDB sin contraseña de root — configurando seguridad inicial..."
        $MSOCK 2>/dev/null <<EOSQL || true
ALTER USER 'root'@'localhost' IDENTIFIED BY '$DB_ROOT_PASS';
DELETE FROM mysql.user WHERE User='';
DELETE FROM mysql.user WHERE User='root' AND Host NOT IN ('localhost','127.0.0.1','::1');
DROP DATABASE IF EXISTS test;
DELETE FROM mysql.db WHERE Db='test' OR Db='test\\_%';
FLUSH PRIVILEGES;
EOSQL
    elif [[ -n "$OLD_DB_ROOT_PASS" ]]; then
        info "Usando contraseña de root previa para configurar..."
        mysql --user=root --password="$OLD_DB_ROOT_PASS" \
              --socket=/run/mysqld/mysqld.sock 2>/dev/null <<EOSQL || true
ALTER USER 'root'@'localhost' IDENTIFIED BY '$DB_ROOT_PASS';
FLUSH PRIVILEGES;
EOSQL
    else
        echo ""
        warn "MariaDB ya tiene contraseña de root. Ingresarla para continuar:"
        read -r -s -p "  Password root actual (vacío si no tiene): " EXISTING_ROOT; echo ""
        if mysql --user=root --password="$EXISTING_ROOT" \
                 --socket=/run/mysqld/mysqld.sock -e "SELECT 1" 2>/dev/null; then
            mysql --user=root --password="$EXISTING_ROOT" \
                  --socket=/run/mysqld/mysqld.sock <<EOSQL
ALTER USER 'root'@'localhost' IDENTIFIED BY '$DB_ROOT_PASS';
FLUSH PRIVILEGES;
EOSQL
        else
            err "No se pudo autenticar como root de MariaDB."; exit 1
        fi
    fi
    ok "Contraseña de root configurada"

    MC="mysql --user=root --password=$DB_ROOT_PASS --host=127.0.0.1 --port=$DB_PORT"
    $MC <<EOSQL
CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '$DB_USER'@'127.0.0.1' IDENTIFIED BY '$DB_PASS';
CREATE USER IF NOT EXISTS '$DB_USER'@'localhost'  IDENTIFIED BY '$DB_PASS';
FLUSH PRIVILEGES;
EOSQL
    ok "MariaDB listo — puerto $DB_PORT | usuario $DB_USER"
fi

# =============================================================================
# PASO 6b — ClickHouse (fresh, upgrade Y reinstall — a diferencia de MariaDB
# arriba, esto SÍ debe correr en upgrade: es infraestructura nueva que no
# existe todavía en ningún install previo a esta migración, y `--upgrade` es
# justo el camino real de producción. Todo el bloque es idempotente (IF NOT
# EXISTS / schema con CREATE TABLE IF NOT EXISTS), así que re-correrlo en
# cada upgrade — incluso cuando ya está todo creado — no rompe nada. Este
# punto del script nunca se alcanza en modo "update" (esa rama hace su
# propio `exit 0` mucho más arriba), así que no hace falta excluirlo aparte.
# =============================================================================
hdr "Configurando ClickHouse"

# Puertos random (no los de fábrica 8123/9000) — mismo criterio que MariaDB
# arriba (menos huella para fingerprinting, aunque igual está atado a
# 127.0.0.1). El archivo completo se escribe UNA sola vez (idempotente por
# presencia del archivo) — reescribirlo entero en cada upgrade no aporta nada
# si los puertos no cambiaron, y corta la captura de trazas un instante. El
# cap de memoria SÍ se reevalúa aparte (sync_ch_memory_cap, ver más arriba)
# incluso cuando el archivo ya existe — la RAM del host puede cambiar después
# de instalar (VPS resizeado) y el cap viejo se queda congelado si no.
_CH_CONF="/etc/clickhouse-server/config.d/99-voxikam.xml"
if [[ ! -f "$_CH_CONF" ]]; then
    cat > "$_CH_CONF" <<EOF
<clickhouse>
    <http_port replace="replace">$CH_PORT</http_port>
    <tcp_port replace="replace">$CH_NATIVE_PORT</tcp_port>
    <!-- Caches de fábrica pensados para clusters analíticos grandes —
         sip_traces acá es una sola tabla chica, no necesita nada de eso.
         Sin bajarlos, el RSS base de ClickHouse en reposo (antes de
         insertar una sola fila) ya ronda los 2GB, confirmado en producción
         — inflaba el tope de memoria de abajo sin necesidad real. -->
    <mark_cache_size>134217728</mark_cache_size>
    <uncompressed_cache_size>0</uncompressed_cache_size>
    <!-- Sin tope, ClickHouse usa los defaults del paquete (pensados para
         servers dedicados grandes) — en una VPS chica compitiendo con
         MariaDB/Kamailio/RTPEngine/Node eso puede llevar a swap o a que el
         OOM-killer mate algo crítico. Valor autoajustado a $CH_MEM_CAP
         arriba, según la RAM real del host — debe quedar por encima del RSS
         base con los caches ya reducidos, o cada insert falla con
         MEMORY_LIMIT_EXCEEDED (confirmado en producción con el tope viejo). -->
    <max_server_memory_usage>$CH_MEM_CAP</max_server_memory_usage>
</clickhouse>
EOF
    chown clickhouse:clickhouse "$_CH_CONF" 2>/dev/null || true
    systemctl restart clickhouse-server
    ok "ClickHouse reconfigurado — puerto HTTP $CH_PORT, puerto nativo $CH_NATIVE_PORT"
else
    sync_ch_memory_cap
fi

# clickhouse-client habla el protocolo NATIVO de ClickHouse, no HTTP — usar
# $CH_PORT (la interfaz HTTP que consume clickhouse-connect desde Python en
# hep_listener.py/traces.py) acá es justamente lo que causaba el "Connection
# reset by peer"/timeout real visto en producción — el cliente nativo
# intentando handshake contra el puerto HTTP.
#
# systemd puede reportar el servicio "activo" antes de que el puerto nativo
# esté realmente aceptando conexiones — 05_install_clickhouse.sh ya espera
# esto en una instalación nueva, pero se salta ese chequeo si el paquete ya
# estaba instalado de una corrida anterior (y acá además puede que se acabe
# de reiniciar con la config nueva de arriba). Se espera acá también.
_CH_READY=false
for _i in $(seq 1 30); do
    clickhouse-client --host 127.0.0.1 --port "$CH_NATIVE_PORT" --query "SELECT 1" &>/dev/null && { _CH_READY=true; break; }
    sleep 1
done
$_CH_READY || { err "clickhouse-server no respondió en el puerto $CH_NATIVE_PORT tras 30s — revisar: journalctl -u clickhouse-server -n 30"; exit 1; }

# ClickHouse permite al usuario 'default' conectar sin password desde
# localhost recién instalado (trust auth) — se usa acá para crear el usuario
# propio de la app, igual que el socket root de MariaDB arriba se usa para
# poner su password y crear el usuario app. Seguro de re-correr: crear un
# usuario/DB que ya existen con IF NOT EXISTS es un no-op.
clickhouse-client --host 127.0.0.1 --port "$CH_NATIVE_PORT" --query "
    CREATE DATABASE IF NOT EXISTS sip_platform;
    CREATE USER IF NOT EXISTS voxikam IDENTIFIED BY '$CH_PASS';
    GRANT ALL ON sip_platform.* TO voxikam;
" || { err "No se pudo crear el usuario/DB de ClickHouse — revisar clickhouse-server"; exit 1; }

clickhouse-client --host 127.0.0.1 --port "$CH_NATIVE_PORT" --user voxikam --password "$CH_PASS" \
    < "$INSTALL_DIR/db/clickhouse_schema.sql"

ok "ClickHouse listo — puerto $CH_PORT | usuario voxikam | DB sip_platform"

# =============================================================================
# PASO 7 — Schema + seed
# =============================================================================
hdr "Cargando base de datos"

# Backup de seguridad justo antes de migrar — este paso corre con los
# servicios ya detenidos (ver "Deteniendo servicios" arriba); si schema.sql
# falla a mitad de camino, bajo `set -e` el script muere ahí mismo y sin esto
# no quedaba ningún camino de vuelta más que restaurar a mano sin saber desde
# qué punto exacto. Separado del backup nocturno (scripts/backup_db.sh) —
# este es específicamente "justo antes de este intento de migración".
mkdir -p /var/backups/voxikam
_PRE_SCHEMA_DUMP="/var/backups/voxikam/pre-schema_$(date +%Y%m%d-%H%M%S).sql.gz"
if mysqldump --single-transaction --user=root --password="$DB_ROOT_PASS" --host=127.0.0.1 --port="$DB_PORT" "$DB_NAME" 2>/dev/null | gzip > "$_PRE_SCHEMA_DUMP" && [[ -s "$_PRE_SCHEMA_DUMP" ]]; then
    info "Backup de seguridad antes de migrar → $_PRE_SCHEMA_DUMP"
else
    warn "No se pudo generar el backup previo a la migración (¿instalación nueva, DB aún vacía?) — se continúa igual"
    rm -f "$_PRE_SCHEMA_DUMP"
fi

if ! $MC "$DB_NAME" < "$INSTALL_DIR/db/schema.sql"; then
    err "schema.sql falló — la base de datos puede haber quedado a medio migrar, y los servicios (voxikam-backend/frontend/hep) siguen detenidos."
    if [[ -f "$_PRE_SCHEMA_DUMP" ]]; then
        err "Restaurar al estado previo a este intento:"
        err "  gunzip -c $_PRE_SCHEMA_DUMP | mysql --user=root --password --host=127.0.0.1 --port=$DB_PORT $DB_NAME"
    fi
    err "Revisar el error de MariaDB arriba, corregirlo, y volver a correr $0 --upgrade. Los servicios NO se reinician solos — no es seguro asumir que el código nuevo funciona contra un schema a medio migrar."
    exit 1
fi

# Privilegios mínimos del usuario de la app — antes era GRANT ALL PRIVILEGES
# (CREATE ROUTINE/TRIGGER/EVENT/DROP/etc., nada de eso lo usa el backend en
# runtime). Se re-aplica en cada deploy (fresh y upgrade), no solo al crear
# el usuario, para que un server ya instalado con el grant viejo también
# converja acá. ALTER se mantiene: cron_partitions.py necesita ALTER TABLE
# para crear/eliminar particiones de cdrs/sip_traces — DROP PARTITION lo
# cubre el privilegio ALTER, no hace falta el DROP (de tablas) separado.
# Sin "|| true" a propósito: si el REVOKE corre pero el GRANT que sigue
# falla, dejar al usuario de la app sin privilegios tumba toda la plataforma
# en el próximo arranque — mejor que el deploy corte acá con el error visible
# a que eso pase en silencio.
if ! $MC <<EOSQL
REVOKE ALL PRIVILEGES, GRANT OPTION FROM '$DB_USER'@'127.0.0.1';
REVOKE ALL PRIVILEGES, GRANT OPTION FROM '$DB_USER'@'localhost';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES, CREATE TEMPORARY TABLES, LOCK TABLES
    ON \`$DB_NAME\`.* TO '$DB_USER'@'127.0.0.1';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES, CREATE TEMPORARY TABLES, LOCK TABLES
    ON \`$DB_NAME\`.* TO '$DB_USER'@'localhost';
FLUSH PRIVILEGES;
EOSQL
then
    err "No se pudo acotar los privilegios de '$DB_USER' — revisar manualmente antes de arrancar los servicios (podría haber quedado sin privilegios)."
    exit 1
fi
ok "Privilegios de '$DB_USER' acotados a lo que el backend realmente usa (sin DROP/CREATE ROUTINE/TRIGGER/EVENT)"

# Upsert de settings que el instalador conoce (funciona en fresh y upgrade)
$MC "$DB_NAME" -e "
INSERT INTO settings (key_name, value, description) VALUES
  ('platform_version', '${INSTALLER_VERSION}', 'Versión instalada de VoxiKam'),
  ('ssh_port',         '${SSH_PORT}',           'Puerto SSH del servidor (para reglas firewall)'),
  ('lan_peers',        '',                      'IPs Asterisk/ViciBox LAN (host:puerto, coma-separados) — genera Grupo 1 dispatcher')
ON DUPLICATE KEY UPDATE value = VALUES(value), description = VALUES(description);
" 2>/dev/null || true

# Migraciones de schema para upgrade (columnas nuevas que IF NOT EXISTS no cubre)
if [[ "$MODE" == "upgrade" ]]; then
    # ── Migraciones DB (rama --upgrade) ─────────────────────────────────────
    # Podado 2026-08-01: con schema_migrations (run_pending_migrations, más
    # arriba en este archivo) se estableció v2.53.0 como línea base — todo el
    # parque real ya está confirmado en esa versión o posterior. Lo que vivía
    # acá (migración show_* → profile_permissions, ui_theme, y el rename
    # connect_charge→connectcharge) ya corrió para siempre en cualquier
    # instalación que llegó hasta 2.53.0 — son operaciones sobre columnas que
    # schema.sql ya no define, quedaron sin destino. Antes de esto ya se
    # había podado una vez (2026-07-27, ver historial de git) verificando
    # contra un dump real de producción — este es el mismo criterio, un paso
    # más adelante ahora que existe un mecanismo de versión real en vez de
    # tener que re-verificar a mano cada vez.
    run_pending_migrations "$MC" "$DB_NAME"

    # Backfill de cdr_summary_day_area — acotado a partir del último día ya
    # cubierto en la DB, con tope de 31 días. Mecanismo permanente (no
    # migración vieja) — corre en cada deploy para ponerse al día con
    # cualquier día que el cron nocturno se haya salteado.
    _last_covered=$($MC "$DB_NAME" -N -e "
        SELECT COALESCE((SELECT MAX(summary_date) FROM cdr_summary_day_area), '1970-01-01')
    " 2>/dev/null || echo "1970-01-01")
    _rday="$(date -d "$_last_covered +1 day" +%Y-%m-%d)"
    _ryesterday="$(date -d yesterday +%Y-%m-%d)"
    _cap_date="$(date -d "-31 days" +%Y-%m-%d)"
    if [[ "$_rday" < "$_cap_date" ]]; then
        warn "Backfill de resumen: hueco de datos más viejo que 31 días (desde $_rday) — se acota al último mes. Correr scripts/cron_summary.py a mano en ventana de mantenimiento para completar el resto."
        _rday="$_cap_date"
    fi
    if [[ "$_rday" > "$_ryesterday" ]]; then
        info "Resumen de reseller/área ya al día — nada que backfillear"
    else
        while [[ ! "$_rday" > "$_ryesterday" ]]; do
            "$INSTALL_DIR/venv/bin/python3" "$INSTALL_DIR/scripts/cron_summary.py" "$_rday" 2>/dev/null || true
            _rday="$(date -d "$_rday +1 day" +%Y-%m-%d)"
        done
    fi

    # Bloqueo de saldo (prepago) — mecanismo permanente, prime inmediato en
    # deploy (el cron de cada minuto lo toma de todos modos).
    "$INSTALL_DIR/venv/bin/python3" "$INSTALL_DIR/scripts/sync_balance_block.py" --apply 2>/dev/null || true

    ok "Schema aplicado — migraciones de columnas aplicadas"
    ok "platform_version → v${INSTALLER_VERSION}"
else
    ok "Schema cargado — seed se ejecutará después del venv (necesita bcrypt)"
fi

# =============================================================================
# PASO 8 — Aplicar configs estáticos (sed) + .env (gen_configs.py)
# =============================================================================
hdr "Aplicando archivos de configuración"

# Función que aplica sed a un archivo fuente y lo copia al destino
apply_conf() {
    local src="$1" dst="$2"
    mkdir -p "$(dirname "$dst")"
    sed \
        -e "s|__PUBLIC_IP__|$PUBLIC_IP|g"     \
        -e "s|__PRIVATE_IP__|$PRIVATE_IP|g"   \
        -e "s|__PRIVATE_NET__|$PRIVATE_NET|g" \
        -e "s|__MGMT_IP__|$MGMT_IP|g"         \
        -e "s|__SSH_PORT__|$SSH_PORT|g"       \
        -e "s|__WEB_PORT__|$WEB_PORT|g"       \
        -e "s|__DOMAIN__|$DOMAIN|g"           \
        -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" \
        "$src" > "$dst"
    ok "$dst"
}

# Si scripts/setup_tls.sh ya corrió, certbot editó el vhost real en vivo
# para agregar el bloque HTTPS + redirect — pisarlo acá con la plantilla del
# repo (HTTP puro) lo deshace en cada deploy. Ver setup_tls.sh para el detalle.
if grep -q "^TLS_ENABLED=1" "$MARKER_FILE" 2>/dev/null; then
    info "TLS activo — se conserva el vhost de nginx tal cual lo dejó certbot (no se sobrescribe)"
else
    apply_conf "$INSTALL_DIR/nginx/voxikam.conf"  "/etc/nginx/sites-available/voxikam.conf"
fi
apply_conf "$INSTALL_DIR/nftables/nftables.conf"   "/etc/nftables.conf"
apply_conf "$INSTALL_DIR/rtpengine/rtpengine.conf" "/etc/rtpengine/rtpengine.conf"

# nftables.d — archivos dinámicos generados por gen_nftables.py desde la DB.
# En fresh/reinstall: copiar las plantillas vacías del repo (punto de partida limpio).
# En upgrade: NO tocar — gen_nftables.py los regenerará en PASO 12b con los datos reales.
mkdir -p /etc/nftables.d
if [[ "$MODE" != "upgrade" ]]; then
    cp "$INSTALL_DIR/nftables/nftables.d/carriers.nft"     /etc/nftables.d/carriers.nft
    cp "$INSTALL_DIR/nftables/nftables.d/customers.nft"    /etc/nftables.d/customers.nft
    cp "$INSTALL_DIR/nftables/nftables.d/manual_rules.nft" /etc/nftables.d/manual_rules.nft
fi

# =============================================================================
# PASO 8a2 — fail2ban (sshd + rechazos de seguridad del backend)
# =============================================================================
hdr "fail2ban"

# Incondicional (no solo "si falta fail2ban-client"): apt-get install es
# idempotente, y así una dependencia nueva (ej. python3-systemd, agregado
# después de que fail2ban ya estaba instalado en servidores previos) se
# garantiza en cada deploy, no solo en la instalación inicial.
# python3-systemd: bindings que fail2ban necesita para backend=systemd
# (jail sshd lee journald). Sin este paquete el jail sshd falla al
# inicializar ("No module named 'systemd'") y arrastra a TODO el
# servicio fail2ban (exit 255, no reinicia por RestartPreventExitStatus).
apt-get install -y -q fail2ban python3-systemd >/dev/null 2>&1 \
    || warn "No se pudo instalar fail2ban — continúa sin esta capa"

if command -v fail2ban-client &>/dev/null; then
    mkdir -p /etc/fail2ban/filter.d /etc/fail2ban/jail.d
    cp "$INSTALL_DIR/fail2ban/filter.d/voxikam-security.conf" /etc/fail2ban/filter.d/voxikam-security.conf
    sed -e "s|__SSH_PORT__|${SSH_PORT}|g" -e "s|__SSH_SERVICE__|${SSH_SERVICE}|g" \
        "$INSTALL_DIR/fail2ban/jail.d/voxikam.conf" > /etc/fail2ban/jail.d/voxikam.conf
    ok "jails copiados (sshd puerto $SSH_PORT, voxikam-security)"

    systemctl enable fail2ban 2>/dev/null
    systemctl restart fail2ban \
        && ok "fail2ban activo" \
        || warn "fail2ban no arrancó — revisar: journalctl -u fail2ban -n 30"
else
    warn "fail2ban no disponible — sin protección de fuerza bruta"
fi

# CDR_INGEST_SECRET — protege POST /api/admin/cdrs/ingest (encontrado sin
# ninguna autenticación en la auditoría de seguridad global, v2.38.0: cualquiera
# en Internet que supiera la IP registrada de un cliente podía vaciarle el
# saldo con un POST fabricado, sin login). Se preserva entre corridas leyendo
# el valor ya desplegado en backend/.env — así un --update posterior nunca
# invalida el secreto que Kamailio (si algún día llega a llamar este endpoint)
# ya tendría configurado. Se genera nuevo solo la primera vez.
CDR_INGEST_SECRET=""
if [[ -f "$INSTALL_DIR/backend/.env" ]]; then
    CDR_INGEST_SECRET=$(grep -m1 '^CDR_INGEST_SECRET=' "$INSTALL_DIR/backend/.env" | cut -d= -f2- || true)
fi
[[ -z "$CDR_INGEST_SECRET" ]] && CDR_INGEST_SECRET=$(openssl rand -hex 32)

CLICKHOUSE_URL="clickhouse://voxikam:${CH_PASS}@127.0.0.1:${CH_PORT}/sip_platform"

# .env files (generados con Jinja2 porque tienen contraseñas de DB, JWT, etc.)
python3 -c "import jinja2" 2>/dev/null || pip3 install -q jinja2
python3 "$INSTALL_DIR/scripts/gen_configs.py" \
    --public-ip   "$PUBLIC_IP"   --private-ip  "$PRIVATE_IP" \
    --private-net "$PRIVATE_NET" --mgmt-ip     "$MGMT_IP"    \
    --web-port    "$WEB_PORT"    --domain      "$DOMAIN"     \
    --db-host     "127.0.0.1"   --db-port     "$DB_PORT"    \
    --db-name     "$DB_NAME"    --db-user      "$DB_USER"    \
    --db-pass     "$DB_PASS"    --jwt-secret   "$JWT_SECRET" \
    --cdr-ingest-secret "$CDR_INGEST_SECRET" \
    --clickhouse-url "$CLICKHOUSE_URL" \
    --admin-email "$ADMIN_EMAIL" \
    --install-dir "$INSTALL_DIR"

# =============================================================================
# PASO 8b — Performance tuning (aplica en fresh y upgrade)
# =============================================================================
hdr "Performance tuning del sistema"

# ── sysctl: buffers de red, conntrack, file descriptors ──────────────────────
cat > /etc/sysctl.d/99-voxikam.conf << 'EOF'
# VoxiKam v2.0 — SIP/RTP performance tuning

# Buffers de socket UDP (RTPEngine necesita buffers grandes para bursts)
net.core.rmem_max           = 67108864
net.core.wmem_max           = 67108864
net.core.rmem_default       = 4194304
net.core.wmem_default       = 4194304
net.ipv4.udp_mem            = 65536 131072 262144
net.ipv4.udp_rmem_min       = 131072
net.ipv4.udp_wmem_min       = 131072

# Backlog de paquetes entrantes antes de que el kernel los procese
net.core.netdev_max_backlog = 30000

# File descriptors a nivel del sistema
fs.file-max                 = 2097152

# IP forward (requerido para xt_RTPENGINE en el futuro)
net.ipv4.ip_forward         = 1

# nf_conntrack — tabla más grande, timeouts UDP más cortos para SIP/RTP
net.netfilter.nf_conntrack_max                  = 131072
net.netfilter.nf_conntrack_udp_timeout          = 10
net.netfilter.nf_conntrack_udp_timeout_stream   = 30
net.netfilter.nf_conntrack_generic_timeout      = 120
EOF

sysctl -p /etc/sysctl.d/99-voxikam.conf > /dev/null 2>&1 \
    && ok "sysctl aplicado" \
    || warn "sysctl: algunos parámetros no disponibles en este kernel (normal en VMs)"

# ── Blacklist nf_conntrack_sip — interfiere con RTPEngine ────────────────────
cat > /etc/modprobe.d/voxikam-blacklist.conf << 'EOF'
# El helper SIP del kernel parsea y reescribe SDPs — entra en conflicto con RTPEngine
blacklist nf_conntrack_sip
install nf_conntrack_sip /bin/true
EOF
modprobe -r nf_conntrack_sip 2>/dev/null || true
ok "nf_conntrack_sip desactivado"

# ── Systemd override para Kamailio ───────────────────────────────────────────
if systemctl list-units --full -all 2>/dev/null | grep -qE "kamailio(\.service)?"; then
    KAMAILIO_CONFIG_CHANGED=1
    mkdir -p /etc/systemd/system/kamailio.service.d
    cat > /etc/systemd/system/kamailio.service.d/voxikam-limits.conf << EOF
[Unit]
# Sin esto, en un reboot completo no hay garantía de orden entre Kamailio y
# MariaDB — si Kamailio arranca primero, sus workers (módulo sqlops) fallan
# al conectar a la DB y esos procesos hijos mueren (init_child failed),
# incluyendo los procesos timer/secondary timer que corren el sondeo
# periódico de carriers del módulo dispatcher. Si esos no se recuperan solos,
# los carriers quedan marcados caídos indefinidamente sin que nadie los
# vuelva a probar — visto en producción en vd1sbc2 tras un reboot completo.
After=mariadb.service
Requires=mariadb.service

[Service]
LimitNOFILE=65536
LimitMEMLOCK=infinity
LimitCORE=infinity
LimitNPROC=infinity
# Requires=/After= solo garantiza que el UNIT de MariaDB ya arrancó — no que
# ya esté aceptando conexiones (init interna, crash recovery de InnoDB, etc.
# pueden tardar unos segundos más). Sin esto, "Can't connect to server on
# 127.0.0.1" seguía pasando en vd1sbc2 pese al Requires/After de arriba.
# TCP puro (no mysqladmin) para no depender de credenciales ni de que el
# cliente de mysql esté instalado — sale apenas el puerto responde, hasta
# 30s. Si MariaDB nunca responde, arranca igual (fail-open, no bloquea el
# boot indefinidamente) — el ExecStartPre de abajo se encarga de esa espera.
ExecStartPre=/bin/bash -c 'for i in \$(seq 1 30); do (exec 3<>/dev/tcp/127.0.0.1/$DB_PORT) 2>/dev/null && exit 0; sleep 1; done; echo "voxikam: MariaDB no respondió en 127.0.0.1:$DB_PORT tras 30s, arrancando Kamailio igual" >&2; exit 0'
# Al reiniciar Kamailio pierde todos los diálogos → limpiar active_calls inmediatamente
ExecStartPost=/bin/sh -c 'sleep 3 && $INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/scripts/cleanup_active_calls.py >> $LOG_DIR/cleanup.log 2>&1 || true'
EOF
    ok "Kamailio systemd limits → LimitNOFILE=65536, LimitMEMLOCK=infinity + ExecStartPost cleanup + espera activa a MariaDB + After/Requires=mariadb.service"
    # La memoria interna (SHM/PKG) se calcula más abajo, en scripts/autotune.sh
    # (--no-restart) — después de que kamailio.cfg ya se regeneró desde el
    # template, para no duplicar la fórmula en dos lugares.
fi

# Kamailio/RTPEngine: override de systemd de RTPEngine + logging
# (rsyslog+logrotate+journald) — funciones compartidas con la rama --update,
# ver definición cerca del inicio de este archivo.
setup_rtpengine_systemd_override
setup_kamailio_rtpengine_syslog

# NOTA: la memoria compartida de Kamailio (SHM_MEMORY/PKG_MEMORY) se calcula y
# escribe más abajo por scripts/autotune.sh, en /etc/default/kamailio.d/
# voxikam-memory.conf — esas son las variables que realmente usa el ExecStart
# del servicio (`-m $SHM_MEMORY -M $PKG_MEMORY`). Antes acá se escribía además
# un `MEMORY=256` fijo en /etc/default/kamailio que el ExecStart nunca lee —
# variable muerta que solo generaba confusión (parecía un límite real de
# 256MB en cada deploy). Eliminado — ver CHANGELOG v2.24.4.

# ── MariaDB — performance tuning (auto-sizing por RAM disponible) ─────────────
if systemctl is-active mariadb &>/dev/null || systemctl is-active mysql &>/dev/null; then
    TOTAL_MEM_MB=$(free -m | awk '/^Mem:/{print $2}')
    if [[ $TOTAL_MEM_MB -ge 16384 ]]; then
        INNODB_POOL_MB=2048
    elif [[ $TOTAL_MEM_MB -ge 4096 ]]; then
        INNODB_POOL_MB=1024
    else
        INNODB_POOL_MB=512
    fi

    cat > /etc/mysql/mariadb.conf.d/99-voxikam-perf.cnf << EOF
# VoxiKam v2.0 — MariaDB performance tuning
# Auto-calculado: RAM=${TOTAL_MEM_MB}MB → InnoDB pool=${INNODB_POOL_MB}MB
[mysqld]
innodb_buffer_pool_size        = ${INNODB_POOL_MB}M
innodb_flush_log_at_trx_commit = 2
innodb_log_buffer_size         = 32M
innodb_flush_method            = O_DIRECT
EOF

    SVC_DB="mariadb"
    systemctl is-active mysql &>/dev/null && SVC_DB="mysql"
    systemctl restart "$SVC_DB" \
        && ok "MariaDB reiniciado con perf tuning (InnoDB pool=${INNODB_POOL_MB}MB, flush=2)" \
        || warn "MariaDB restart falló — revisar: journalctl -u $SVC_DB -n 20"
fi

# ── NIC ring buffers via udev + aplicar ahora ────────────────────────────────
if command -v ethtool &>/dev/null; then
    cat > /etc/udev/rules.d/71-voxikam-nic.rules << 'EOF'
# VoxiKam v2.0 — ring buffers 4096 en todas las NICs físicas
ACTION=="add", SUBSYSTEM=="net", KERNEL!="lo", DRIVERS=="?*", \
    RUN+="/sbin/ethtool -G $name rx 4096 tx 4096 2>/dev/null || true"
EOF
    for iface in $(ip -br link show | awk '$1 != "lo" {print $1}' | cut -d@ -f1); do
        ethtool -G "$iface" rx 4096 tx 4096 2>/dev/null \
            && ok "NIC $iface ring buffers → rx/tx 4096" \
            || true   # silencioso si la NIC no soporta el tamaño
    done
else
    apt-get install -y -q ethtool 2>/dev/null && ok "ethtool instalado" || true
fi

ok "Performance tuning v2.0 aplicado"

# =============================================================================
# PASO 9 — Python virtualenv + dependencias backend
# =============================================================================
hdr "Backend Python"

python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install -q --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -q -r "$INSTALL_DIR/backend/requirements.txt"
ok "Virtualenv listo"

# Backfill único de prefix_matched para TODO el histórico anterior al
# trigger (agregado en schema.sql, PASO 7 arriba) — mismo motivo y mismo
# guard que la rama --update: ver ese comentario para el detalle completo.
if ! grep -q "^PREFIX_BACKFILL_TRIGGERED=1" "$MARKER_FILE" 2>/dev/null; then
    mkdir -p "$INSTALL_DIR/logs"
    nohup "$INSTALL_DIR/venv/bin/python3" "$INSTALL_DIR/scripts/backfill_prefix_matched.py" --yes \
        >>"$INSTALL_DIR/logs/backfill_prefix_matched.log" 2>&1 &
    if grep -q "^PREFIX_BACKFILL_TRIGGERED=" "$MARKER_FILE" 2>/dev/null; then
        sed -i "s/^PREFIX_BACKFILL_TRIGGERED=.*/PREFIX_BACKFILL_TRIGGERED=1/" "$MARKER_FILE"
    else
        echo "PREFIX_BACKFILL_TRIGGERED=1" >> "$MARKER_FILE"
    fi
    ok "Backfill histórico de prefix_matched lanzado en background (una sola vez, no bloquea este deploy)"
fi

# Particiones cdrs/sip_traces: carve inicial de meses/días reales desde p_future.
# En instalaciones que vienen de antes de v2.12.0 (sin particionar) esto no hace nada
# y lo avisa — requiere scripts/migrate_partitioning.py manual en ventana de mantenimiento.
"$INSTALL_DIR/venv/bin/python3" "$INSTALL_DIR/scripts/cron_partitions.py" >>"$LOG_FILE" 2>&1 || true

# Seed: solo para fresh/reinstall (upgrade conserva usuarios y datos existentes)
if [[ "$MODE" != "upgrade" ]]; then
    ADMIN_HASH=$(ADMIN_PASS="$ADMIN_PASS" "$INSTALL_DIR/venv/bin/python3" - <<'PYEOF'
import os, bcrypt
pwd = os.environ['ADMIN_PASS'].encode()
print(bcrypt.hashpw(pwd, bcrypt.gensalt()).decode())
PYEOF
)
    sed \
        -e "s|__ADMIN_EMAIL__|$ADMIN_EMAIL|g"       \
        -e "s|__ADMIN_HASH__|$ADMIN_HASH|g"         \
        -e "s|__PUBLIC_IP__|$PUBLIC_IP|g"           \
        -e "s|__PRIVATE_IP__|$PRIVATE_IP|g"         \
        -e "s|__SBC_DOMAIN__|$DOMAIN|g"             \
        -e "s|__PLATFORM_NAME__|$PLATFORM_NAME|g"   \
        -e "s|__PLATFORM_VERSION__|$PLATFORM_VERSION|g" \
        -e "s|__SSH_PORT__|$SSH_PORT|g"             \
        "$INSTALL_DIR/db/seed.sql" | $MC "$DB_NAME"
    ok "Seed ejecutado → admin: $ADMIN_EMAIL"
else
    ok "Upgrade: seed omitido — usuarios y datos conservados"
fi

# =============================================================================
# PASO 10 — Next.js build
# =============================================================================
build_frontend

# =============================================================================
# PASO 11 — Firewall nftables
# =============================================================================
hdr "Firewall"

chmod 600 /etc/nftables.conf
systemctl enable nftables
nft -f /etc/nftables.conf
ok "nftables activo"

# =============================================================================
# PASO 12 — Usuario voxikam + permisos + sudoers + servicios systemd
# =============================================================================
hdr "Usuario del sistema y permisos"

# Crear usuario dedicado sin shell (no puede hacer login)
id voxikam &>/dev/null || useradd \
    --system \
    --no-create-home \
    --shell /usr/sbin/nologin \
    --comment "KPBTec VoxiKam service account" \
    voxikam
ok "Usuario voxikam listo"

# Propiedad completa del directorio de instalación
chown -R voxikam:voxikam "$INSTALL_DIR"
chmod 750 "$INSTALL_DIR"

# www-data necesita traversar el directorio para servir estáticos de Next.js
# nginx corre como www-data — sin esta membresía: Permission denied en /_next/static/
usermod -aG voxikam www-data
ok "www-data agregado al grupo voxikam (nginx puede leer estáticos)"

# voxikam necesita acceder al socket de Kamailio para kamcmd dlg.briefing
# el socket /run/kamailio/kamailio_ctl es del grupo kamailio — sin esto: Permission denied
if getent group kamailio > /dev/null 2>&1; then
    usermod -aG kamailio voxikam
    ok "voxikam agregado al grupo kamailio (kamcmd accessible)"
fi

# voxikam necesita leer el journal para el panel Sistema → Salud (estado y
# últimas líneas de log de cada servicio, sin exponer systemctl restart/stop
# al backend — eso queda solo para el CLI `voxikam` por consola, con sudo).
# Sin este grupo, journalctl devuelve "No journal files were opened" para un
# usuario no-root.
usermod -aG systemd-journal voxikam
ok "voxikam agregado al grupo systemd-journal (lee logs de servicios para el panel)"

# Scripts Python ejecutables por voxikam
chmod +x "$INSTALL_DIR/scripts/"*.py
chmod +x "$INSTALL_DIR/scripts/setup/"*.sh

ok "Propiedad de $INSTALL_DIR → voxikam (scripts ejecutables)"

# /var/lib/voxikam/ — hep_listener.py (usuario voxikam) escribe hep_stats.json;
# cron_dlg_stats.py (root vía cron) escribe live_snapshot.json — voxikam:voxikam
# porque root puede escribir en cualquier directorio sin importar el dueño,
# pero voxikam solo puede escribir en el suyo.
mkdir -p /var/lib/voxikam
chown voxikam:voxikam /var/lib/voxikam
ok "Permisos /var/lib/voxikam → voxikam puede escribir"

# /etc/nftables.d/ — voxikam escribe los .nft desde gen_nftables.py
chown root:voxikam /etc/nftables.d
chmod 775 /etc/nftables.d
chown voxikam:voxikam /etc/nftables.d/*.nft 2>/dev/null || true
ok "Permisos /etc/nftables.d → voxikam puede escribir"

# /etc/kamailio/ — dispatcher.list + kamailio.cfg
if [[ -d /etc/kamailio ]]; then
    # dispatcher.list — escrito por gen_dispatcher.py
    touch /etc/kamailio/dispatcher.list 2>/dev/null || true
    chown voxikam:voxikam /etc/kamailio/dispatcher.list 2>/dev/null || true
    ok "Permisos /etc/kamailio/dispatcher.list → voxikam"

    # voxikam-routes.cfg (el mecanismo VIEJO, #!include_file) ya no se usa
    # — reemplazado por el htable "techmap" (respaldado en techprefix_map,
    # MySQL, ver db/schema.sql y templates/kamailio.cfg.j2). Se borra si
    # quedó de una instalación anterior, para no dejar un archivo huérfano
    # que confunda a quien mire /etc/kamailio/ después.
    rm -f /etc/kamailio/voxikam-routes.cfg

    # children= (procesos SIP de Kamailio) estaba fijo en el template (8) sin
    # relación con el CPU real del host — mismo problema que tenían los
    # workers del backend. Autoajustado 1:1 con vCPU detectados (mismo
    # criterio que ya usaba el valor original hardcodeado en un host de 8
    # cores) — los children de Kamailio son mayormente I/O-bound, no CPU-bound,
    # así que compartir 1:1 con el backend/RTPEngine en el mismo host es seguro.
    KAMAILIO_CHILDREN=$(nproc)

    # kamailio.cfg — siempre se regenera desde template (fresh y upgrade)
    # El template es la fuente de verdad; los datos variables van en .env / DB
    sed \
        -e "s|{{ private_ip }}|${PRIVATE_IP}|g" \
        -e "s|{{ public_ip }}|${PUBLIC_IP}|g"   \
        -e "s|{{ db_user }}|${DB_USER}|g"        \
        -e "s|{{ db_pass }}|${DB_PASS}|g"        \
        -e "s|{{ db_port }}|${DB_PORT}|g"        \
        -e "s|{{ db_name }}|${DB_NAME}|g"        \
        -e "s|{{ kamailio_children }}|${KAMAILIO_CHILDREN}|g" \
        -e "s|{{ cps_max_wait_ms }}|2000|g" \
        "$INSTALL_DIR/templates/kamailio.cfg.j2" \
        > /etc/kamailio/kamailio.cfg
    ok "kamailio.cfg actualizado desde template (children=${KAMAILIO_CHILDREN}, detectado de vCPU real)"
    KAMAILIO_CONFIG_CHANGED=1

    # Memoria interna de Kamailio (SHM/PKG) — calculada en scripts/autotune.sh
    # (mismo script que corre solo en cada arranque vía voxikam-autotune.service).
    # --no-restart: acá SÍ puede haber llamadas en vivo ahora mismo, así que
    # solo actualiza el archivo de config y avisa, nunca reinicia Kamailio solo.
    chmod +x "$INSTALL_DIR/scripts/autotune.sh"
    "$INSTALL_DIR/scripts/autotune.sh" --no-restart || warn "autotune.sh terminó con errores — revisar arriba"
else
    warn "/etc/kamailio no existe — instalar Kamailio y luego ejecutar: sudo ./deploy.sh --upgrade"
fi

# sudoers ya se sincronizó arriba, en la sección compartida a todos los modos.

sync_systemd_service_files

systemctl daemon-reload
systemctl enable --now voxikam-backend voxikam-frontend voxikam-hep
ok "voxikam-backend, voxikam-frontend y voxikam-hep habilitados"

# Health-check real — que systemctl no devuelva error solo dice que el
# proceso arrancó, no que quedó sano (crash-loop en el primer request, puerto
# ocupado, excepción en el lifespan, etc.). Antes de esto no había ningún
# chequeo de esto en todo el deploy.
info "Verificando que el backend responda (hasta 20s)..."
_HEALTH_OK=0
for _i in $(seq 1 10); do
    curl -fsS -m 3 "http://127.0.0.1:8000/api/health" >/dev/null 2>&1 && { _HEALTH_OK=1; break; }
    sleep 2
done
if [[ "$_HEALTH_OK" -eq 1 ]]; then
    ok "Backend responde en /api/health"
else
    err "El backend NO respondió a /api/health tras 20s — systemd lo reporta arrancado, pero puede estar crasheando en loop."
    err "Revisar antes de dar el deploy por bueno:  journalctl -u voxikam-backend -n 50 --no-pager"
fi

# voxikam-autotune: SOLO habilitado (no --now) — correrá solo en el PRÓXIMO
# arranque del sistema (ej. tras un resize de CPU/RAM + reboot). No se
# arranca ahora porque su comportamiento por defecto SÍ reinicia Kamailio, y
# durante este deploy puede haber llamadas en vivo (el tuning de esta corrida
# ya lo hizo deploy.sh más arriba, con --no-restart).
if [[ -f "$INSTALL_DIR/systemd/voxikam-autotune.service" ]]; then
    sed -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" \
        "$INSTALL_DIR/systemd/voxikam-autotune.service" \
        > /etc/systemd/system/voxikam-autotune.service
    systemctl daemon-reload
    systemctl enable voxikam-autotune >/dev/null 2>&1
    ok "voxikam-autotune habilitado para el próximo arranque (no corre ahora)"
fi

# =============================================================================
# PASO 12b — Regenerar dispatcher.list + routes.cfg desde DB
# =============================================================================
# En upgrade: los archivos quedan con la versión anterior del script.
# En fresh:   puede haber datos de prueba en la DB (seed).
# Siempre regenerar para que reflejen el código actual y los datos reales.
hdr "Dispatcher Kamailio"

if [[ -d /etc/kamailio ]]; then
    PUBLIC_IP="${PUBLIC_IP}" PRIVATE_IP="${PRIVATE_IP}" \
        "$INSTALL_DIR/venv/bin/python3" "$INSTALL_DIR/scripts/gen_dispatcher.py" \
        && ok "dispatcher.list y routes.cfg regenerados desde DB" \
        || warn "gen_dispatcher.py falló — ejecutar manualmente tras arranque"

    # Reiniciar kamailio si está instalado (recoge nueva config)
    _kam_svc=""
    for _s in kamailio kamailio.service; do
        systemctl list-units --full -all 2>/dev/null | grep -q "$_s" && { _kam_svc="$_s"; break; }
    done
    if [[ -n "$_kam_svc" ]]; then
        systemctl restart "$_kam_svc" && ok "Kamailio reiniciado con nueva config" \
            || warn "Kamailio restart falló — revisar: journalctl -u $_kam_svc -n 20"
    elif pgrep -x kamailio >/dev/null 2>&1; then
        ok "Kamailio corriendo (proceso detectado) — reiniciar manualmente si cambiaste config"
    else
        info "Kamailio no detectado — instalar y luego ejecutar --upgrade"
    fi
fi

# Regenerar reglas de firewall desde DB (carriers + clientes + reglas manuales)
"$INSTALL_DIR/venv/bin/python3" "$INSTALL_DIR/scripts/gen_nftables.py" \
    && ok "nftables regenerado desde DB (carriers, clientes, reglas manuales)" \
    || warn "gen_nftables.py falló — revisar reglas de firewall manualmente"

# =============================================================================
# PASO 13 — Nginx
# =============================================================================
hdr "Nginx"

# Limpiar nombres anteriores si existen — sip-platform.conf (rebrand previo)
# y kaplabilling.conf (migración): ambos definían el mismo limit_req_zone
# api_limit/login_limit a nivel http, y con los dos en sites-enabled/ nginx
# falla con "already bound to key" al recargar (visto en la migración de
# vd1sbc2 — voxikam.conf nuevo + kaplabilling.conf viejo cargados a la vez).
rm -f /etc/nginx/sites-enabled/sip-platform.conf /etc/nginx/sites-available/sip-platform.conf
rm -f /etc/nginx/sites-enabled/kaplabilling.conf /etc/nginx/sites-available/kaplabilling.conf
ln -sf /etc/nginx/sites-available/voxikam.conf /etc/nginx/sites-enabled/voxikam.conf
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
ok "Nginx en puerto $WEB_PORT"

# =============================================================================
# PASO 14 — Crontab
# =============================================================================
setup_voxikam_crontab

# =============================================================================
# PASO 15 — Health checks
# =============================================================================
hdr "Verificando instalación"

sleep 5
ALL_OK=true

chk_svc() {
    systemctl is-active --quiet "$1" && ok "$1 corriendo" \
        || { err "$1 falló — revisar: journalctl -u $1 -n 20"; ALL_OK=false; }
}
chk_http() {
    curl -sf --max-time 5 "http://127.0.0.1:$2$3" > /dev/null \
        && ok "$1 responde en :$2" || warn "$1 aún no responde (puede tardar)"
}

chk_svc mariadb
chk_svc nginx
chk_svc voxikam-backend
chk_svc voxikam-frontend
chk_svc voxikam-hep
chk_http "FastAPI"  8000      "/api/health"
chk_http "Next.js"  3000      "/"
chk_http "Nginx"    "$WEB_PORT" "/health"

# =============================================================================
# RESUMEN
# =============================================================================
_ELAPSED=$(( SECONDS - INSTALL_START ))
_ELAPSED_FMT="$(( _ELAPSED / 60 ))m $(( _ELAPSED % 60 ))s"

echo ""
_BAR="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ "$ALL_OK" == false ]]; then
    echo -e "${YELLOW}${_BAR}${NC}"
    if [[ "$MODE" == "upgrade" ]]; then
        echo -e "${YELLOW}  Upgrade completado con advertencias ⚠${NC}"
    else
        echo -e "${YELLOW}  Instalación con errores — revisar ✗${NC}"
    fi
    echo -e "${YELLOW}${_BAR}${NC}"
    echo ""
    echo "  URL:    http://$DOMAIN:$WEB_PORT"
    echo "  Admin:  $ADMIN_EMAIL"
    [[ "$MODE" != "upgrade" ]] && echo "  Creds:  $CREDS_FILE"
    echo "  Log:    $LOG_FILE"
    [[ "$MODE" == "upgrade" ]] && echo "  Datos y credenciales: conservados"
    echo ""
    echo "  Diagnóstico:"
    echo "    journalctl -u voxikam-backend -n 30 --no-pager"
    echo "    journalctl -u voxikam-frontend -n 30 --no-pager"
    echo "    journalctl -u voxikam-hep -n 30 --no-pager"
    echo ""
    echo "  Tiempo: $_ELAPSED_FMT"
else
    echo -e "${GREEN}${_BAR}${NC}"
    if [[ "$MODE" == "upgrade" ]]; then
        echo -e "${GREEN}  Upgrade completado ✓${NC}"
    else
        echo -e "${GREEN}  Instalación completada ✓${NC}"
    fi
    echo -e "${GREEN}${_BAR}${NC}"
    echo ""
    echo "  URL:    http://$DOMAIN:$WEB_PORT"
    echo "  Admin:  $ADMIN_EMAIL"
    [[ "$MODE" != "upgrade" ]] && echo "  Creds:  $CREDS_FILE"
    echo "  Log:    $LOG_FILE"
    [[ "$MODE" == "upgrade" ]] && echo "  Datos y credenciales: conservados"
    echo ""
    echo "  Tiempo: $_ELAPSED_FMT"
fi
echo ""
echo "  Visítanos en: github.com/KPBTec/VoxiKam"
echo "  $PLATFORM_NAME · un desarrollo de KPBTec"
echo ""

if [[ "${KAMAILIO_CONFIG_CHANGED:-0}" == "1" ]]; then
    warn "PENDIENTE: reiniciar Kamailio manualmente"
    echo "  Este deploy regeneró kamailio.cfg y/o la memoria interna (SHM/PKG) —"
    echo "  el cambio NO toma efecto hasta reiniciar, y eso corta TODAS las"
    echo "  llamadas activas en el momento del restart."
    echo "  Hacerlo en horario de baja carga:  systemctl restart kamailio"
    echo ""
    echo "  Si este --upgrade es el que introduce el htable \"techmap\" (Grupos"
    echo "  de ruteo por techprefix, reemplaza voxikam-routes.cfg): DESPUÉS de"
    echo "  este restart, altas/bajas de clientes/prefijos/grupos vuelven a"
    echo "  aplicar en caliente solas (gen_dispatcher.py dispara \`kamcmd"
    echo "  htable.reload techmap\`) — no hace falta reiniciar de nuevo para eso."
    echo ""
fi
