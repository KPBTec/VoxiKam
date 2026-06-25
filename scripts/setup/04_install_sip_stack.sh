#!/bin/bash
# la plataforma anterior — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

# Instala Kamailio 5.7.x + RTPEngine 10.x desde repos oficiales.
# Si ya están instalados, solo verifica versiones y omite la instalación.

source "$(dirname "$0")/../_colors.sh"

hdr "Stack SIP — Kamailio + RTPEngine"

# ── Detectar codename Debian ──────────────────────────────────────────────────
DISTRO_CODENAME=$(. /etc/os-release && echo "$VERSION_CODENAME")
[[ -z "$DISTRO_CODENAME" ]] && DISTRO_CODENAME="bookworm"

# ── Verificar Kamailio ────────────────────────────────────────────────────────
INSTALL_KAMAILIO=true
if command -v kamailio &>/dev/null; then
    KAM_VER=$(kamailio -v 2>&1 | grep -oP 'kamailio \K[0-9.]+' | head -1)
    ok "Kamailio $KAM_VER ya instalado — omitiendo"
    INSTALL_KAMAILIO=false
fi

# ── Verificar RTPEngine ───────────────────────────────────────────────────────
INSTALL_RTPENGINE=true
if command -v rtpengine &>/dev/null; then
    RTP_VER=$(rtpengine --version 2>&1 | grep -oP 'Version: \K[0-9.]+' | head -1)
    ok "RTPEngine $RTP_VER ya instalado — omitiendo"
    INSTALL_RTPENGINE=false
fi

$INSTALL_KAMAILIO || $INSTALL_RTPENGINE || { ok "Stack SIP completo — sin cambios"; exit 0; }

# ── Confirmar instalación ─────────────────────────────────────────────────────
echo ""
$INSTALL_KAMAILIO  && warn "Kamailio no instalado"
$INSTALL_RTPENGINE && warn "RTPEngine no instalado"
echo ""
read -r -p "  ¿Instalar stack SIP ahora (Kamailio 5.7 + RTPEngine 10.x)? [S/n]: " _C
[[ "${_C:-S}" =~ ^[Ss]$ ]] || { err "Instala Kamailio y RTPEngine manualmente y vuelve a ejecutar."; exit 1; }
echo ""

apt-get update -qq

# ─────────────────────────────────────────────────────────────────────────────
# KAMAILIO 5.7.x — repo oficial kamailio.org
# ─────────────────────────────────────────────────────────────────────────────
if $INSTALL_KAMAILIO; then
    hdr "Instalando Kamailio 5.7"

    # GPG key
    curl -fsSL https://deb.kamailio.org/kamailiodebkey.gpg \
        | gpg --dearmor -o /usr/share/keyrings/kamailio-archive-keyring.gpg \
        && ok "GPG key kamailio.org instalada" \
        || { err "No se pudo obtener la GPG key de kamailio.org"; exit 1; }

    echo "deb [signed-by=/usr/share/keyrings/kamailio-archive-keyring.gpg] \
http://deb.kamailio.org/kamailio57 ${DISTRO_CODENAME} main" \
        > /etc/apt/sources.list.d/kamailio.list
    ok "Repo kamailio57 agregado (${DISTRO_CODENAME})"

    apt-get update -qq
    apt-get install -y \
        kamailio \
        kamailio-mysql-modules \
        kamailio-extra-modules \
        kamailio-utils-modules \
        kamailio-tls-modules

    KAM_VER=$(kamailio -v 2>&1 | grep -oP 'kamailio \K[0-9.]+' | head -1)
    ok "Kamailio $KAM_VER instalado"
fi

# ─────────────────────────────────────────────────────────────────────────────
# RTPENGINE 10.x — repo Sipwise
# ─────────────────────────────────────────────────────────────────────────────
if $INSTALL_RTPENGINE; then
    hdr "Instalando RTPEngine 10.x"

    # GPG key Sipwise
    curl -fsSL https://deb.sipwise.com/spce/Release.key \
        | gpg --dearmor -o /usr/share/keyrings/sipwise-archive-keyring.gpg \
        && ok "GPG key Sipwise instalada" \
        || { err "No se pudo obtener la GPG key de deb.sipwise.com"; exit 1; }

    echo "deb [signed-by=/usr/share/keyrings/sipwise-archive-keyring.gpg] \
https://deb.sipwise.com/spce/mr10.5/ ${DISTRO_CODENAME} main" \
        > /etc/apt/sources.list.d/sipwise-rtpengine.list
    ok "Repo Sipwise mr10.5 agregado (${DISTRO_CODENAME})"

    apt-get update -qq
    apt-get install -y ngcp-rtpengine-daemon

    RTP_VER=$(rtpengine --version 2>&1 | grep -oP 'Version: \K[0-9.]+' | head -1)
    ok "RTPEngine $RTP_VER instalado"

    # Habilitar servicio (no arrancar aún — la config se aplica en el paso siguiente)
    systemctl enable rtpengine 2>/dev/null || true
    ok "rtpengine.service habilitado (arrancará con la config de la plataforma anterior)"
fi

ok "Stack SIP listo"
