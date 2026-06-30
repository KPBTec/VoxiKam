# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import subprocess, sys
from pathlib import Path

from auth import require_admin
from database import get_db

router = APIRouter()
SCRIPTS = Path(__file__).parent.parent.parent / "scripts"


class RuleIn(BaseModel):
    ip: str
    action: str = "allow"
    service: str = "all"
    description: Optional[str] = None
    jail: bool = False


@router.get("")
async def list_rules(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("SELECT * FROM firewall_rules ORDER BY action, ip"))
    return r.mappings().all()


@router.post("", status_code=201)
async def add_rule(body: RuleIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(text("""
        INSERT INTO firewall_rules (ip, action, service, description, jail)
        VALUES (:ip, :action, :service, :description, :jail)
    """), body.model_dump())
    await db.commit()
    _sync()
    return {"ok": True}


@router.put("/{rid}")
async def update_rule(rid: int, body: RuleIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    data = body.model_dump(); data["id"] = rid
    await db.execute(text(
        "UPDATE firewall_rules SET ip=:ip, action=:action, service=:service, description=:description, jail=:jail WHERE id=:id"
    ), data)
    await db.commit()
    _sync()
    return {"ok": True}


@router.delete("/{rid}", status_code=204)
async def delete_rule(rid: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(text("DELETE FROM firewall_rules WHERE id = :id"), {"id": rid})
    await db.commit()
    _sync()


@router.post("/{rid}/jail")
async def toggle_jail(rid: int, jail: bool, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(text("UPDATE firewall_rules SET jail=:jail WHERE id=:id"), {"jail": jail, "id": rid})
    await db.commit()
    _sync()
    return {"ok": True}


def _sync():
    subprocess.Popen([sys.executable, str(SCRIPTS / "gen_nftables.py")])
