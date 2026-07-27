# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Estado de los servicios systemd de VoxiKam para Sistema → Salud — solo lectura
(systemctl show / journalctl -n, nunca restart/stop desde acá). Reiniciar o
seguir logs en vivo se hace por consola con el CLI `voxikam -r|-l` (scripts/
voxikam-cli.sh) — ese sí puede actuar porque corre con los permisos del admin
que lo invoca, no con los del usuario `voxikam` (backend), que a propósito
solo tiene sudo para nft/kamcmd (ver sudoers/voxikam).
"""
import asyncio

from fastapi import APIRouter, Depends

from auth import require_admin

router = APIRouter()

_UNITS = [
    {"key": "back",      "unit": "voxikam-backend",  "label": "Backend (FastAPI)"},
    {"key": "front",     "unit": "voxikam-frontend", "label": "Frontend (Next.js)"},
    {"key": "hep",       "unit": "voxikam-hep",      "label": "Captura HEP"},
    {"key": "clickhouse", "unit": "clickhouse-server", "label": "ClickHouse (Trazas SIP)"},
    {"key": "kamailio",  "unit": "kamailio",         "label": "Kamailio (SIP)"},
    {"key": "rtpengine", "unit": "rtpengine",        "label": "RTPEngine (RTP)"},
    {"key": "autotune",  "unit": "voxikam-autotune", "label": "Autotune (al arrancar)"},
]


async def _run(*args: str) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        return out.decode(errors="replace")
    except (asyncio.TimeoutError, FileNotFoundError, OSError):
        return ""


async def _unit_info(entry: dict) -> dict:
    unit = entry["unit"]
    raw = await _run(
        "systemctl", "show", unit,
        "--property=ActiveState,SubState,ActiveEnterTimestamp,MainPID,NRestarts,LoadState",
    )
    props = dict(line.split("=", 1) for line in raw.strip().splitlines() if "=" in line)

    log_raw = await _run("journalctl", "-u", unit, "-n", "5", "--no-pager", "-o", "cat")
    recent_logs = [l for l in log_raw.splitlines() if l.strip()]

    return {
        **entry,
        "load_state": props.get("LoadState", "unknown"),
        "active_state": props.get("ActiveState", "unknown"),
        "sub_state": props.get("SubState", "unknown"),
        "since": props.get("ActiveEnterTimestamp") or None,
        "pid": props.get("MainPID") if props.get("MainPID") not in (None, "0") else None,
        "restarts": props.get("NRestarts"),
        "recent_logs": recent_logs,
    }


@router.get("")
async def services_status(_=Depends(require_admin)):
    return await asyncio.gather(*(_unit_info(u) for u in _UNITS))
