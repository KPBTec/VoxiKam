# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

import os
import re

import psutil
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from auth import require_admin
from audit import record_event
from database import get_db
import cors_state

router = APIRouter()

_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$"
)


def _fmt_bytes(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


@router.get("")
async def system_stats(_=Depends(require_admin)):
    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    load1, load5, load15 = os.getloadavg()

    net_raw = psutil.net_io_counters(pernic=True)
    net = [
        {
            "iface":   iface,
            "rx_str":  _fmt_bytes(c.bytes_recv),
            "tx_str":  _fmt_bytes(c.bytes_sent),
        }
        for iface, c in net_raw.items()
        if iface != "lo"
    ]

    return {
        "cpu_percent":   cpu,
        "load_avg":      round(load1, 2),
        "ram_percent":   mem.percent,
        "ram_used_gb":   round(mem.used  / 1024 ** 3, 2),
        "ram_total_gb":  round(mem.total / 1024 ** 3, 1),
        "disk_percent":  disk.percent,
        "disk_used_gb":  round(disk.used  / 1024 ** 3, 1),
        "disk_total_gb": round(disk.total / 1024 ** 3, 1),
        "net": net,
    }


async def get_domain(db: AsyncSession) -> tuple[str, str]:
    """Dominio guardado desde el panel (tabla settings) — vacío si nunca se
    configuró (la instalación sigue funcionando por IP/puerto sin esto)."""
    r = await db.execute(text(
        "SELECT key_name, value FROM settings WHERE key_name IN ('system_domain', 'system_domain_port')"
    ))
    stored = {row[0]: row[1] for row in r.all()}
    return stored.get("system_domain") or "", stored.get("system_domain_port") or "80"


async def set_domain(db: AsyncSession, domain: str, web_port: int, admin_name: str) -> None:
    domain = domain.strip().lower()
    if not _HOSTNAME_RE.match(domain):
        raise ValueError(f"'{domain}' no es un dominio/hostname válido")
    if not (1 <= web_port <= 65535):
        raise ValueError("web_port debe estar entre 1 y 65535")

    await db.execute(text("""
        INSERT INTO settings (key_name, value, description)
        VALUES ('system_domain', :domain, 'Dominio (FQDN) de acceso al panel — ver Sistema → Dominio de acceso')
        ON DUPLICATE KEY UPDATE value = :domain
    """), {"domain": domain})
    await db.execute(text("""
        INSERT INTO settings (key_name, value, description)
        VALUES ('system_domain_port', :port, 'Puerto asociado al dominio de acceso')
        ON DUPLICATE KEY UPDATE value = :port
    """), {"port": str(web_port)})
    await record_event(db, "system_domain", 0, "updated", admin_name, domain)
    await db.commit()

    # Aplica en caliente en ESTE proceso — sin esto, el cambio solo se
    # vería después de un restart (ver main.py::lifespan, que hace lo
    # mismo al arrancar para no perder el valor entre reinicios).
    cors_state.add_origin(domain, web_port)


class DomainIn(BaseModel):
    domain: str
    web_port: int = 80


@router.get("/domain")
async def get_domain_endpoint(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    domain, web_port = await get_domain(db)
    return {"domain": domain, "web_port": int(web_port)}


@router.put("/domain")
async def set_domain_endpoint(body: DomainIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    try:
        await set_domain(db, body.domain, body.web_port, admin.get("name") or admin.get("email"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}
