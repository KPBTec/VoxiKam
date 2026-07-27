# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Sistema → Infraestructura — panel para lo que hasta la auditoría de
arquitectura v2.47.0 solo se podía activar por SSH: HTTPS (Let's Encrypt),
backup automático de la DB, y alertas de infra por correo. Los tres ya
existían como scripts (scripts/setup_tls.sh, scripts/backup_db.sh,
scripts/cron_infra_alert.py) — esto es la capa de control + visibilidad
desde el panel, sin tener que entrar por consola.

Los scripts corren con sudo (allowlist exacta en sudoers/voxikam, mismo
patrón que system_services.py) — nunca un comando genérico.
"""
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from audit import record_event
from auth import require_admin
from database import get_db

router = APIRouter()

INSTALL_DIR = os.getenv("INSTALL_DIR", "/opt/voxikam")
MARKER_FILE = Path("/etc/voxikam.conf")
STATE_DIR = Path("/var/lib/voxikam")
TLS_ACTION_FILE = STATE_DIR / "tls_action_status.json"
BACKUP_RUN_FILE = STATE_DIR / "backup_last_run.json"
BACKUP_ACTION_FILE = STATE_DIR / "backup_action_status.json"
ALERT_STATUS_FILE = STATE_DIR / "infra_alert_status.json"
BACKUP_ROOT = Path("/var/backups/voxikam")


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _write_json(path: Path, data: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _marker_value(key: str) -> str:
    try:
        for line in MARKER_FILE.read_text().splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""


async def _setting(db: AsyncSession, key: str, default: bool = True) -> bool:
    r = await db.execute(text("SELECT value FROM settings WHERE key_name = :k"), {"k": key})
    row = r.first()
    if row is None:
        return default
    return row[0] != "0"


async def _set_setting(db: AsyncSession, key: str, value: bool, description: str) -> None:
    await db.execute(text("""
        INSERT INTO settings (key_name, value, description)
        VALUES (:k, :v, :d)
        ON DUPLICATE KEY UPDATE value = :v
    """), {"k": key, "v": "1" if value else "0", "d": description})


async def _run_privileged(cmd: list[str], status_file: Path, label: str) -> None:
    """Corre un script con sudo en background y deja el resultado en un
    archivo de estado — BackgroundTasks no puede devolver nada al cliente
    después de que la respuesta ya salió, así que el frontend hace polling
    de GET /admin/system/infra."""
    _write_json(status_file, {"status": "running", "label": label,
                               "started_at": datetime.now(timezone.utc).isoformat()})
    try:
        proc = await asyncio.create_subprocess_exec(
            "sudo", *cmd,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=180.0)
        ok = proc.returncode == 0
        _write_json(status_file, {
            "status": "ok" if ok else "error",
            "label": label,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "output_tail": out.decode(errors="replace")[-3000:],
        })
    except asyncio.TimeoutError:
        _write_json(status_file, {"status": "error", "label": label,
                                   "finished_at": datetime.now(timezone.utc).isoformat(),
                                   "output_tail": "Timeout (180s) — revisar journalctl -u voxikam-backend"})


@router.get("")
async def get_infra_status(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    domain = os.getenv("DOMAIN", "")
    tls_enabled = _marker_value("TLS_ENABLED") == "1"

    backup_files = sorted(BACKUP_ROOT.glob("mariadb/mariadb_*.sql.gz"),
                           key=lambda p: p.stat().st_mtime, reverse=True) if BACKUP_ROOT.exists() else []
    backup_last_run = _read_json(BACKUP_RUN_FILE)
    backup_action = _read_json(BACKUP_ACTION_FILE)

    alert_status = _read_json(ALERT_STATUS_FILE)

    return {
        "tls": {
            "enabled": tls_enabled,
            "domain": domain,
            "action": _read_json(TLS_ACTION_FILE),
        },
        "backup": {
            "enabled": await _setting(db, "backup_enabled", default=True),
            "last_run": backup_last_run,
            "action": backup_action,
            "recent_files": [
                {"name": p.name, "bytes": p.stat().st_size,
                 "modified_at": datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat()}
                for p in backup_files[:10]
            ],
        },
        "alerts": {
            "enabled": await _setting(db, "infra_alerts_enabled", default=True),
            "status": alert_status,
        },
    }


@router.post("/tls/enable")
async def enable_tls(background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    existing = _read_json(TLS_ACTION_FILE)
    if existing and existing.get("status") == "running":
        raise HTTPException(409, "Ya hay una operación de TLS en curso")
    background_tasks.add_task(_run_privileged,
                               [f"{INSTALL_DIR}/scripts/setup_tls.sh"], TLS_ACTION_FILE, "enable")
    await record_event(db, "system_infra", 0, "tls_enable_started", admin.get("name") or admin.get("email"), "")
    await db.commit()
    return {"ok": True, "status": "started"}


@router.post("/tls/disable")
async def disable_tls(background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    existing = _read_json(TLS_ACTION_FILE)
    if existing and existing.get("status") == "running":
        raise HTTPException(409, "Ya hay una operación de TLS en curso")
    background_tasks.add_task(_run_privileged,
                               [f"{INSTALL_DIR}/scripts/setup_tls.sh", "--disable"], TLS_ACTION_FILE, "disable")
    await record_event(db, "system_infra", 0, "tls_disable_started", admin.get("name") or admin.get("email"), "")
    await db.commit()
    return {"ok": True, "status": "started"}


class ToggleIn(BaseModel):
    enabled: bool


@router.put("/backup")
async def set_backup_enabled(body: ToggleIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    await _set_setting(db, "backup_enabled", body.enabled,
                        "Backup automático diario de MariaDB/ClickHouse (Sistema → Infraestructura)")
    await record_event(db, "system_infra", 0, "backup_toggle", admin.get("name") or admin.get("email"),
                        "enabled" if body.enabled else "disabled")
    await db.commit()
    return {"ok": True}


@router.post("/backup/run-now")
async def run_backup_now(background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    existing = _read_json(BACKUP_ACTION_FILE)
    if existing and existing.get("status") == "running":
        raise HTTPException(409, "Ya hay un backup en curso")
    background_tasks.add_task(_run_privileged,
                               [f"{INSTALL_DIR}/scripts/backup_db.sh", "--force"], BACKUP_ACTION_FILE, "run-now")
    await record_event(db, "system_infra", 0, "backup_run_now", admin.get("name") or admin.get("email"), "")
    await db.commit()
    return {"ok": True, "status": "started"}


@router.put("/alerts")
async def set_alerts_enabled(body: ToggleIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    await _set_setting(db, "infra_alerts_enabled", body.enabled,
                        "Alertas por correo de infraestructura — cron caído, disco/memoria (Sistema → Infraestructura)")
    await record_event(db, "system_infra", 0, "alerts_toggle", admin.get("name") or admin.get("email"),
                        "enabled" if body.enabled else "disabled")
    await db.commit()
    return {"ok": True}
