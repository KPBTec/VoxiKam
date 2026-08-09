# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Configura y dispara scripts/cron_external_sync.py — este router nunca habla
directo con la DB externa, solo guarda config y delega al script (mismo
patrón que gen_nftables.py/gen_dispatcher.py vía subprocess).
"""
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from auth import require_admin
from database import get_db
from audit import diff_and_record
from sync_runner import run_sync

router = APIRouter()

SCRIPTS = Path(__file__).parent.parent.parent / "scripts"
SYNC_SCRIPT = SCRIPTS / "cron_external_sync.py"

DEFAULT_PORTS = {"mysql": 3306, "postgres": 5432, "sqlserver": 1433}

PERMISSIONS_NEEDED = {
    "mysql":     ["CREATE (solo la primera vez, para crear la tabla cdrs si no existe)", "INSERT sobre esa tabla"],
    "postgres":  ["CREATE (solo la primera vez)", "INSERT"],
    "sqlserver": ["CREATE TABLE (solo la primera vez)", "INSERT",
                  "Requiere además unixODBC + driver ODBC de Microsoft (msodbcsql18) instalados en el servidor VoxiKam"],
}


class ConfigIn(BaseModel):
    engine: str
    host: str
    port: int
    db_name: str
    db_user: str
    db_pass: Optional[str] = None   # None/"" = no tocar la contraseña ya guardada
    enabled: bool = False


@router.get("/config")
async def get_config(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("SELECT * FROM external_sync_config WHERE id = 1"))
    row = dict(r.mappings().first() or {})
    return {
        "engine":  row.get("engine", "mysql"),
        "host":    row.get("host", ""),
        "port":    row.get("port", 3306),
        "db_name": row.get("db_name", ""),
        "db_user": row.get("db_user", ""),
        "has_password": bool(row.get("db_pass")),
        "enabled": bool(row.get("enabled")),
        "last_sync_at": row.get("last_sync_at"),
        "last_sync_id": row.get("last_sync_id"),
        "last_status": row.get("last_status"),
        "last_error": row.get("last_error"),
    }


@router.get("/permissions-needed")
async def permissions_needed(engine: str = "mysql", _=Depends(require_admin)):
    return {"engine": engine, "permissions": PERMISSIONS_NEEDED.get(engine, [])}


@router.put("/config")
async def update_config(body: ConfigIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    before_row = await db.execute(text("SELECT engine, host, port, db_name, enabled FROM external_sync_config WHERE id = 1"))
    before = dict(before_row.mappings().first() or {})

    fields = ["engine=:engine", "host=:host", "port=:port", "db_name=:db_name",
              "db_user=:db_user", "enabled=:enabled"]
    params = {
        "engine": body.engine, "host": body.host, "port": body.port,
        "db_name": body.db_name, "db_user": body.db_user, "enabled": body.enabled,
    }
    if body.db_pass:
        fields.append("db_pass=:db_pass")
        params["db_pass"] = body.db_pass

    await db.execute(text(f"UPDATE external_sync_config SET {', '.join(fields)} WHERE id = 1"), params)

    after = {"engine": body.engine, "host": body.host, "port": body.port,
              "db_name": body.db_name, "enabled": body.enabled}
    await diff_and_record(db, "external_sync_config", 1, before, after,
                           ["engine", "host", "port", "db_name", "enabled"],
                           admin.get("name") or admin.get("email"))
    await db.commit()
    return {"ok": True}


@router.post("/test-connection")
async def test_connection(_=Depends(require_admin)):
    p = subprocess.run(
        [sys.executable, str(SYNC_SCRIPT), "--test"],
        capture_output=True, text=True, timeout=15,
    )
    return {"ok": p.returncode == 0, "output": (p.stdout + p.stderr).strip()}


@router.post("/run-now")
async def run_now(admin=Depends(require_admin)):
    # Fire-and-forget: la primera sincronización de un histórico grande puede
    # tardar — el resultado se sigue en GET /log, no en la respuesta HTTP.
    # timeout largo acá también, solo como red de contención si el script
    # revienta ANTES de escribir su propio log (si termina normal, /log ya lo cuenta).
    run_sync(SYNC_SCRIPT, timeout=1800)
    return {"ok": True, "started": True}


@router.get("/log")
async def sync_log(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text(
        "SELECT * FROM external_sync_log ORDER BY started_at DESC LIMIT 30"
    ))
    return r.mappings().all()
