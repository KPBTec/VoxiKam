#!/bin/bash
# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.
#
# Backup diario de MariaDB (facturas, saldos, clientes — los datos que
# importan de verdad) + best-effort de ClickHouse (sip_traces). Antes de
# esto, deploy.sh no tenía NINGÚN backup real: solo dejaba la instalación
# vieja intacta como red de rollback de un upgrade fallido, que no protege
# contra perder datos por disco roto, borrado accidental, etc.
#
# Se guarda fuera de $INSTALL_DIR a propósito — un `rsync --delete` de deploy
# o un `rm -rf` accidental del directorio de instalación no debe poder
# llevarse puestos los backups.
#
# Uso: correr como root (cron lo hace así, ver cron/voxikam).
#   ./scripts/backup_db.sh            # respeta el toggle settings.backup_enabled
#   ./scripts/backup_db.sh --force    # ignora el toggle (botón "Ejecutar ahora" del panel)
#
# Restaurar MariaDB:
#   gunzip -c /var/backups/voxikam/mariadb/mariadb_YYYYMMDD-HHMMSS.sql.gz \
#     | mysql -u root -p"$ROOT_PASS" -P "$DB_PORT" -h 127.0.0.1 "$DB_NAME"
#
# Restaurar ClickHouse (si el backup nativo se pudo generar):
#   clickhouse-client --query "RESTORE DATABASE sip_platform FROM Disk('backups', 'backup_YYYYMMDD-HHMMSS')"

set -uo pipefail   # sin -e: un fallo parcial (ej. ClickHouse) no debe abortar el backup de MariaDB
source "$(dirname "$0")/_colors.sh"

[[ $EUID -eq 0 ]] || { echo "Correr como root."; exit 1; }

LOG_DIR="/voxikam-install/logs-configs"
CRED_FILE="$LOG_DIR/credentials.conf"
BACKUP_ROOT="/var/backups/voxikam"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
TS="$(date +%Y%m%d-%H%M%S)"

[[ -f "$CRED_FILE" ]] || { echo "No se encontró $CRED_FILE"; exit 1; }
_cred() { (grep -m1 "^\s*$1\s*=" "$CRED_FILE" 2>/dev/null || true) | awk -F'= ' '{print $2}' | tr -d '[:space:]'; }

DB_PORT=$(_cred "port")
DB_NAME=$(_cred "database")
ROOT_PASS=$(_cred "root_password")
_MC="mysql -N -u root -p${ROOT_PASS} -P ${DB_PORT} -h 127.0.0.1 ${DB_NAME}"

# Toggle desde Sistema → Infraestructura (settings.backup_enabled) — sin fila
# = activado (opt-out, no opt-in: un backup que falta por defecto es peor
# que uno de más). --force lo ignora (botón "Ejecutar ahora" del panel).
if [[ "${1:-}" != "--force" ]]; then
    _ENABLED=$($_MC -e "SELECT value FROM settings WHERE key_name='backup_enabled'" 2>/dev/null || echo "")
    if [[ "$_ENABLED" == "0" ]]; then
        echo "Backup desactivado desde el panel (Sistema → Infraestructura) — se salta esta corrida."
        exit 0
    fi
fi

mkdir -p "$BACKUP_ROOT/mariadb" "$BACKUP_ROOT/clickhouse"
chmod 700 "$BACKUP_ROOT"

# ── MariaDB — lo que realmente importa (facturas, saldos, clientes) ────────
hdr "Backup MariaDB ($DB_NAME)"
_DUMP="$BACKUP_ROOT/mariadb/mariadb_${TS}.sql.gz"
_MARIADB_OK=0
_MARIADB_BYTES=0
if mysqldump --single-transaction --routines --triggers --events \
        -u root -p"$ROOT_PASS" -P "$DB_PORT" -h 127.0.0.1 "$DB_NAME" \
        2>"$BACKUP_ROOT/mariadb/.last_error.log" | gzip > "$_DUMP"; then
    _SIZE=$(du -h "$_DUMP" | cut -f1)
    _MARIADB_BYTES=$(stat -c%s "$_DUMP" 2>/dev/null || echo 0)
    _MARIADB_OK=1
    ok "MariaDB → $_DUMP ($_SIZE)"
    rm -f "$BACKUP_ROOT/mariadb/.last_error.log"
else
    err "mysqldump falló — ver $BACKUP_ROOT/mariadb/.last_error.log"
    rm -f "$_DUMP"
fi

# ── ClickHouse — best-effort, no bloquea el backup de MariaDB si falla ─────
hdr "Backup ClickHouse (sip_platform)"
_CH_PASS=$(_cred "ch_password" 2>/dev/null || true)
_CH_OK=0
if command -v clickhouse-client &>/dev/null && [[ -n "$_CH_PASS" ]]; then
    _CH_NATIVE_PORT=$(_cred "ch_native_port")
    if clickhouse-client --host 127.0.0.1 --port "${_CH_NATIVE_PORT:-9000}" \
            --user voxikam --password "$_CH_PASS" \
            --query "BACKUP DATABASE sip_platform TO Disk('default', '${BACKUP_ROOT}/clickhouse/backup_${TS}')" \
            2>"$BACKUP_ROOT/clickhouse/.last_error.log"; then
        ok "ClickHouse → ${BACKUP_ROOT}/clickhouse/backup_${TS}"
        rm -f "$BACKUP_ROOT/clickhouse/.last_error.log"
        _CH_OK=1
    else
        warn "Backup nativo de ClickHouse falló (ver ${BACKUP_ROOT}/clickhouse/.last_error.log) — sip_traces son datos de diagnóstico, no facturación, no es bloqueante"
    fi
else
    warn "ClickHouse no aprovisionado todavía en este install — se salta"
fi

# ── Retención local ─────────────────────────────────────────────────────────
find "$BACKUP_ROOT/mariadb"    -name "mariadb_*.sql.gz" -mtime "+${RETENTION_DAYS}" -delete
find "$BACKUP_ROOT/clickhouse" -maxdepth 1 -name "backup_*" -mtime "+${RETENTION_DAYS}" -exec rm -rf {} + 2>/dev/null || true
info "Retención local: ${RETENTION_DAYS} días"

# ── Copia fuera del server (opcional) ───────────────────────────────────────
# Si en credentials.conf existe [backup] remote_dest = user@host:/ruta o un
# remote rclone, se sincroniza acá. Sin esto, un backup que vive solo en el
# mismo disco que la DB no protege contra que el disco entero se rompa.
_REMOTE_DEST=$(_cred "remote_dest" 2>/dev/null || true)
_REMOTE_OK=0
if [[ -n "$_REMOTE_DEST" ]]; then
    if command -v rsync &>/dev/null; then
        if rsync -az "$BACKUP_ROOT/" "$_REMOTE_DEST/"; then
            ok "Sincronizado fuera del server → $_REMOTE_DEST"
            _REMOTE_OK=1
        else
            warn "rsync a $_REMOTE_DEST falló — el backup local igual quedó guardado"
        fi
    fi
else
    warn "Sin destino remoto configurado ([backup] remote_dest en credentials.conf) — el backup solo vive en este disco. Si el disco se rompe, se pierde también el backup."
fi

# ── Estado — leído por GET /admin/system/infra (Sistema → Infraestructura) ─
mkdir -p /var/lib/voxikam
cat > /var/lib/voxikam/backup_last_run.json <<EOF
{
  "timestamp": "$(date -Iseconds)",
  "mariadb_ok": $([ "$_MARIADB_OK" = "1" ] && echo true || echo false),
  "mariadb_bytes": ${_MARIADB_BYTES},
  "mariadb_file": "$(basename "$_DUMP")",
  "clickhouse_ok": $([ "$_CH_OK" = "1" ] && echo true || echo false),
  "remote_synced": $([ "$_REMOTE_OK" = "1" ] && echo true || echo false)
}
EOF
