#!/bin/bash
# =============================================================================
# la plataforma anterior — SIP Class 4 Billing & Monitoring Platform
#
# Copyright (c) 2025 KPBTec
# MIT License — https://github.com/KPBTec/kaplabilling/blob/main/LICENSE
# Contact & support: https://t.me/KPBTec
#
# By KPBTec
# =============================================================================
# Instalador
#
# Uso recomendado:
#   git clone <repo> /opt/kaplabilling
#   cd /opt/kaplabilling
#   sudo ./install.sh
#
# Flags opcionales (omitir para menú interactivo):
#   --update     Código + migraciones + frontend, SIN reiniciar Kamailio (rápido)
#   --upgrade    Actualizar código, schema, configs y Kamailio (completo)
#   --reinstall  Borrar todo y reinstalar desde cero
#
# El directorio de instalación es donde está este script.
# Queda guardado en /etc/kaplabilling.conf para referencia futura.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$SCRIPT_DIR"             # puede cambiar si hay instalación previa en otra ruta
MARKER_FILE="/etc/kaplabilling.conf"   # ubicación fija — siempre encontrable

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

LOG_DIR="/kaplabilling-install/logs-configs"
CREDS_FILE="$LOG_DIR/credentials.conf"

[[ $EUID -ne 0 ]] && { err "Ejecutar como root: sudo ./install.sh"; exit 1; }

mkdir -p "$LOG_DIR"; chmod 700 "$LOG_DIR"
LOG_FILE="$LOG_DIR/install-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo ""
echo -e "${BOLD}${CYAN}"
echo "  ╔══════════════════════════════════════════════╗"
printf "  ║    %-28s v%-8s║\n" "$PLATFORM_NAME" "$PLATFORM_VERSION"
echo "  ╚══════════════════════════════════════════════╝"
echo -e "${NC}"
echo -e "  ${BOLD}Plataforma:${NC} $PLATFORM_NAME v$PLATFORM_VERSION"
echo -e "  ${BOLD}Directorio origen:${NC} $SCRIPT_DIR"
echo -e "  ${BOLD}Usuario:${NC}           kaplabilling  (sin shell, sin login — solo servicios)"
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
            DROP USER IF EXISTS 'kaplabilling'@'127.0.0.1'; \
            DROP USER IF EXISTS 'kaplabilling'@'localhost'; \
            FLUSH PRIVILEGES;" 2>/dev/null
}

if [[ -f "$MARKER_FILE" && "$MODE" == "fresh" ]]; then
    # Cargar versión instalada desde el marker
    _INSTALLED_VERSION=$(grep "^VERSION=" "$MARKER_FILE" 2>/dev/null | cut -d= -f2 | tr -d '[:space:]' || echo "desconocida")
    _INSTALLED_DATE=$(grep "^INSTALL_DATE=" "$MARKER_FILE" 2>/dev/null | cut -d= -f2 | tr -d '[:space:]' || echo "")

    echo ""
    echo -e "  ${BOLD}${YELLOW}╔══════════════════════════════════════════════════╗${NC}"
    echo -e "  ${BOLD}${YELLOW}║     Instalación existente detectada              ║${NC}"
    echo -e "  ${BOLD}${YELLOW}╚══════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${BOLD}Versión instalada:${NC}  v${_INSTALLED_VERSION:-?}"
    echo -e "  ${BOLD}Versión en repo:${NC}    v${INSTALLER_VERSION}"
    [[ -n "$_INSTALLED_DATE" ]] && echo -e "  ${BOLD}Instalado el:${NC}      $(echo "$_INSTALLED_DATE" | cut -dT -f1)"
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
        warn "No se encontró instalación previa en el marker — usando $SCRIPT_DIR"
        INSTALL_DIR="$SCRIPT_DIR"
    fi

    # Detener servicios ANTES de tocar archivos (solo upgrade/reinstall — update hace hot-reload)
    if [[ "$MODE" != "update" ]]; then
        hdr "Deteniendo servicios"
        for _svc in kaplabilling-backend kaplabilling-frontend kaplabilling-hep; do
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
        command -v rsync &>/dev/null || apt-get install -y rsync -qq
        rsync -a --delete \
            --exclude='.env' \
            --exclude='.env.local' \
            --exclude='venv/' \
            --exclude='node_modules/' \
            --exclude='.next/' \
            --exclude='standalone/' \
            "$SCRIPT_DIR/" "$INSTALL_DIR/"
        ok "Código sincronizado"
        echo ""
    fi
else
    # Fresh: el destino SIEMPRE es /opt/kaplabilling, independientemente de donde
    # se ejecutó el install. Si el origen es distinto, se copia antes de continuar.
    INSTALL_DIR="/opt/kaplabilling"
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
            "$SCRIPT_DIR/" "$INSTALL_DIR/"
        ok "Archivos copiados a $INSTALL_DIR"
        echo ""
    fi
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

    # ── Spinner ligero ─────────────────────────────────────────────────────────
    _uspinner() {
        local label="$1"; shift
        info "${label}..."
        "$@" >>"$LOG_FILE" 2>&1 &
        local _PID=$! _T=0
        while kill -0 $_PID 2>/dev/null; do
            printf "\r  → %s ... %ds" "$label" "$_T"
            sleep 3; _T=$((_T + 3))
        done
        printf "\r%-60s\r" " "
        wait $_PID && ok "${label} (${_T}s)" || { err "${label} falló — ver $LOG_FILE"; exit 1; }
    }

    # ── Python: actualizar dependencias ────────────────────────────────────────
    hdr "Dependencias Python"
    "$INSTALL_DIR/venv/bin/pip" install -q --upgrade pip >>"$LOG_FILE" 2>&1
    "$INSTALL_DIR/venv/bin/pip" install -q -r "$INSTALL_DIR/backend/requirements.txt" >>"$LOG_FILE" 2>&1
    ok "Dependencias actualizadas"

    # ── Migraciones DB ─────────────────────────────────────────────────────────
    hdr "Migraciones DB"
    $_UMC "$_UDB_NAME" < "$INSTALL_DIR/db/schema.sql" >>"$LOG_FILE" 2>&1

    $_UMC "$_UDB_NAME" -e "
    ALTER TABLE firewall_rules
      ADD COLUMN IF NOT EXISTS service ENUM('all','sip','rtp','ssh') NOT NULL DEFAULT 'all'
      AFTER action;
    ALTER TABLE prefixes
      ADD COLUMN IF NOT EXISTS group_name VARCHAR(50) NOT NULL DEFAULT ''
      AFTER destination;
    ALTER TABLE cdrs
      ADD COLUMN IF NOT EXISTS call_state VARCHAR(20) NULL AFTER disposition;
    ALTER TABLE cdrs_failed
      ADD COLUMN IF NOT EXISTS call_state VARCHAR(20) NULL AFTER hangup_cause;
    ALTER TABLE customers MODIFY COLUMN cpslimit SMALLINT UNSIGNED NOT NULL DEFAULT 2;
    ALTER TABLE cdrs
      ADD COLUMN IF NOT EXISTS sip_code SMALLINT UNSIGNED NOT NULL DEFAULT 200 AFTER billsec;
    ALTER TABLE sip_traces
      ADD INDEX IF NOT EXISTS idx_cid_captured (call_id, captured_at);
    CREATE TABLE IF NOT EXISTS customer_profiles (
        id               INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        name             VARCHAR(100)  NOT NULL,
        description      TEXT          NULL,
        show_calls       TINYINT(1)    NOT NULL DEFAULT 1,
        show_quality     TINYINT(1)    NOT NULL DEFAULT 1,
        show_reports     TINYINT(1)    NOT NULL DEFAULT 1,
        show_invoices    TINYINT(1)    NOT NULL DEFAULT 0,
        show_trunk_guide TINYINT(1)    NOT NULL DEFAULT 1,
        created_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    ALTER TABLE customers ADD COLUMN IF NOT EXISTS profile_id      INT UNSIGNED NULL     AFTER rate_plan_id;
    ALTER TABLE customers ADD COLUMN IF NOT EXISTS show_calls       TINYINT(1) NOT NULL DEFAULT 1 AFTER profile_id;
    ALTER TABLE customers ADD COLUMN IF NOT EXISTS show_quality     TINYINT(1) NOT NULL DEFAULT 1 AFTER show_calls;
    ALTER TABLE customers ADD COLUMN IF NOT EXISTS show_reports     TINYINT(1) NOT NULL DEFAULT 1 AFTER show_quality;
    ALTER TABLE customers ADD COLUMN IF NOT EXISTS show_invoices    TINYINT(1) NOT NULL DEFAULT 0 AFTER show_reports;
    ALTER TABLE customers ADD COLUMN IF NOT EXISTS show_trunk_guide TINYINT(1) NOT NULL DEFAULT 1 AFTER show_invoices;
    CREATE TABLE IF NOT EXISTS calls_timeseries (
        id              BIGINT UNSIGNED   AUTO_INCREMENT PRIMARY KEY,
        ts              DATETIME          NOT NULL,
        customer_id     INT UNSIGNED      NOT NULL,
        carrier_id      INT UNSIGNED      NOT NULL,
        call_count      SMALLINT UNSIGNED NOT NULL DEFAULT 0,
        answered_count  SMALLINT UNSIGNED NOT NULL DEFAULT 0,
        failed_count    SMALLINT UNSIGNED NOT NULL DEFAULT 0,
        UNIQUE KEY uq_ts_cust_carr (ts, customer_id, carrier_id),
        INDEX idx_ts (ts)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    CREATE TABLE IF NOT EXISTS traffic_quality_hourly (
        id          BIGINT UNSIGNED   AUTO_INCREMENT PRIMARY KEY,
        ts_hour     DATETIME          NOT NULL,
        customer_id INT UNSIGNED      NOT NULL,
        total       INT UNSIGNED      NOT NULL DEFAULT 0,
        answered    INT UNSIGNED      NOT NULL DEFAULT 0,
        short_calls INT UNSIGNED      NOT NULL DEFAULT 0,
        c_487       INT UNSIGNED      NOT NULL DEFAULT 0,
        c_486       INT UNSIGNED      NOT NULL DEFAULT 0,
        c_404       INT UNSIGNED      NOT NULL DEFAULT 0,
        c_503       INT UNSIGNED      NOT NULL DEFAULT 0,
        c_other     INT UNSIGNED      NOT NULL DEFAULT 0,
        UNIQUE KEY uq_hour_customer (ts_hour, customer_id),
        INDEX idx_ts_hour (ts_hour),
        INDEX idx_customer_hour (customer_id, ts_hour)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    " >>"$LOG_FILE" 2>&1 || true
    ok "Migraciones aplicadas"

    # ── Frontend Next.js ───────────────────────────────────────────────────────
    hdr "Frontend Next.js"
    cd "$INSTALL_DIR/frontend"
    rm -rf node_modules package-lock.json
    _uspinner "Instalando paquetes npm" npm install --include=optional

    # Binding nativo @tailwindcss/oxide (mismo check que el instalador completo)
    _OXIDE_ARCH=""
    case "$(uname -m)" in
        x86_64)  _OXIDE_ARCH="linux-x64-gnu"   ;;
        aarch64) _OXIDE_ARCH="linux-arm64-gnu"  ;;
    esac
    if [[ -n "$_OXIDE_ARCH" && ! -d "node_modules/@tailwindcss/oxide-${_OXIDE_ARCH}" ]]; then
        npm install --no-save "@tailwindcss/oxide-${_OXIDE_ARCH}" >>"$LOG_FILE" 2>&1 \
            && ok "Binding @tailwindcss/oxide-${_OXIDE_ARCH} instalado" \
            || { err "No se pudo instalar @tailwindcss/oxide-${_OXIDE_ARCH}"; exit 1; }
    fi

    _uspinner "Compilando Next.js" npm run build
    cp -r .next/static  .next/standalone/.next/static
    cp -r public        .next/standalone/public 2>/dev/null || true
    cd "$INSTALL_DIR"
    ok "Frontend construido"

    # ── Crontab ────────────────────────────────────────────────────────────────
    hdr "Crontab"
    # Directorio de logs para crons de usuario kaplabilling (LOG_DIR es root-only)
    mkdir -p "$INSTALL_DIR/logs"
    chown kaplabilling:kaplabilling "$INSTALL_DIR/logs"
    chmod 755 "$INSTALL_DIR/logs"
    rm -f /etc/cron.d/sip-platform   # limpiar nombre anterior
    sed \
        -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" \
        -e "s|__LOG_DIR__|$LOG_DIR|g"         \
        "$INSTALL_DIR/cron/kaplabilling" > /etc/cron.d/kaplabilling
    chmod 644 /etc/cron.d/kaplabilling
    ok "Crontab configurado — logs kaplabilling en $INSTALL_DIR/logs/"

    # ── Directorio de datos runtime ────────────────────────────────────────────
    mkdir -p /var/lib/kaplabilling
    # Generar snapshot inicial de dlg.stats_active para que la API live no arranque en blanco
    "$INSTALL_DIR/venv/bin/python3" "$INSTALL_DIR/scripts/cron_dlg_stats.py" 2>/dev/null || true

    # ── Kamailio logging — rsyslog + logrotate ─────────────────────────────────
    mkdir -p /etc/rsyslog.d /etc/logrotate.d
    cat > /etc/rsyslog.d/40-kamailio.conf << 'EOF'
if $syslogfacility-text == 'local0' then /var/log/kamailio.log
& stop
EOF
    touch /var/log/kamailio.log
    chown root:adm /var/log/kamailio.log 2>/dev/null || chown root:root /var/log/kamailio.log
    chmod 640 /var/log/kamailio.log
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
    systemctl enable rsyslog 2>/dev/null || true
    systemctl restart rsyslog \
        && ok "rsyslog instalado: Kamailio → /var/log/kamailio.log (rotate diario, 1 día)" \
        || warn "rsyslog no pudo iniciarse — revisar: journalctl -u rsyslog"

    # ── Permisos scripts ───────────────────────────────────────────────────────
    chown -R kaplabilling:kaplabilling "$INSTALL_DIR"
    chmod +x "$INSTALL_DIR/scripts/"*.py
    # Grupo kamailio: kaplabilling necesita acceder al socket kamcmd para timeseries
    getent group kamailio > /dev/null 2>&1 && usermod -aG kamailio kaplabilling && \
        ok "kaplabilling → grupo kamailio (kamcmd accessible)" || true
    ok "Permisos aplicados"

    # ── Actualizar service files (rename sip- → kaplabilling-) ───────────────
    hdr "Actualizando servicios systemd"
    for svc in kaplabilling-backend kaplabilling-frontend kaplabilling-hep; do
        sed -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" \
            "$INSTALL_DIR/systemd/${svc}.service" \
            > "/etc/systemd/system/${svc}.service"
        ok "/etc/systemd/system/${svc}.service"
    done
    # Limpiar servicios viejos silenciosamente si existen
    for old in sip-backend sip-frontend sip-hep; do
        systemctl stop    "$old" 2>/dev/null || true
        systemctl disable "$old" 2>/dev/null || true
        rm -f "/etc/systemd/system/${old}.service"
    done

    # ── Reiniciar servicios de aplicación (Kamailio NO se toca) ───────────────
    hdr "Reiniciando servicios"
    systemctl daemon-reload
    systemctl enable kaplabilling-backend kaplabilling-frontend kaplabilling-hep 2>/dev/null || true
    for _svc in kaplabilling-backend kaplabilling-frontend kaplabilling-hep; do
        systemctl restart "$_svc" \
            && ok "Reiniciado: $_svc" \
            || warn "$_svc falló — revisar: journalctl -u $_svc -n 20"
    done
    nginx -t >>"$LOG_FILE" 2>&1 && systemctl reload nginx && ok "Nginx recargado"

    # ── Health check ───────────────────────────────────────────────────────────
    sleep 4
    echo ""
    _ALL_OK=true
    for _svc in kaplabilling-backend kaplabilling-frontend kaplabilling-hep; do
        systemctl is-active --quiet "$_svc" \
            && ok "$_svc activo" \
            || { err "$_svc no está corriendo — journalctl -u $_svc -n 20"; _ALL_OK=false; }
    done

    echo ""
    if $_ALL_OK; then
        echo -e "  ${BOLD}${GREEN}✓ Actualización completada — Kamailio no fue tocado${NC}"
    else
        echo -e "  ${BOLD}${YELLOW}⚠ Actualización con advertencias — revisar servicios${NC}"
    fi
    echo -e "  ${BOLD}Log:${NC} $LOG_FILE"
    echo ""
    exit 0
fi

# =============================================================================
# PASO 1-3 — Validaciones y dependencias (delegado a scripts)
# =============================================================================
bash "$INSTALL_DIR/scripts/setup/01_check_os.sh"
bash "$INSTALL_DIR/scripts/setup/02_disable_fw.sh"
bash "$INSTALL_DIR/scripts/setup/03_install_deps.sh"

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
        err "Para instalar desde cero usa: ./install.sh --fresh"
        exit 1
    fi
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

    # Fallbacks para campos no presentes en instalaciones antiguas
    [[ -z "$SSH_PORT"    ]] && { SSH_PORT=$(ss -tlnp 2>/dev/null | grep sshd | awk '{print $4}' | grep -oP '\d+$' | head -1); [[ -z "$SSH_PORT" ]] && SSH_PORT=22; }
    [[ -z "$MGMT_IP"    ]] && MGMT_IP="10.100.254.1"
    [[ -z "$PRIVATE_NET" ]] && PRIVATE_NET="10.0.0.0/8"

    ok "Credenciales cargadas de $LOG_DIR/credentials.conf"
    ok "Dominio: $DOMAIN | Puerto web: $WEB_PORT | DB puerto: $DB_PORT"
    echo ""

    # MC disponible para PASO 7 (schema) sin re-crear la DB
    MC="mysql --user=root --password=$DB_ROOT_PASS --host=127.0.0.1 --port=$DB_PORT"

else
    # ── FRESH / REINSTALL: preguntas interactivas ─────────────────────────────
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

    SSH_PORT=$(ss -tlnp 2>/dev/null | grep sshd | awk '{print $4}' | grep -oP '\d+$' | head -1)
    [[ -z "$SSH_PORT" ]] && SSH_PORT=$(grep -E '^\s*Port\s+[0-9]' /etc/ssh/sshd_config 2>/dev/null | awk '{print $2}' | head -1)
    [[ -z "$SSH_PORT" ]] && SSH_PORT=22

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
    DB_USER="kaplabilling"
    DB_PASS=$(openssl rand -base64 24 | tr -d '/+=' | head -c 28)
    DB_NAME="sip_platform"
    JWT_SECRET=$(openssl rand -hex 32)

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

[platform]
admin_email   = $ADMIN_EMAIL
jwt_secret    = $JWT_SECRET
url           = http://$DOMAIN:$WEB_PORT
EOF
    chmod 600 "$CREDS_FILE"
    ok "Credenciales → $CREDS_FILE"

    cat > "$MARKER_FILE" <<EOF
# KPBTec la plataforma anterior — archivo de configuración del sistema
# Generado por install.sh — no editar manualmente
INSTALL_DIR=$INSTALL_DIR
LOG_DIR=$LOG_DIR
VENV=$INSTALL_DIR/venv
SCRIPTS=$INSTALL_DIR/scripts
INSTALL_DATE=$(date -Iseconds)
VERSION=$INSTALLER_VERSION
EOF
    chmod 644 "$MARKER_FILE"
    ok "Marcador del sistema → $MARKER_FILE (v${INSTALLER_VERSION})"
fi

# Para upgrade: actualizar VERSION en el marker existente
if [[ "$MODE" == "upgrade" && -f "$MARKER_FILE" ]]; then
    sed -i "s/^VERSION=.*/VERSION=${INSTALLER_VERSION}/" "$MARKER_FILE"
    ok "Marcador actualizado → v${INSTALLER_VERSION}"
fi

# =============================================================================
# PASO 6 — MariaDB (solo fresh/reinstall — upgrade reutiliza la existente)
# =============================================================================
if [[ "$MODE" != "upgrade" ]]; then
    hdr "Configurando MariaDB"

    cat > /etc/mysql/mariadb.conf.d/99-kaplabilling.cnf <<EOF
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
GRANT ALL PRIVILEGES ON \`$DB_NAME\`.* TO '$DB_USER'@'127.0.0.1';
GRANT ALL PRIVILEGES ON \`$DB_NAME\`.* TO '$DB_USER'@'localhost';
FLUSH PRIVILEGES;
EOSQL
    ok "MariaDB listo — puerto $DB_PORT | usuario $DB_USER"
fi

# =============================================================================
# PASO 7 — Schema + seed
# =============================================================================
hdr "Cargando base de datos"

$MC "$DB_NAME" < "$INSTALL_DIR/db/schema.sql"

# Upsert de settings que el instalador conoce (funciona en fresh y upgrade)
$MC "$DB_NAME" -e "
INSERT INTO settings (key_name, value, description) VALUES
  ('platform_version', '${INSTALLER_VERSION}', 'Versión instalada de la plataforma anterior'),
  ('ssh_port',         '${SSH_PORT}',           'Puerto SSH del servidor (para reglas firewall)'),
  ('lan_peers',        '',                      'IPs Asterisk/ViciBox LAN (host:puerto, coma-separados) — genera Grupo 1 dispatcher')
ON DUPLICATE KEY UPDATE value = VALUES(value), description = VALUES(description);
" 2>/dev/null || true

# Migraciones de schema para upgrade (columnas nuevas que IF NOT EXISTS no cubre)
if [[ "$MODE" == "upgrade" ]]; then
    $MC "$DB_NAME" -e "
    ALTER TABLE firewall_rules
      ADD COLUMN IF NOT EXISTS service ENUM('all','sip','rtp','ssh') NOT NULL DEFAULT 'all'
      AFTER action;
    " 2>/dev/null || true

    # Agregar columna group_name a prefixes si no existe
    $MC "$DB_NAME" -e "
    ALTER TABLE prefixes
      ADD COLUMN IF NOT EXISTS group_name VARCHAR(50) NOT NULL DEFAULT ''
      AFTER destination;
    " 2>/dev/null || true

    # call_state en cdrs y cdrs_failed (v1.9)
    $MC "$DB_NAME" -e "
    ALTER TABLE cdrs
      ADD COLUMN IF NOT EXISTS call_state VARCHAR(20) NULL AFTER disposition;
    ALTER TABLE cdrs_failed
      ADD COLUMN IF NOT EXISTS call_state VARCHAR(20) NULL AFTER hangup_cause;
    " 2>/dev/null || true

    # cpslimit TINYINT→SMALLINT para soportar valores >255 (v2.1)
    $MC "$DB_NAME" -e "
    ALTER TABLE customers MODIFY COLUMN cpslimit SMALLINT UNSIGNED NOT NULL DEFAULT 2;
    " 2>/dev/null || true

    # sip_code en cdrs para llamadas establecidas (v2.1)
    $MC "$DB_NAME" -e "
    ALTER TABLE cdrs
      ADD COLUMN IF NOT EXISTS sip_code SMALLINT UNSIGNED NOT NULL DEFAULT 200 AFTER billsec;
    " 2>/dev/null || true

    # Módulos del portal cliente — controlables por cliente
    $MC "$DB_NAME" -e "
    ALTER TABLE customers
      ADD COLUMN IF NOT EXISTS show_calls       TINYINT(1) NOT NULL DEFAULT 1,
      ADD COLUMN IF NOT EXISTS show_quality     TINYINT(1) NOT NULL DEFAULT 1,
      ADD COLUMN IF NOT EXISTS show_reports     TINYINT(1) NOT NULL DEFAULT 1,
      ADD COLUMN IF NOT EXISTS show_invoices    TINYINT(1) NOT NULL DEFAULT 0,
      ADD COLUMN IF NOT EXISTS show_trunk_guide TINYINT(1) NOT NULL DEFAULT 1;
    " 2>/dev/null || true

    # Índice compuesto sip_traces (v2.0) — búsqueda call_id + fecha sin full scan
    $MC "$DB_NAME" -e "
    ALTER TABLE sip_traces
      ADD INDEX IF NOT EXISTS idx_cid_captured (call_id, captured_at);
    " 2>/dev/null || true

    # Tabla timeseries por minuto (v1.9)
    $MC "$DB_NAME" -e "
    CREATE TABLE IF NOT EXISTS calls_timeseries (
        id              BIGINT UNSIGNED   AUTO_INCREMENT PRIMARY KEY,
        ts              DATETIME          NOT NULL,
        customer_id     INT UNSIGNED      NOT NULL,
        carrier_id      INT UNSIGNED      NOT NULL,
        call_count      SMALLINT UNSIGNED NOT NULL DEFAULT 0,
        answered_count  SMALLINT UNSIGNED NOT NULL DEFAULT 0,
        failed_count    SMALLINT UNSIGNED NOT NULL DEFAULT 0,
        UNIQUE KEY uq_ts_cust_carr (ts, customer_id, carrier_id),
        INDEX idx_ts (ts)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    " 2>/dev/null || true

    # Tabla ASR Quality por hora (v2.2)
    $MC "$DB_NAME" -e "
    CREATE TABLE IF NOT EXISTS traffic_quality_hourly (
        id          BIGINT UNSIGNED   AUTO_INCREMENT PRIMARY KEY,
        ts_hour     DATETIME          NOT NULL,
        customer_id INT UNSIGNED      NOT NULL,
        total       INT UNSIGNED      NOT NULL DEFAULT 0,
        answered    INT UNSIGNED      NOT NULL DEFAULT 0,
        short_calls INT UNSIGNED      NOT NULL DEFAULT 0,
        c_487       INT UNSIGNED      NOT NULL DEFAULT 0,
        c_486       INT UNSIGNED      NOT NULL DEFAULT 0,
        c_404       INT UNSIGNED      NOT NULL DEFAULT 0,
        c_503       INT UNSIGNED      NOT NULL DEFAULT 0,
        c_other     INT UNSIGNED      NOT NULL DEFAULT 0,
        UNIQUE KEY uq_hour_customer (ts_hour, customer_id),
        INDEX idx_ts_hour (ts_hour),
        INDEX idx_customer_hour (customer_id, ts_hour)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    " 2>/dev/null || true

    # Insertar prefijos Perú completos si no existen e actualizar group_name
    $MC "$DB_NAME" -e "
    INSERT IGNORE INTO prefixes (prefix, destination, group_name, country) VALUES
      ('511',  'Fijo Lima y Callao', 'FIJO LIMA',      'PE'),
      ('5141', 'Fijo Amazonas',      'FIJO PROVINCIA',  'PE'),
      ('5143', 'Fijo Ancash',        'FIJO PROVINCIA',  'PE'),
      ('5183', 'Fijo Apurimac',      'FIJO PROVINCIA',  'PE'),
      ('5154', 'Fijo Arequipa',      'FIJO PROVINCIA',  'PE'),
      ('5166', 'Fijo Ayacucho',      'FIJO PROVINCIA',  'PE'),
      ('5176', 'Fijo Cajamarca',     'FIJO PROVINCIA',  'PE'),
      ('5184', 'Fijo Cusco',         'FIJO PROVINCIA',  'PE'),
      ('5167', 'Fijo Huancavelica',  'FIJO PROVINCIA',  'PE'),
      ('5162', 'Fijo Huanuco',       'FIJO PROVINCIA',  'PE'),
      ('5156', 'Fijo Ica',           'FIJO PROVINCIA',  'PE'),
      ('5164', 'Fijo Junin',         'FIJO PROVINCIA',  'PE'),
      ('5144', 'Fijo La Libertad',   'FIJO PROVINCIA',  'PE'),
      ('5174', 'Fijo Lambayeque',    'FIJO PROVINCIA',  'PE'),
      ('5165', 'Fijo Loreto',        'FIJO PROVINCIA',  'PE'),
      ('5182', 'Fijo Madre de Dios', 'FIJO PROVINCIA',  'PE'),
      ('5153', 'Fijo Moquegua',      'FIJO PROVINCIA',  'PE'),
      ('5163', 'Fijo Pasco',         'FIJO PROVINCIA',  'PE'),
      ('5173', 'Fijo Piura',         'FIJO PROVINCIA',  'PE'),
      ('5151', 'Fijo Puno',          'FIJO PROVINCIA',  'PE'),
      ('5142', 'Fijo San Martin',    'FIJO PROVINCIA',  'PE'),
      ('5152', 'Fijo Tacna',         'FIJO PROVINCIA',  'PE'),
      ('5172', 'Fijo Tumbes',        'FIJO PROVINCIA',  'PE'),
      ('5161', 'Fijo Ucayali',       'FIJO PROVINCIA',  'PE'),
      ('5190', 'Moviles 90X',        'MOVILES',         'PE'),
      ('5191', 'Moviles 91X',        'MOVILES',         'PE'),
      ('5192', 'Moviles 92X',        'MOVILES',         'PE'),
      ('5193', 'Moviles 93X',        'MOVILES',         'PE'),
      ('5194', 'Moviles 94X',        'MOVILES',         'PE'),
      ('5195', 'Moviles 95X',        'MOVILES',         'PE'),
      ('5196', 'Moviles 96X',        'MOVILES',         'PE'),
      ('5197', 'Moviles 97X',        'MOVILES',         'PE'),
      ('5198', 'Moviles 98X',        'MOVILES',         'PE'),
      ('5199', 'Moviles 99X',        'MOVILES',         'PE');
    -- Asignar group_name a prefijos existentes que quedaron en blanco
    UPDATE prefixes SET group_name='FIJO LIMA'      WHERE prefix='511'  AND group_name='';
    UPDATE prefixes SET group_name='FIJO PROVINCIA' WHERE prefix IN ('5141','5143','5183','5154','5166','5176','5184','5167','5162','5156','5164','5144','5174','5165','5182','5153','5163','5173','5151','5142','5152','5172','5161') AND group_name='';
    UPDATE prefixes SET group_name='MOVILES'        WHERE prefix IN ('519','5190','5191','5192','5193','5194','5195','5196','5197','5198','5199') AND group_name='';
    INSERT INTO prefix_lengths (length, count)
      SELECT LENGTH(prefix), COUNT(*) FROM prefixes GROUP BY LENGTH(prefix)
      ON DUPLICATE KEY UPDATE count = VALUES(count);
    " 2>/dev/null || true

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

apply_conf "$INSTALL_DIR/nginx/kaplabilling.conf"  "/etc/nginx/sites-available/kaplabilling.conf"
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

# .env files (generados con Jinja2 porque tienen contraseñas de DB, JWT, etc.)
python3 -c "import jinja2" 2>/dev/null || pip3 install -q jinja2
python3 "$INSTALL_DIR/scripts/gen_configs.py" \
    --public-ip   "$PUBLIC_IP"   --private-ip  "$PRIVATE_IP" \
    --private-net "$PRIVATE_NET" --mgmt-ip     "$MGMT_IP"    \
    --web-port    "$WEB_PORT"    --domain      "$DOMAIN"     \
    --db-host     "127.0.0.1"   --db-port     "$DB_PORT"    \
    --db-name     "$DB_NAME"    --db-user      "$DB_USER"    \
    --db-pass     "$DB_PASS"    --jwt-secret   "$JWT_SECRET" \
    --install-dir "$INSTALL_DIR"

# =============================================================================
# PASO 8b — Performance tuning (aplica en fresh y upgrade)
# =============================================================================
hdr "Performance tuning del sistema"

# ── sysctl: buffers de red, conntrack, file descriptors ──────────────────────
cat > /etc/sysctl.d/99-kaplabilling.conf << 'EOF'
# la plataforma anterior v2.0 — SIP/RTP performance tuning

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

sysctl -p /etc/sysctl.d/99-kaplabilling.conf > /dev/null 2>&1 \
    && ok "sysctl aplicado" \
    || warn "sysctl: algunos parámetros no disponibles en este kernel (normal en VMs)"

# ── Blacklist nf_conntrack_sip — interfiere con RTPEngine ────────────────────
cat > /etc/modprobe.d/kaplabilling-blacklist.conf << 'EOF'
# El helper SIP del kernel parsea y reescribe SDPs — entra en conflicto con RTPEngine
blacklist nf_conntrack_sip
install nf_conntrack_sip /bin/true
EOF
modprobe -r nf_conntrack_sip 2>/dev/null || true
ok "nf_conntrack_sip desactivado"

# ── Systemd override para Kamailio ───────────────────────────────────────────
if systemctl list-units --full -all 2>/dev/null | grep -qE "kamailio(\.service)?"; then
    mkdir -p /etc/systemd/system/kamailio.service.d
    cat > /etc/systemd/system/kamailio.service.d/kaplabilling-limits.conf << EOF
[Service]
LimitNOFILE=65536
LimitMEMLOCK=infinity
LimitCORE=infinity
LimitNPROC=infinity
# Al reiniciar Kamailio pierde todos los diálogos → limpiar active_calls inmediatamente
ExecStartPost=/bin/sh -c 'sleep 3 && $INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/scripts/cleanup_active_calls.py >> $LOG_DIR/cleanup.log 2>&1 || true'
EOF
    ok "Kamailio systemd limits → LimitNOFILE=65536, LimitMEMLOCK=infinity + ExecStartPost cleanup"
fi

# ── Systemd override para RTPEngine ──────────────────────────────────────────
if systemctl list-units --full -all 2>/dev/null | grep -q "rtpengine.service"; then
    mkdir -p /etc/systemd/system/rtpengine.service.d
    cat > /etc/systemd/system/rtpengine.service.d/kaplabilling-limits.conf << 'EOF'
[Service]
LimitNOFILE=65536
LimitMEMLOCK=infinity
LimitCORE=infinity
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_RAW CAP_SYS_NICE
EOF
    ok "RTPEngine systemd limits → LimitNOFILE=65536, LimitMEMLOCK=infinity, CAP_NET_ADMIN/RAW/SYS_NICE"
fi

systemctl daemon-reload 2>/dev/null || true

# ── Kamailio logging — rsyslog LOCAL0 → /var/log/kamailio.log ────────────────
mkdir -p /etc/rsyslog.d /etc/logrotate.d
cat > /etc/rsyslog.d/40-kamailio.conf << 'EOF'
# la plataforma anterior — captura logs de Kamailio (facility LOCAL0)
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

systemctl enable rsyslog 2>/dev/null || true
systemctl restart rsyslog \
    && ok "rsyslog instalado: Kamailio → /var/log/kamailio.log (rotate diario, 1 día)" \
    || warn "rsyslog no pudo iniciarse — revisar: journalctl -u rsyslog"

# ── /etc/default/kamailio — shared memory 256 MB ─────────────────────────────
if [[ -f /etc/default/kamailio ]]; then
    if grep -q "^MEMORY=" /etc/default/kamailio; then
        sed -i 's/^MEMORY=.*/MEMORY=256/' /etc/default/kamailio
    else
        echo "MEMORY=256" >> /etc/default/kamailio
    fi
    ok "/etc/default/kamailio → MEMORY=256 (256 MB shared memory)"
fi

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

    cat > /etc/mysql/mariadb.conf.d/99-kaplabilling-perf.cnf << EOF
# la plataforma anterior v2.0 — MariaDB performance tuning
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
    cat > /etc/udev/rules.d/71-kaplabilling-nic.rules << 'EOF'
# la plataforma anterior v2.0 — ring buffers 4096 en todas las NICs físicas
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
hdr "Frontend Next.js"

cd "$INSTALL_DIR/frontend"

# Función: corre comando en background, spinner en pantalla, output completo al log
# Si falla, muestra las últimas líneas del log para diagnóstico inmediato
_spinner() {
    local label="$1"; shift
    info "${label}..."
    # Output del comando va directo al log (no al terminal) — así se captura TODO sin silenciar
    "$@" >>"$LOG_FILE" 2>&1 &
    local _PID=$! _T=0
    while kill -0 $_PID 2>/dev/null; do
        printf "\r  → %s ... %ds" "$label" "$_T"
        sleep 3
        _T=$((_T + 3))
    done
    printf "\r%-60s\r" " "
    if wait $_PID; then
        ok "${label} (${_T}s)"
    else
        err "${label} falló (${_T}s) — últimas líneas del log:"
        echo ""
        tail -25 "$LOG_FILE"
        echo ""
        exit 1
    fi
}

# Limpiar node_modules previo — evita bug de npm con optional deps (github.com/npm/cli/issues/4828)
rm -rf node_modules package-lock.json
_spinner "Instalando paquetes npm" npm install --include=optional

# Verificar que el binding nativo de @tailwindcss/oxide quedó instalado.
# npm en entorno no-interactivo omite optional deps aunque se pida --include=optional.
# Si falta, instalar el paquete específico de la plataforma actual.
_OXIDE_ARCH=""
case "$(uname -m)" in
    x86_64)  _OXIDE_ARCH="linux-x64-gnu"   ;;
    aarch64) _OXIDE_ARCH="linux-arm64-gnu"  ;;
esac
if [[ -n "$_OXIDE_ARCH" && ! -d "node_modules/@tailwindcss/oxide-${_OXIDE_ARCH}" ]]; then
    info "Binding nativo de @tailwindcss/oxide no instalado — instalando manualmente..."
    npm install --no-save "@tailwindcss/oxide-${_OXIDE_ARCH}" >>"$LOG_FILE" 2>&1 \
        && ok "Binding nativo instalado (@tailwindcss/oxide-${_OXIDE_ARCH})" \
        || { err "No se pudo instalar @tailwindcss/oxide-${_OXIDE_ARCH}"; exit 1; }
fi

_spinner "Compilando frontend Next.js" npm run build

# Next.js standalone no incluye los estáticos — copiarlos manualmente
cp -r .next/static   .next/standalone/.next/static
cp -r public         .next/standalone/public 2>/dev/null || true
cd "$INSTALL_DIR"
ok "Frontend construido"

# =============================================================================
# PASO 11 — Firewall nftables
# =============================================================================
hdr "Firewall"

chmod 600 /etc/nftables.conf
systemctl enable nftables
nft -f /etc/nftables.conf
ok "nftables activo"

# =============================================================================
# PASO 12 — Usuario kaplabilling + permisos + sudoers + servicios systemd
# =============================================================================
hdr "Usuario del sistema y permisos"

# Crear usuario dedicado sin shell (no puede hacer login)
id kaplabilling &>/dev/null || useradd \
    --system \
    --no-create-home \
    --shell /usr/sbin/nologin \
    --comment "KPBTec VoxiKam service account" \
    kaplabilling
ok "Usuario kaplabilling listo"

# Propiedad completa del directorio de instalación
chown -R kaplabilling:kaplabilling "$INSTALL_DIR"
chmod 750 "$INSTALL_DIR"

# www-data necesita traversar el directorio para servir estáticos de Next.js
# nginx corre como www-data — sin esta membresía: Permission denied en /_next/static/
usermod -aG kaplabilling www-data
ok "www-data agregado al grupo kaplabilling (nginx puede leer estáticos)"

# kaplabilling necesita acceder al socket de Kamailio para kamcmd dlg.briefing
# el socket /run/kamailio/kamailio_ctl es del grupo kamailio — sin esto: Permission denied
if getent group kamailio > /dev/null 2>&1; then
    usermod -aG kamailio kaplabilling
    ok "kaplabilling agregado al grupo kamailio (kamcmd accessible)"
fi

# Scripts Python ejecutables por kaplabilling
chmod +x "$INSTALL_DIR/scripts/"*.py
chmod +x "$INSTALL_DIR/scripts/setup/"*.sh

ok "Propiedad de $INSTALL_DIR → kaplabilling (scripts ejecutables)"

# /etc/nftables.d/ — kaplabilling escribe los .nft desde gen_nftables.py
chown root:kaplabilling /etc/nftables.d
chmod 775 /etc/nftables.d
chown kaplabilling:kaplabilling /etc/nftables.d/*.nft 2>/dev/null || true
ok "Permisos /etc/nftables.d → kaplabilling puede escribir"

# /etc/kamailio/ — dispatcher.list + kamailio.cfg
if [[ -d /etc/kamailio ]]; then
    # dispatcher.list — escrito por gen_dispatcher.py
    touch /etc/kamailio/dispatcher.list 2>/dev/null || true
    chown kaplabilling:kaplabilling /etc/kamailio/dispatcher.list 2>/dev/null || true
    ok "Permisos /etc/kamailio/dispatcher.list → kaplabilling"

    # kaplabilling-routes.cfg — generado por gen_dispatcher.py, debe existir
    # antes de que kamailio arranque (lo usa #!include_file en kamailio.cfg)
    if [[ ! -f /etc/kamailio/kaplabilling-routes.cfg ]]; then
        echo "# AUTO-GENERADO por gen_dispatcher.py — vacío hasta primer sync" \
            > /etc/kamailio/kaplabilling-routes.cfg
        chown kaplabilling:kaplabilling /etc/kamailio/kaplabilling-routes.cfg 2>/dev/null || true
        ok "kaplabilling-routes.cfg creado (vacío inicial)"
    fi

    # kamailio.cfg — siempre se regenera desde template (fresh y upgrade)
    # El template es la fuente de verdad; los datos variables van en .env / DB
    sed \
        -e "s|{{ private_ip }}|${PRIVATE_IP}|g" \
        -e "s|{{ public_ip }}|${PUBLIC_IP}|g"   \
        -e "s|{{ db_user }}|${DB_USER}|g"        \
        -e "s|{{ db_pass }}|${DB_PASS}|g"        \
        -e "s|{{ db_port }}|${DB_PORT}|g"        \
        -e "s|{{ db_name }}|${DB_NAME}|g"        \
        "$INSTALL_DIR/templates/kamailio.cfg.j2" \
        > /etc/kamailio/kamailio.cfg
    ok "kamailio.cfg actualizado desde template"
else
    warn "/etc/kamailio no existe — instalar Kamailio y luego ejecutar: sudo ./install.sh --upgrade"
fi

# sudoers: kaplabilling puede ejecutar SOLO nft y kamcmd como root (sin password)
cp "$INSTALL_DIR/sudoers/kaplabilling" /etc/sudoers.d/kaplabilling
chmod 440 /etc/sudoers.d/kaplabilling
# Validar que el archivo no rompe sudo
visudo -c -f /etc/sudoers.d/kaplabilling && ok "Sudoers configurado — kaplabilling puede: nft, kamcmd" \
    || { err "Error en sudoers — revisar $INSTALL_DIR/sudoers/kaplabilling"; exit 1; }

hdr "Servicios systemd"

# Limpiar servicios viejos (sip-*) silenciosamente si vienen de v1
for old in sip-backend sip-frontend sip-hep; do
    systemctl stop    "$old" 2>/dev/null || true
    systemctl disable "$old" 2>/dev/null || true
    rm -f "/etc/systemd/system/${old}.service"
done

# Aplicar INSTALL_DIR a los service files (reemplazo de __INSTALL_DIR__)
for svc in kaplabilling-backend kaplabilling-frontend kaplabilling-hep; do
    sed "s|__INSTALL_DIR__|$INSTALL_DIR|g" \
        "$INSTALL_DIR/systemd/${svc}.service" \
        > "/etc/systemd/system/${svc}.service"
    ok "/etc/systemd/system/${svc}.service"
done

systemctl daemon-reload
systemctl enable --now kaplabilling-backend kaplabilling-frontend kaplabilling-hep
ok "kaplabilling-backend, kaplabilling-frontend y kaplabilling-hep habilitados"

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

# Limpiar nombre anterior si existe
rm -f /etc/nginx/sites-enabled/sip-platform.conf /etc/nginx/sites-available/sip-platform.conf
ln -sf /etc/nginx/sites-available/kaplabilling.conf /etc/nginx/sites-enabled/kaplabilling.conf
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
ok "Nginx en puerto $WEB_PORT"

# =============================================================================
# PASO 14 — Crontab
# =============================================================================
hdr "Tareas programadas"

mkdir -p "$INSTALL_DIR/logs"
chown kaplabilling:kaplabilling "$INSTALL_DIR/logs"
chmod 755 "$INSTALL_DIR/logs"
rm -f /etc/cron.d/sip-platform
sed \
    -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" \
    -e "s|__LOG_DIR__|$LOG_DIR|g"         \
    "$INSTALL_DIR/cron/kaplabilling" > /etc/cron.d/kaplabilling
chmod 644 /etc/cron.d/kaplabilling
ok "Crontab configurado — logs kaplabilling en $INSTALL_DIR/logs/"

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
chk_svc kaplabilling-backend
chk_svc kaplabilling-frontend
chk_svc kaplabilling-hep
chk_http "FastAPI"  8000      "/api/health"
chk_http "Next.js"  3000      "/"
chk_http "Nginx"    "$WEB_PORT" "/health"

# =============================================================================
# RESUMEN
# =============================================================================
echo ""
if [[ "$ALL_OK" == false ]]; then
    echo -e "${BOLD}${YELLOW}"
    if [[ "$MODE" == "upgrade" ]]; then
        echo "  ╔══════════════════════════════════════════════════╗"
        echo "  ║      Upgrade completado con advertencias ⚠      ║"
        echo "  ╠══════════════════════════════════════════════════╣"
        printf "  ║  URL:    http://%-33s║\n" "$DOMAIN:$WEB_PORT"
        printf "  ║  Admin:  %-39s║\n" "$ADMIN_EMAIL"
        printf "  ║  Log:    %-39s║\n" "$LOG_FILE"
        echo "  ║  Datos y credenciales: conservados              ║"
    else
        echo "  ╔══════════════════════════════════════════════════╗"
        echo "  ║      Instalación con errores — revisar ✗        ║"
        echo "  ╠══════════════════════════════════════════════════╣"
        printf "  ║  URL:    http://%-33s║\n" "$DOMAIN:$WEB_PORT"
        printf "  ║  Admin:  %-39s║\n" "$ADMIN_EMAIL"
        printf "  ║  Creds:  %-39s║\n" "$CREDS_FILE"
        printf "  ║  Log:    %-39s║\n" "$LOG_FILE"
    fi
    echo "  ╠══════════════════════════════════════════════════╣"
    echo "  ║  Diagnóstico:                                    ║"
    echo "  ║  journalctl -u kaplabilling-backend -n 30 --no-pager     ║"
    echo "  ║  journalctl -u kaplabilling-frontend -n 30 --no-pager    ║"
    echo "  ║  journalctl -u kaplabilling-hep -n 30 --no-pager         ║"
    echo "  ╚══════════════════════════════════════════════════╝"
    echo -e "${NC}"
else
    echo -e "${BOLD}${GREEN}"
    if [[ "$MODE" == "upgrade" ]]; then
        echo "  ╔══════════════════════════════════════════════════╗"
        echo "  ║          Upgrade completado ✓                   ║"
        echo "  ╠══════════════════════════════════════════════════╣"
        printf "  ║  URL:    http://%-33s║\n" "$DOMAIN:$WEB_PORT"
        printf "  ║  Admin:  %-39s║\n" "$ADMIN_EMAIL"
        printf "  ║  Log:    %-39s║\n" "$LOG_FILE"
        echo "  ║  Datos y credenciales: conservados              ║"
    else
        echo "  ╔══════════════════════════════════════════════════╗"
        echo "  ║          Instalación completada ✓               ║"
        echo "  ╠══════════════════════════════════════════════════╣"
        printf "  ║  URL:    http://%-33s║\n" "$DOMAIN:$WEB_PORT"
        printf "  ║  Admin:  %-39s║\n" "$ADMIN_EMAIL"
        printf "  ║  Creds:  %-39s║\n" "$CREDS_FILE"
        printf "  ║  Log:    %-39s║\n" "$LOG_FILE"
    fi
    echo "  ╚══════════════════════════════════════════════════╝"
    echo -e "${NC}"
fi
