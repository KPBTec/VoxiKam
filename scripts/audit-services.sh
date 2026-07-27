#!/bin/bash
# audit-services.sh — SOLO LECTURA. No detiene ni deshabilita nada.
#
# Lista los servicios systemd habilitados en el server y señala candidatos a
# deshabilitar para achicar la superficie de un SBC de producción — con el
# motivo de cada uno, para decidir a mano. Nunca actúa solo: correr esto,
# revisar la salida, y recién ahí decidir qué apagar con
# `systemctl disable --now <servicio>` uno por uno.
set -euo pipefail

echo "═══ Servicios habilitados (arrancan en cada boot) ═══"
systemctl list-unit-files --state=enabled --type=service --no-pager

echo
echo "═══ Servicios activos ahora mismo ═══"
systemctl list-units --type=service --state=running --no-pager

echo
echo "═══ Candidatos a revisar (con motivo) ═══"

_check() {
    local svc="$1" reason="$2"
    if systemctl is-enabled --quiet "$svc" 2>/dev/null; then
        echo "  [ACTIVO]  $svc — $reason"
    fi
}

_check qemu-guest-agent.service "Solo aporta algo si el panel del hosting lo consulta (apagado prolijo, IP reportada al hypervisor). Si no se usa esa integración, se puede apagar — si se usa, apagarlo degrada lo que ve el panel del proveedor del VM."
_check avahi-daemon.service    "Descubrimiento de red local (mDNS/Bonjour) — sin uso en un SBC headless."
_check cups.service            "Sistema de impresión — sin uso en un server."
_check cups-browsed.service    "Idem cups.service."
_check ModemManager.service    "Gestión de módems 3G/4G — sin uso salvo que el server tenga uno."
_check bluetooth.service       "Sin uso en un server sin hardware Bluetooth."
_check snapd.service           "Si no se instaló software vía snap, no hace falta el daemon corriendo todo el tiempo."

echo
echo "═══ rpcbind + grabación de llamadas por NFS — CASO ESPECIAL, no es bloat genérico ═══"
# Confirmado en vd1sbc2: rpcbind.service está ACTIVO porque
# rtpengine-recording-nfs-mount.service lo necesita para montar el NFS donde
# rtpengine-recording-daemon guarda las grabaciones. Los tres van juntos —
# apagar rpcbind sin confirmar rompe la grabación de llamadas SI se usa ese
# feature. No hay forma de saberlo desde acá: hay que confirmarlo a mano.
if systemctl is-enabled --quiet rtpengine-recording-nfs-mount.service 2>/dev/null; then
    echo "  rtpengine-recording-nfs-mount.service está HABILITADO — este server graba llamadas a un NFS."
    mount | grep -q nfs && echo "  Hay un mount NFS activo ahora mismo (mount | grep nfs)." \
                        || echo "  No hay un mount NFS activo ahora mismo — puede estar montado bajo demanda."
    echo "  Antes de tocar rpcbind: confirmar si la grabación de llamadas es un feature que se usa de verdad."
    echo "  Si SÍ se usa: dejar rpcbind + rtpengine-recording-nfs-mount + rtpengine-recording-daemon como están."
    echo "  Si NO se usa: los tres se pueden apagar juntos, y libera CPU real (7 procesos rtpengine-recording en ps/htop)."
else
    echo "  rtpengine-recording-nfs-mount.service no está habilitado — si rpcbind sigue activo igual, revisar quién más lo usa antes de apagarlo (NFS/NIS de otro proceso)."
fi

echo
echo "═══ Workers del backend (voxikam-backend) ═══"
grep -oP '(?<=--workers )\d+' /etc/systemd/system/voxikam-backend.service 2>/dev/null \
    | xargs -I{} echo "  Configurado con {} workers — comparar contra nproc:"
nproc 2>/dev/null | xargs -I{} echo "  CPUs disponibles: {}"
echo "  (Kamailio + RTPEngine + MariaDB comparten el mismo box — 7 workers puede ser demasiado si nproc es 8; ver scripts/autotune.sh)"
