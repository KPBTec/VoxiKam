# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Barrido de TODOS los servicios systemd habilitados en el server — no solo los
de VoxiKam (ver services_status.py para esos) — para detectar candidatos a
apagar en un SBC de producción (menos superficie, menos RAM/CPU ocioso).

Clasificación deliberadamente ESTÁTICA (allowlist), no "inteligente" en
runtime: adivinar si un servicio "está en uso" observando el sistema es poco
confiable, y acá el costo de un falso positivo es alto (Kamailio/MariaDB/SSH
apagados por error en un SBC de producción). Tres categorías:

  - REQUIRED   → VoxiKam o la base del OS lo necesitan. Informativo, sin acción.
  - ACTIONABLE → candidatos conocidos y comunes a un headless Debian que se
                 pueden apagar/reencender desde acá con un click. Sudoers
                 (sudoers/voxikam) autoriza SOLO estos comandos exactos, uno
                 por uno — nunca `systemctl` genérico.
  - UNKNOWN    → cualquier otro servicio habilitado que no está en ninguna de
                 las dos listas de arriba. Se MUESTRA (transparencia total)
                 pero sin botón — desconocido no es lo mismo que "seguro de
                 apagar", revisar por consola con criterio antes de tocarlo.
"""
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from audit import record_event
from auth import require_admin
from database import get_db

router = APIRouter()

REQUIRED = {
    "ssh.service", "sshd.service",
    "mariadb.service", "mysql.service",
    "clickhouse-server.service",
    "kamailio.service",
    # Nombre real confirmado en vd1sbc2 (paquete rtpengine de Debian) —
    # "rtpengine.service" a secas no existe. rtpengine-recording-daemon NO
    # está acá — ver ACTIONABLE, el usuario confirmó que no usa grabación.
    "rtpengine-daemon.service",
    "voxikam-backend.service", "voxikam-frontend.service", "voxikam-hep.service", "voxikam-autotune.service",
    "nginx.service",
    "cron.service", "rsyslog.service",
    "fail2ban.service",
    "nftables.service",
    "systemd-journald.service", "systemd-udevd.service", "systemd-timesyncd.service",
    "systemd-networkd.service", "systemd-resolved.service", "systemd-logind.service",
    "networking.service", "dbus.service",
    # Base del OS en un Debian netinst mínimo (confirmado en vd1sbc2) — arrancan
    # solos, no consumen nada corriendo, no tiene sentido ofrecer apagarlos.
    "apparmor.service", "blk-availability.service", "console-setup.service",
    "e2scrub_reap.service", "keyboard-setup.service", "lvm2-monitor.service",
    "systemd-pstore.service", "getty@.service", "getty@tty1.service",
}

# unit → explicación mostrada en el panel. Cada uno necesita una línea exacta
# en sudoers/voxikam (disable --now Y enable --now) — si falta, el endpoint
# de acción devuelve 500 al intentar sudo, no falla silenciosamente.
ACTIONABLE = {
    "avahi-daemon.service":  "Descubrimiento de red local (mDNS/Bonjour) — sin uso en un SBC headless.",
    "cups.service":          "Sistema de impresión — sin uso en un server.",
    "cups-browsed.service":  "Idem cups.service — se apagan juntos.",
    "ModemManager.service":  "Gestión de módems 3G/4G — sin uso salvo que el server tenga uno físico.",
    "bluetooth.service":     "Sin uso en un server sin hardware Bluetooth.",
    "snapd.service":         "Si no instalaste nada vía snap, no hace falta el daemon corriendo todo el tiempo.",
    # Confirmado por el admin (2026-07-08): no usa grabación de llamadas — los
    # tres van juntos, apagar solo uno deja huérfano al resto.
    "rtpengine-recording-daemon.service":  "Grabación de llamadas — confirmado que no se usa. Libera CPU real (7 procesos vistos en producción).",
    "rtpengine-recording-nfs-mount.service": "Mount NFS donde se guardaban las grabaciones — sin uso si rtpengine-recording-daemon está apagado.",
    "rpcbind.service": "Solo servía para el mount NFS de arriba — sin otro uso conocido en VoxiKam (NFS/NIS).",
}


async def _run(*args: str) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=8.0)
        return out.decode(errors="replace")
    except (asyncio.TimeoutError, FileNotFoundError, OSError):
        return ""


@router.get("")
async def list_services(_=Depends(require_admin)):
    raw = await _run("systemctl", "list-unit-files", "--type=service", "--state=enabled", "--no-legend", "--no-pager")
    units = [line.split()[0] for line in raw.strip().splitlines() if line.strip()]

    active_raw = await _run("systemctl", "list-units", "--type=service", "--state=running", "--no-legend", "--no-pager")
    active = {line.split()[0] for line in active_raw.strip().splitlines() if line.strip()}

    out = {"required": [], "actionable": [], "unknown": []}
    for u in units:
        running = u in active
        if u in REQUIRED:
            out["required"].append({"unit": u, "running": running})
        elif u in ACTIONABLE:
            out["actionable"].append({"unit": u, "running": running, "reason": ACTIONABLE[u]})
        else:
            out["unknown"].append({"unit": u, "running": running})
    return out


class ServiceAction(BaseModel):
    action: str  # "disable" | "enable"


@router.post("/{unit}/action")
async def act_on_service(unit: str, body: ServiceAction,
                          db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    if unit not in ACTIONABLE:
        raise HTTPException(403, "Este servicio no está en la lista de candidatos conocidos — no se puede apagar desde el panel, revisar por consola")
    if body.action not in ("disable", "enable"):
        raise HTTPException(400, "action debe ser 'disable' o 'enable'")

    proc = await asyncio.create_subprocess_exec(
        "sudo", "systemctl", body.action, "--now", unit,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise HTTPException(502, f"systemctl {body.action} {unit} falló: {err.decode(errors='replace')[:300]}")

    # Auditado — es una acción con sudo real sobre el sistema (impacto en
    # servicio/seguridad), no un cambio de campo, pero record_event() ya
    # está pensado para justo esto (crear/borrar/activar/desactivar). Sin
    # entity_id numérico natural para un nombre de unit — se usa 0 y el
    # nombre del servicio va en el detalle.
    await record_event(db, "system_service", 0, body.action,
                        admin.get("name") or admin.get("email"), unit)
    await db.commit()
    return {"ok": True, "unit": unit, "action": body.action}
