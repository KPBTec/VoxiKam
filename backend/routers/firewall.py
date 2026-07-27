# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from ipaddress import ip_address
import subprocess, sys
from pathlib import Path

from auth import require_admin
from database import get_db
from audit import record_event

router = APIRouter()
SCRIPTS = Path(__file__).parent.parent.parent / "scripts"


class RuleIn(BaseModel):
    ip: str
    action: str = "allow"
    service: str = "all"
    description: Optional[str] = None
    jail: bool = False

    @field_validator("ip")
    @classmethod
    def _ip_must_be_valid(cls, v: str) -> str:
        """Mismo criterio que customers.py::CustomerIPIn._ip_must_be_valid —
        se embebe sin escapar en una regla nftables generada por
        scripts/gen_nftables.py, aplicada como root vía `sudo nft -f`."""
        try:
            ip_address(v)
        except ValueError:
            raise ValueError(
                "Debe ser una dirección IP válida (IPv4 o IPv6) — se usa tal cual "
                "en una regla nftables generada"
            )
        return v


@router.get("")
async def list_rules(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("SELECT * FROM firewall_rules ORDER BY action, ip"))
    return r.mappings().all()


@router.post("", status_code=201)
async def add_rule(body: RuleIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    result = await db.execute(text("""
        INSERT INTO firewall_rules (ip, action, service, description, jail)
        VALUES (:ip, :action, :service, :description, :jail)
    """), body.model_dump())
    by = admin.get("name") or admin.get("email")
    await record_event(db, "firewall_rule", result.lastrowid, "created", by, f"{body.action} {body.ip} ({body.service})")
    await db.commit()
    _sync()
    return {"ok": True}


@router.put("/{rid}")
async def update_rule(rid: int, body: RuleIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    data = body.model_dump(); data["id"] = rid
    await db.execute(text(
        "UPDATE firewall_rules SET ip=:ip, action=:action, service=:service, description=:description, jail=:jail WHERE id=:id"
    ), data)
    by = admin.get("name") or admin.get("email")
    await record_event(db, "firewall_rule", rid, "updated", by, f"{body.action} {body.ip} ({body.service})")
    await db.commit()
    _sync()
    return {"ok": True}


@router.delete("/{rid}", status_code=204)
async def delete_rule(rid: int, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    row = await db.execute(text("SELECT ip, action FROM firewall_rules WHERE id=:id"), {"id": rid})
    old = row.mappings().first()
    await db.execute(text("DELETE FROM firewall_rules WHERE id = :id"), {"id": rid})
    by = admin.get("name") or admin.get("email")
    await record_event(db, "firewall_rule", rid, "deleted", by, f"{old['action']} {old['ip']}" if old else "")
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


# ── fail2ban — ver/desbanear IPs (backend corre nativo, llamada directa) ─────
FAIL2BAN_JAILS = ["sshd", "voxikam-security"]


def _parse_banned_ips(status_output: str) -> list[str]:
    for line in status_output.splitlines():
        line = line.strip()
        if "Banned IP list:" in line:
            ips = line.split(":", 1)[1].strip()
            return ips.split() if ips else []
    return []


@router.get("/fail2ban")
async def fail2ban_status(_=Depends(require_admin)):
    """IPs baneadas por jail. Requiere fail2ban-client en sudoers (ver sudoers/voxikam)."""
    result = {}
    for jail in FAIL2BAN_JAILS:
        try:
            p = subprocess.run(
                ["sudo", "fail2ban-client", "status", jail],
                capture_output=True, text=True, timeout=5,
            )
            result[jail] = _parse_banned_ips(p.stdout) if p.returncode == 0 else []
        except Exception:
            result[jail] = []
    return result


class UnbanIn(BaseModel):
    jail: str
    ip: str


@router.post("/fail2ban/unban")
async def fail2ban_unban(body: UnbanIn, _=Depends(require_admin)):
    if body.jail not in FAIL2BAN_JAILS:
        return {"ok": False, "error": "jail inválido"}
    subprocess.run(
        ["sudo", "fail2ban-client", "set", body.jail, "unbanip", body.ip],
        capture_output=True, timeout=5,
    )
    return {"ok": True}


# ── fail2ban — ver config actual (solo lectura) ──────────────────────────────
# Se lee con `fail2ban-client get` (valor REALMENTE cargado en el proceso),
# no el archivo /etc/fail2ban/jail.d/voxikam.conf — si alguien editó el
# archivo a mano sin recargar fail2ban, el archivo mentiría; esto no.
_FAIL2BAN_PARAMS = ["maxretry", "findtime", "bantime", "banaction"]


@router.get("/fail2ban/config")
async def fail2ban_config(_=Depends(require_admin)):
    result = {}
    for jail in FAIL2BAN_JAILS:
        cfg = {}
        for param in _FAIL2BAN_PARAMS:
            try:
                p = subprocess.run(
                    ["sudo", "fail2ban-client", "get", jail, param],
                    capture_output=True, text=True, timeout=5,
                )
                cfg[param] = p.stdout.strip() if p.returncode == 0 else None
            except Exception:
                cfg[param] = None
        result[jail] = cfg
    return result
