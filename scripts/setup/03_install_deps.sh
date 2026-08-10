#!/bin/bash
# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

# Instala dependencias del sistema preguntando antes si hay faltantes

source "$(dirname "$0")/../_colors.sh"

hdr "Verificando dependencias del sistema"

MISSING=(); PKGS=()

chk() { command -v "$1" &>/dev/null && ok "$1" || { warn "$1 faltante"; MISSING+=("$1"); PKGS+=("$2"); }; }

chk python3      "python3 python3-pip python3-jinja2"
chk node         "nodejs"
chk npm          "npm"
chk nginx        "nginx"
chk nft          "nftables"
chk curl         "curl"
chk openssl      "openssl"
chk rsync        "rsync"
chk rsyslogd     "rsyslog"
# envsubst (gettext-base) — usado por deploy.sh para renderizar db/setup/*.sql
# (contienen contraseñas reales: sed rompía o corrompía la sustitución si el
# valor tenía '/', '&' o '\', envsubst sustituye el valor literal sin
# interpretarlo como patrón).
chk envsubst     "gettext-base"

dpkg -l mariadb-server 2>/dev/null | grep -q "^ii" || { MISSING+=("mariadb-server"); PKGS+=("mariadb-server mariadb-client"); }

# Dependencias del sistema para weasyprint (generación de PDFs de facturas)
for _pkg in libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf2.0-0; do
    dpkg -l "$_pkg" 2>/dev/null | grep -q "^ii" \
        || { warn "$_pkg faltante (requerido por weasyprint/PDF)"; MISSING+=("$_pkg"); PKGS+=("$_pkg"); }
done
dpkg -l python3-venv   2>/dev/null | grep -q "^ii" || { warn "python3-venv faltante"; MISSING+=("python3-venv"); PKGS+=("python3-venv"); }
python3 -c "import jinja2" 2>/dev/null || PKGS+=("python3-jinja2")

# Módulos Kamailio extra (db_mysql, sqlops, dialog, siptrace)
# kamailio-mysql-modules → db_mysql.so  (CDR a DB)
# kamailio-extra-modules → sqlops.so    (INSERT/UPDATE desde script)
# kamailio-utils-modules → siptrace.so  (HEP3 → mini-Homer)
# dialog.so suele venir en el paquete base kamailio, pero en algunas distros
# está en kamailio-extra-modules — se instala igualmente sin daño.
for _kpkg in kamailio-mysql-modules kamailio-extra-modules kamailio-utils-modules; do
    dpkg -l "$_kpkg" 2>/dev/null | grep -q "^ii" \
        || { warn "$_kpkg faltante"; MISSING+=("$_kpkg"); PKGS+=("$_kpkg"); }
done

# Node.js mínimo v22 — debe chequearse ANTES del exit 0 para no saltarse la actualización
NODE_V=$(node --version 2>/dev/null | sed 's/v//' | cut -d. -f1 || echo 0)
[[ "$NODE_V" -lt 22 ]] && { warn "Node.js v${NODE_V} < 22 requerido"; MISSING+=("nodejs>=22"); }

[[ ${#MISSING[@]} -eq 0 ]] && { ok "Todas las dependencias presentes"; exit 0; }

echo ""
warn "Faltan: ${MISSING[*]}"
read -r -p "  ¿Instalar ahora? [S/n]: " C
[[ "${C:-S}" =~ ^[Ss]$ ]] || { err "Instala los paquetes manualmente y vuelve a ejecutar."; exit 1; }

apt-get update -qq
PKGS_UNIQ=$(echo "${PKGS[@]}" | tr ' ' '\n' | sort -u | grep -v '^nodejs>=22$' | tr '\n' ' ')
[[ -n "$PKGS_UNIQ" ]] && apt-get install -y $PKGS_UNIQ

# Instalar/actualizar Node.js a v22 LTS si la versión es insuficiente
[[ "$NODE_V" -lt 22 ]] && {
    info "Instalando Node.js 22 LTS vía nodesource..."
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
    apt-get install -y nodejs
}

ok "Dependencias instaladas — Python $(python3 --version | awk '{print $2}') | Node.js $(node --version)"
