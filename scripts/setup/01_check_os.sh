#!/bin/bash
# la plataforma anterior — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2025 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2025 – Todos los derechos reservados.

# Valida que el sistema sea Debian 12+ antes de continuar

source "$(dirname "$0")/../_colors.sh"

hdr "Validando sistema operativo"

OS_ID=""; OS_VER=0
[[ -f /etc/os-release ]] && {
    OS_ID=$(grep ^ID=      /etc/os-release | cut -d= -f2 | tr -d '"')
    OS_VER=$(grep ^VERSION_ID= /etc/os-release | cut -d= -f2 | tr -d '"' | cut -d. -f1)
}

[[ "$OS_ID" != "debian" ]] && {
    err "SO no soportado: '$OS_ID'. Solo Debian 12+ es compatible."
    exit 1
}

[[ "$OS_VER" -lt 12 ]] && {
    err "Debian $OS_VER no soportado. Mínimo: Debian 12 (Bookworm)."
    exit 1
}

[[ "$OS_VER" -eq 13 ]] && {
    warn "Debian 13 (Trixie / testing) detectado — puede haber incompatibilidades."
    read -r -p "  ¿Continuar de todas formas? [s/N]: " C
    [[ "$C" =~ ^[sS]$ ]] || { err "Cancelado."; exit 1; }
}

ok "Debian $OS_VER — compatible"
