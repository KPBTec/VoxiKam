#!/bin/bash
# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.
#
# Habilita HTTPS (Let's Encrypt) sobre el dominio ya configurado.
#
# Uso: sudo ./scripts/setup_tls.sh            # activar
#      sudo ./scripts/setup_tls.sh --disable  # revertir a HTTP plano
#
# Qué hace:
#   1. Instala certbot + el plugin de nginx (si falta).
#   2. Corre `certbot --nginx` contra el dominio de credentials.conf — certbot
#      valida el dominio vía HTTP-01 (necesita el puerto 80 alcanzable desde
#      internet, ya abierto por nftables) y edita el vhost de nginx en vivo
#      para agregar el bloque HTTPS + redirect automático.
#   3. Deja un marcador (TLS_ENABLED=1) en /etc/voxikam.conf.
#   4. Agrega un deploy-hook para que la renovación automática (certbot.timer,
#      instalado por el paquete de Debian) recargue nginx después de renovar.
#
# Por qué es un script aparte y no un paso más de deploy.sh:
#   No es seguro correrlo sin supervisión — necesita que el dominio ya
#   resuelva de verdad a este server y que el puerto 80 esté abierto desde
#   afuera. Se corre una vez, a mano, cuando estés listo.
#
# IMPORTANTE — a partir de acá, deploy.sh deja de sobrescribir el vhost de
# nginx en cada --update/--upgrade (ver el chequeo de TLS_ENABLED en
# deploy.sh, sección "Aplicando archivos de configuración"). Motivo: certbot
# edita el archivo real en /etc/nginx/sites-available/voxikam.conf para
# agregar el bloque HTTPS — si deploy.sh lo pisara con la plantilla del repo
# (HTTP puro) en el próximo deploy, deshace la config de TLS. Un cambio nuevo
# en nginx/voxikam.conf del repo (un location nuevo, un header nuevo) ya NO
# se aplica solo una vez que TLS está activo — hay que fusionarlo a mano en
# el server, o pedir que se automatice ese merge en una vuelta futura.

set -euo pipefail
source "$(dirname "$0")/_colors.sh"

[[ $EUID -eq 0 ]] || { echo "Correr como root (sudo ./scripts/setup_tls.sh)"; exit 1; }

MARKER_FILE="/etc/voxikam.conf"
LOG_DIR="/voxikam-install/logs-configs"
CRED_FILE="$LOG_DIR/credentials.conf"

[[ -f "$CRED_FILE" ]] || { echo "No se encontró $CRED_FILE — ¿corriste deploy.sh al menos una vez?"; exit 1; }

_cred() { (grep -m1 "^\s*$1\s*=" "$CRED_FILE" 2>/dev/null || true) | awk -F'= ' '{print $2}' | tr -d '[:space:]'; }

DOMAIN=$(_cred "domain")
ADMIN_EMAIL=$(_cred "admin_email")
WEB_PORT=$(_cred "web_port")

# ── --disable — revertir a HTTP plano (desde Sistema → Infraestructura) ─────
if [[ "${1:-}" == "--disable" ]]; then
    hdr "Desactivando HTTPS para $DOMAIN"
    INSTALL_DIR=$(awk -F= '/^INSTALL_DIR=/{print $2}' "$MARKER_FILE" 2>/dev/null || echo "/opt/voxikam")
    if [[ -f "$INSTALL_DIR/nginx/voxikam.conf" ]]; then
        sed \
            -e "s|__WEB_PORT__|$WEB_PORT|g" \
            -e "s|__DOMAIN__|$DOMAIN|g" \
            -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" \
            "$INSTALL_DIR/nginx/voxikam.conf" > /etc/nginx/sites-available/voxikam.conf
        nginx -t && systemctl reload nginx \
            && ok "vhost de nginx revertido a HTTP plano (plantilla del repo)" \
            || { err "nginx -t falló contra la plantilla revertida — revisar /etc/nginx/sites-available/voxikam.conf a mano"; exit 1; }
    else
        err "No se encontró $INSTALL_DIR/nginx/voxikam.conf — no se pudo revertir el vhost"
        exit 1
    fi
    if grep -q "^TLS_ENABLED=" "$MARKER_FILE" 2>/dev/null; then
        sed -i "s/^TLS_ENABLED=.*/TLS_ENABLED=0/" "$MARKER_FILE"
    fi
    ok "HTTPS desactivado — deploy.sh vuelve a controlar el vhost de nginx en el próximo --update/--upgrade"
    warn "El certificado emitido por Let's Encrypt NO se borra (no hace daño quieto) — solo se dejó de usar en el vhost"
    exit 0
fi

[[ -n "$DOMAIN" && "$DOMAIN" != "localhost" ]] || {
    err "No hay un dominio real configurado (domain=$DOMAIN en credentials.conf)."
    err "Let's Encrypt necesita un FQDN público que resuelva a este server — configura el dominio primero (Sistema → Dominio de acceso, o re-corriendo deploy.sh)."
    exit 1
}
[[ -n "$ADMIN_EMAIL" ]] || { err "No hay admin_email en credentials.conf — necesario para el registro ante Let's Encrypt."; exit 1; }

hdr "HTTPS para $DOMAIN"
info "Verificando que el dominio resuelva a este server..."
_PUB_IP=$(curl -fsS -4 https://ifconfig.me 2>/dev/null || curl -fsS -4 https://icanhazip.com 2>/dev/null || echo "")
_DNS_IP=$(getent hosts "$DOMAIN" | awk '{print $1}' | head -1 || echo "")
if [[ -n "$_PUB_IP" && -n "$_DNS_IP" && "$_PUB_IP" != "$_DNS_IP" ]]; then
    warn "$DOMAIN resuelve a $_DNS_IP pero la IP pública de este server parece ser $_PUB_IP."
    warn "Si el DNS todavía no propagó, certbot va a fallar la validación — no es un bug de este script."
    if [[ -t 0 ]]; then
        read -r -p "  ¿Continuar de todas formas? [s/N]: " C
        [[ "${C:-N}" =~ ^[Ss]$ ]] || exit 1
    else
        # Sin TTY (invocado desde el panel vía sudo, ver system_infra.py) — no
        # hay quien conteste un prompt. Seguir: si el DNS de verdad no
        # propagó, certbot igual va a fallar la validación un paso más
        # adelante con un error mucho más específico que este chequeo.
        warn "Sin terminal interactiva — se continúa igual, certbot validará el dominio de verdad a continuación"
    fi
fi

if ! command -v certbot &>/dev/null; then
    info "Instalando certbot + plugin de nginx..."
    apt-get update -qq
    apt-get install -y certbot python3-certbot-nginx
fi

info "Emitiendo certificado y configurando nginx (certbot --nginx)..."
certbot --nginx \
    -d "$DOMAIN" \
    -m "$ADMIN_EMAIL" \
    --agree-tos \
    --redirect \
    --non-interactive \
    && ok "Certificado emitido y nginx configurado para $DOMAIN" \
    || { err "certbot falló — revisar /var/log/letsencrypt/letsencrypt.log"; exit 1; }

# Deploy-hook de renovación — certbot.timer (paquete de Debian) ya renueva
# solo; esto asegura que nginx recargue el cert nuevo sin downtime cuando
# eso pase (certbot NO recarga servicios por defecto en el flujo de renovación).
mkdir -p /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh <<'EOF'
#!/bin/bash
systemctl reload nginx
EOF
chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
ok "Deploy-hook de renovación instalado (recarga nginx tras cada renovación automática)"

# Marcador — deploy.sh lo consulta para dejar de pisar el vhost de nginx
if grep -q "^TLS_ENABLED=" "$MARKER_FILE" 2>/dev/null; then
    sed -i "s/^TLS_ENABLED=.*/TLS_ENABLED=1/" "$MARKER_FILE"
else
    echo "TLS_ENABLED=1" >> "$MARKER_FILE"
fi

echo ""
ok "HTTPS activo → https://$DOMAIN"
warn "A partir de ahora, deploy.sh --update/--upgrade NO va a volver a sobrescribir /etc/nginx/sites-available/voxikam.conf — ver el comentario al inicio de este script para el motivo."
