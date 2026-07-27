#!/bin/bash
# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

# Instala ClickHouse server + client desde el repo oficial. Si ya está
# instalado, solo verifica versión y omite la instalación — mismo patrón que
# 04_install_sip_stack.sh. A diferencia de MariaDB (que viene en los repos
# default de Debian), ClickHouse necesita su propio repo apt + GPG key.
#
# Solo instala el motor y lo deja corriendo — la creación de la base
# sip_platform, el usuario voxikam y el schema (db/clickhouse_schema.sql)
# se hacen en deploy.sh, mismo criterio que MariaDB (este script es análogo
# a "apt-get install mariadb-server", no al CREATE DATABASE/CREATE USER que
# viene después en el flujo principal).

source "$(dirname "$0")/../_colors.sh"

hdr "ClickHouse — sip_traces"

DISTRO_CODENAME=$(. /etc/os-release && echo "$VERSION_CODENAME")
[[ -z "$DISTRO_CODENAME" ]] && DISTRO_CODENAME="bookworm"

if command -v clickhouse-server &>/dev/null; then
    CH_VER=$(clickhouse-server --version 2>&1 | grep -oP 'version \K[0-9.]+' | head -1)
    ok "ClickHouse $CH_VER ya instalado — omitiendo"
    exit 0
fi

echo ""
warn "ClickHouse no instalado"
echo ""
read -r -p "  ¿Instalar ClickHouse server + client ahora (repo oficial packages.clickhouse.com)? [S/n]: " _C
[[ "${_C:-S}" =~ ^[Ss]$ ]] || { err "Instala ClickHouse manualmente y vuelve a ejecutar."; exit 1; }
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Repo oficial ClickHouse (no está en Debian por defecto)
# ─────────────────────────────────────────────────────────────────────────────
curl -fsSL 'https://packages.clickhouse.com/rpm/lts/repodata/repomd.xml.key' \
    | gpg --dearmor -o /usr/share/keyrings/clickhouse-keyring.gpg \
    && ok "GPG key packages.clickhouse.com instalada" \
    || { err "No se pudo obtener la GPG key de packages.clickhouse.com"; exit 1; }

echo "deb [signed-by=/usr/share/keyrings/clickhouse-keyring.gpg] https://packages.clickhouse.com/deb stable main" \
    > /etc/apt/sources.list.d/clickhouse.list
ok "Repo ClickHouse stable agregado"

apt-get update -qq
apt-get install -y clickhouse-server clickhouse-client

systemctl enable --now clickhouse-server

# systemd marca el servicio "activo" en cuanto el proceso arranca, pero
# ClickHouse tarda unos segundos más en terminar de inicializar y abrir sus
# puertos — un solo `sleep 2` + `is-active` no alcanza. Se espera activamente
# a que responda de verdad, no solo a que el proceso esté vivo. Puerto 9000
# explícito: es el protocolo NATIVO que habla clickhouse-client (no 8123,
# que es la interfaz HTTP que usa clickhouse-connect desde Python).
info "Esperando a que ClickHouse responda (puerto nativo 9000)..."
_CH_READY=false
for _i in $(seq 1 30); do
    if clickhouse-client --host 127.0.0.1 --port 9000 --query "SELECT 1" &>/dev/null; then
        _CH_READY=true
        break
    fi
    sleep 1
done

if ! $_CH_READY; then
    err "clickhouse-server no respondió tras 30s — revisar: journalctl -u clickhouse-server -n 30"
    exit 1
fi

CH_VER=$(clickhouse-server --version 2>&1 | grep -oP 'version \K[0-9.]+' | head -1)
ok "ClickHouse $CH_VER instalado y corriendo"
