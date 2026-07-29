# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Envío de correo — Resend o SMTP
propio, a elección del admin en Sistema → Correo.

La configuración se guarda en la tabla `settings` — NO en `.env`. `.env`
(RESEND_API_KEY/ALERT_FROM_EMAIL) solo sirve como fallback para quien
prefiera configurarlo por archivo, y solo aplica al proveedor Resend (el
fallback histórico, de antes de que existiera el selector de proveedor).
Si no hay nada configurado, send_email() no intenta nada — se loguea y
listo, nunca lanza excepción hacia el llamador (un fallo de envío no debe
interrumpir el billing ni ninguna otra lógica).
"""

import base64
import html
import logging
import os
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger("voxikam.mailer")

RESEND_API_URL = "https://api.resend.com/emails"
_DEFAULT_FROM = "no-reply@kpbtec.com"

_SETTINGS_KEYS = (
    "mail_provider", "resend_api_key", "alert_from_email",
    "smtp_host", "smtp_port", "smtp_username", "smtp_password", "smtp_encryption",
)


async def get_mail_config(db: AsyncSession) -> dict:
    """Config de envío: tabla `settings` primero, `.env` como fallback (solo Resend)."""
    row = await db.execute(text(
        f"SELECT key_name, value FROM settings WHERE key_name IN ({','.join(':k'+str(i) for i in range(len(_SETTINGS_KEYS)))})"
    ), {f"k{i}": k for i, k in enumerate(_SETTINGS_KEYS)})
    stored = {r[0]: r[1] for r in row.all()}
    return {
        "provider":       stored.get("mail_provider") or "resend",
        "api_key":        stored.get("resend_api_key") or os.getenv("RESEND_API_KEY", ""),
        "from_email":     stored.get("alert_from_email") or os.getenv("ALERT_FROM_EMAIL", _DEFAULT_FROM),
        "smtp_host":      stored.get("smtp_host") or "",
        "smtp_port":      int(stored.get("smtp_port") or 587),
        "smtp_username":  stored.get("smtp_username") or "",
        "smtp_password":  stored.get("smtp_password") or "",
        "smtp_encryption": stored.get("smtp_encryption") or "tls",
    }


async def _send_via_resend(cfg: dict, to: str, subject: str, html: str, attachments: Optional[list[dict]]) -> bool:
    if not cfg["api_key"]:
        log.warning("send_email: sin API key de Resend configurada (Sistema → Correo) — correo no enviado (asunto: %s)", subject)
        return False

    payload = {"from": f"VoxiKam <{cfg['from_email']}>", "to": [to], "subject": subject, "html": html}
    if attachments:
        payload["attachments"] = attachments

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                RESEND_API_URL,
                headers={"Authorization": f"Bearer {cfg['api_key']}"},
                json=payload,
            )
        if resp.status_code >= 300:
            log.error("send_email (resend): API respondió %s — %s", resp.status_code, resp.text[:300])
            return False
        return True
    except Exception as e:
        log.error("send_email (resend): error de red — %s", e)
        return False


async def _send_via_smtp(cfg: dict, to: str, subject: str, html: str, attachments: Optional[list[dict]]) -> bool:
    if not cfg["smtp_host"] or not cfg["smtp_username"]:
        log.warning("send_email: SMTP incompleto (host/usuario) — correo no enviado (asunto: %s)", subject)
        return False

    import aiosmtplib

    msg = MIMEMultipart()
    msg["From"] = f"VoxiKam <{cfg['from_email']}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(html, "html"))
    for att in attachments or []:
        part = MIMEApplication(base64.b64decode(att["content"]), Name=att["filename"])
        part["Content-Disposition"] = f'attachment; filename="{att["filename"]}"'
        msg.attach(part)

    encryption = cfg["smtp_encryption"]
    try:
        await aiosmtplib.send(
            msg,
            hostname=cfg["smtp_host"],
            port=cfg["smtp_port"],
            username=cfg["smtp_username"] or None,
            password=cfg["smtp_password"] or None,
            use_tls=(encryption == "ssl"),
            start_tls=(encryption == "tls"),
            timeout=20.0,
        )
        return True
    except Exception as e:
        log.error("send_email (smtp): %s", e)
        return False


async def send_email(
    db: AsyncSession, to: str, subject: str, html: str,
    attachments: Optional[list[dict]] = None,
) -> bool:
    """attachments: [{"filename": str, "content": <base64 str>}, ...]."""
    cfg = await get_mail_config(db)
    if cfg["provider"] == "smtp":
        return await _send_via_smtp(cfg, to, subject, html, attachments)
    return await _send_via_resend(cfg, to, subject, html, attachments)


def alert_html(title: str, rows: list[tuple[str, str]], footer: str = "") -> str:
    """
    Plantilla mínima consistente para alertas — misma paleta que el resto de
    VoxiKam. Todo valor pasa por html.escape() — `rows` casi siempre incluye
    el nombre del cliente (texto libre editable por un admin en customers.py,
    sin validación de tags HTML, solo de caracteres de control), y este
    correo va al email interno de notificación de alertas — sin escapar acá,
    un nombre con HTML/JS quedaba embebido tal cual en la bandeja del
    operador que recibe las alertas.
    """
    rows_html = "".join(
        f'<tr><td style="padding:8px 0;color:#5b7390;font-size:13px;width:160px;">{html.escape(str(k))}</td>'
        f'<td style="padding:8px 0;color:#e7ecf3;font-size:13px;">{html.escape(str(v))}</td></tr>'
        for k, v in rows
    )
    safe_title = html.escape(title)
    safe_footer = html.escape(footer) if footer else ""
    return f"""
    <div style="font-family:sans-serif;max-width:560px;margin:0 auto;background:#070b14;">
      <div style="background:#0d1526;padding:24px;border-radius:12px 12px 0 0;border:1px solid #1a2744;border-bottom:0;">
        <h1 style="color:#dd8b3d;margin:0;font-size:18px;">{safe_title}</h1>
      </div>
      <div style="background:#070b14;border:1px solid #1a2744;border-top:0;border-radius:0 0 12px 12px;padding:20px 24px;">
        <table style="width:100%;border-collapse:collapse;">{rows_html}</table>
        {f'<p style="color:#5b7390;font-size:12px;margin-top:16px;">{safe_footer}</p>' if safe_footer else ''}
      </div>
    </div>
    """
