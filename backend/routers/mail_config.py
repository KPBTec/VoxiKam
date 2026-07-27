# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Configuración de envío de correo (Resend o SMTP propio) — compartida por
Alertas de balance, Disconnect Policies y Facturas (envío automático). Vivía
embebida en el panel de Alertas de balance, pero no es específica de ese
módulo — la config es la misma para cualquier correo que mande VoxiKam.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from audit import record_event
from auth import require_admin
from database import get_db
from mailer import get_mail_config, send_email

router = APIRouter()

_TEXT_FIELDS = {
    "alert_from_email":  "Remitente de los correos de VoxiKam",
    "mail_provider":      "Proveedor de envío activo (resend | smtp)",
    "smtp_host":          "Host del servidor SMTP",
    "smtp_port":          "Puerto del servidor SMTP",
    "smtp_username":      "Usuario SMTP",
    "smtp_encryption":    "Cifrado SMTP (tls | ssl | none)",
}


class MailConfigIn(BaseModel):
    provider: str = "resend"                 # "resend" | "smtp"
    api_key: Optional[str] = None            # None/"" = no tocar la key ya guardada
    from_email: str
    restart_orphan_alerts: bool = False
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None      # None/"" = no tocar la contraseña ya guardada
    smtp_encryption: str = "tls"              # "tls" | "ssl" | "none"


@router.get("")
async def get_mail_config_status(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    """
    Nunca devuelve la API key ni la contraseña SMTP en texto plano — solo si
    hay una configurada (desde el panel o desde .env) y el resto de los datos
    no-secretos, para no hacerlos viajar de vuelta al navegador después de
    guardados.
    """
    cfg = await get_mail_config(db)
    r = await db.execute(text(
        "SELECT value FROM settings WHERE key_name = 'alert_restart_orphans_enabled'"
    ))
    row = r.first()
    return {
        "provider": cfg["provider"],
        "has_api_key": bool(cfg["api_key"]),
        "from_email": cfg["from_email"],
        "restart_orphan_alerts": bool(row and row[0] == "1"),
        "smtp_host": cfg["smtp_host"],
        "smtp_port": cfg["smtp_port"],
        "smtp_username": cfg["smtp_username"],
        "has_smtp_password": bool(cfg["smtp_password"]),
        "smtp_encryption": cfg["smtp_encryption"],
    }


async def _set(db: AsyncSession, key: str, value: str, description: str = "") -> None:
    await db.execute(text("""
        INSERT INTO settings (key_name, value, description)
        VALUES (:k, :v, :d)
        ON DUPLICATE KEY UPDATE value = :v
    """), {"k": key, "v": value, "d": description})


@router.put("")
async def set_mail_config(body: MailConfigIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    if body.provider not in ("resend", "smtp"):
        raise HTTPException(400, "provider debe ser 'resend' o 'smtp'")
    if body.smtp_encryption not in ("tls", "ssl", "none"):
        raise HTTPException(400, "smtp_encryption debe ser 'tls', 'ssl' o 'none'")

    await _set(db, "mail_provider", body.provider, _TEXT_FIELDS["mail_provider"])
    await _set(db, "alert_from_email", body.from_email, _TEXT_FIELDS["alert_from_email"])
    if body.api_key:
        await _set(db, "resend_api_key", body.api_key, "API key de Resend — sin esto, ningún correo se envía por Resend")
    await _set(db, "smtp_host", body.smtp_host or "", _TEXT_FIELDS["smtp_host"])
    await _set(db, "smtp_port", str(body.smtp_port), _TEXT_FIELDS["smtp_port"])
    await _set(db, "smtp_username", body.smtp_username or "", _TEXT_FIELDS["smtp_username"])
    await _set(db, "smtp_encryption", body.smtp_encryption, _TEXT_FIELDS["smtp_encryption"])
    if body.smtp_password:
        await _set(db, "smtp_password", body.smtp_password, "Contraseña SMTP — sin esto, ningún correo se envía por SMTP")
    await _set(db, "alert_restart_orphans_enabled", "1" if body.restart_orphan_alerts else "0",
               "Enviar correo cuando Kamailio se reinicia con llamadas en curso sin facturar (scripts/cleanup_active_calls.py)")
    # Nunca la API key/contraseña en el detalle — solo qué proveedor quedó
    # activo, para no guardar secretos en texto plano en un segundo lugar.
    await record_event(db, "mail_config", 0, "updated", admin.get("name") or admin.get("email"),
                        f"provider={body.provider}")
    await db.commit()
    return {"ok": True}


class TestEmailIn(BaseModel):
    to: str


@router.post("/test")
async def send_test_email(body: TestEmailIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    """Envía un correo de prueba con la config guardada AHORA MISMO — para validar antes de confiar en las alertas/facturas automáticas."""
    ok = await send_email(
        db, to=body.to,
        subject="VoxiKam — correo de prueba",
        html="""
        <div style="font-family:sans-serif;max-width:480px;margin:0 auto;background:#070b14;">
          <div style="background:#0d1526;padding:24px;border-radius:12px 12px 0 0;border:1px solid #1a2744;border-bottom:0;">
            <h1 style="color:#dd8b3d;margin:0;font-size:18px;">Correo de prueba</h1>
          </div>
          <div style="background:#070b14;border:1px solid #1a2744;border-top:0;border-radius:0 0 12px 12px;padding:20px 24px;">
            <p style="color:#e7ecf3;font-size:14px;">Si estás viendo esto, la configuración de correo de VoxiKam (Sistema → Correo) funciona correctamente.</p>
          </div>
        </div>
        """,
    )
    if not ok:
        raise HTTPException(502, "No se pudo enviar — revisar los datos de conexión y los logs del backend (journalctl -u voxikam-backend)")
    return {"ok": True}
