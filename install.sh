#!/bin/bash
# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.
#
# Punto de entrada público — este es el ÚNICO archivo que se descarga suelto
# (wget/curl) antes de tener el repo clonado. Su único trabajo es clonar
# VoxiKam en una carpeta temporal y delegarle todo a deploy.sh — nunca
# duplicar acá ninguna lógica de instalación real, eso vive en deploy.sh.
#
# Uso:
#   wget https://raw.githubusercontent.com/KPBTec/VoxiKam/main/install.sh
#   sudo bash install.sh              # instalación nueva (menú interactivo)
#   sudo bash install.sh --update     # o cualquier flag de deploy.sh, se reenvía tal cual
set -e

if [[ $EUID -ne 0 ]]; then
    echo "Este instalador necesita privilegios de root — corré: sudo bash install.sh"
    exit 1
fi

# git no está en la lista de dependencias que chequea deploy.sh (scripts/setup/
# 03_install_deps.sh) porque hasta este punto todavía no existe ni el repo ni
# ese script — se resuelve acá, antes de poder clonar nada.
if ! command -v git &>/dev/null; then
    echo "Instalando git..."
    apt-get update -qq
    apt-get install -y -qq git
fi

TMPDIR="/tmp/voxikam-install-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$TMPDIR"
cd "$TMPDIR"

echo "Clonando VoxiKam en $TMPDIR/VoxiKam..."
git clone --depth=1 https://github.com/KPBTec/VoxiKam.git

cd VoxiKam
exec ./deploy.sh "$@"
