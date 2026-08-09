# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Peers LAN (Asterisk/ViciBox) — tráfico ENTRANTE (carrier → Asterisk, Grupo 1
de dispatcher, ver scripts/gen_dispatcher.py). Antes era un campo de texto
suelto (settings.lan_peers, CSV) sin ningún endpoint ni pantalla — el propio
gen_dispatcher.py ya daba por hecha una página "Settings > LAN Peers" que
nunca se construyó. CRUD simple, mismo criterio que customer_ips
(backend/routers/customers.py) — alta/baja, sin edición.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from pathlib import Path

from auth import require_admin
from database import get_db
from audit import record_event
from sync_runner import run_sync

router = APIRouter()
SCRIPTS = Path(__file__).parent.parent.parent / "scripts"


class LanPeerIn(BaseModel):
    host: str
    port: int = 5060
    description: Optional[str] = None

    @field_validator("host")
    @classmethod
    def _host_no_control_chars(cls, v: str) -> str:
        """Se embebe sin escapar en dispatcher.list (Grupo 1) — mismo
        criterio defensivo que customers.name/carrier_groups.name."""
        v = v.strip()
        if not v or any(ord(c) < 32 or ord(c) == 127 for c in v):
            raise ValueError("host no puede estar vacío ni contener saltos de línea/caracteres de control")
        return v

    @field_validator("port")
    @classmethod
    def _port_range(cls, v: int) -> int:
        if not (1 <= v <= 65535):
            raise ValueError("port debe estar entre 1 y 65535")
        return v


@router.get("")
async def list_lan_peers(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("SELECT id, host, port, description, created_at FROM lan_peers ORDER BY host"))
    return r.mappings().all()


@router.post("", status_code=201)
async def add_lan_peer(body: LanPeerIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    dup = await db.execute(text(
        "SELECT 1 FROM lan_peers WHERE host = :host AND port = :port"
    ), {"host": body.host, "port": body.port})
    if dup.first():
        raise HTTPException(409, "Ya existe un peer con ese host y puerto")
    result = await db.execute(text(
        "INSERT INTO lan_peers (host, port, description) VALUES (:host, :port, :description)"
    ), body.model_dump())
    await record_event(db, "lan_peer", result.lastrowid, "created",
                        admin.get("name") or admin.get("email"), f"{body.host}:{body.port}")
    await db.commit()
    _sync_dispatcher()
    return {"id": result.lastrowid}


@router.delete("/{peer_id}", status_code=204)
async def delete_lan_peer(peer_id: int, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    row = await db.execute(text("SELECT host, port FROM lan_peers WHERE id = :id"), {"id": peer_id})
    peer = row.mappings().first()
    await db.execute(text("DELETE FROM lan_peers WHERE id = :id"), {"id": peer_id})
    if peer:
        await record_event(db, "lan_peer", peer_id, "deleted",
                            admin.get("name") or admin.get("email"), f"{peer['host']}:{peer['port']}")
    await db.commit()
    _sync_dispatcher()


def _sync_dispatcher():
    run_sync(SCRIPTS / "gen_dispatcher.py")
