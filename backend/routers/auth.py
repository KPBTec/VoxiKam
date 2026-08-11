# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

import hashlib
import logging
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from auth import create_token, verify_password, hash_password, get_current_user, resolve_permissions
from database import get_db
from mailer import send_email
from rate_limit import increment, peek_count, is_rate_limited
from routers.system import get_domain

router = APIRouter()
log = logging.getLogger("voxikam-security")

RESET_TOKEN_TTL_MINUTES = 60

# Auditoría v2.55: middleware/security.py ya limita /api/auth/login a 10/60s,
# pero eso es POR IP — un atacante rotando IPs (botnet, proxies rotativos)
# puede fuerza bruta una cuenta puntual sin acercarse a ese límite. Este es un
# segundo límite, independiente, keyeado por la cuenta objetivo en vez de por
# origen — no reemplaza al de IP, lo complementa.
#
# Re-auditoría v2.56.0: esto era un dict en memoria, mismo bug de fondo que
# cors_state.ALLOWED_ORIGINS ya tuvo (fragmentado entre workers con
# --workers>1) — migrado a rate_limit.py, respaldado en la tabla compartida
# rate_limit_counters. peek_count() (sin incrementar) es lo que permite
# seguir rechazando ANTES del SELECT de usuario sin gastar una query extra,
# igual que la versión en memoria; solo se incrementa cuando el login
# efectivamente FALLA (no cada intento) — mismo criterio de siempre.
_ACCOUNT_LOGIN_LIMIT = (8, 300)  # 8 intentos fallidos / 5 min por cuenta


def _account_key(email: str) -> str:
    return f"account:{email.strip().lower()}"


async def _account_rate_limited(db: AsyncSession, email: str) -> bool:
    max_fail, window = _ACCOUNT_LOGIN_LIMIT
    return await peek_count(db, _account_key(email), window) >= max_fail


async def _record_account_failure(db: AsyncSession, email: str) -> None:
    _, window = _ACCOUNT_LOGIN_LIMIT
    await increment(db, _account_key(email), window)


def _get_real_ip(request: Request) -> str:
    """
    Auditoría v2.55 (workflow multi-agente): esto antes confiaba en
    CF-Connecting-IP/X-Forwarded-For leídos directo del request, sin pasar
    por la resolución de proxy confiable de uvicorn. nginx antepone el valor
    del cliente en X-Forwarded-For ($proxy_add_x_forwarded_for) y nunca toca
    CF-Connecting-IP — así que un atacante podía mandar cualquiera de los
    dos headers con la IP de un carrier/cliente real, y el log
    SECURITY_REJECT de más abajo (que alimenta a fail2ban) baneaba esa IP
    durante 1 hora en TODOS los puertos. request.client.host SÍ es confiable
    acá: uvicorn corre con --proxy-headers --forwarded-allow-ips=127.0.0.1
    (ver systemd/voxikam-backend.service), que solo confía en el XFF cuando
    la conexión TCP directa viene de nginx en el mismo host — mismo patrón
    que ya usa correctamente middleware/security.py.
    """
    return request.client.host if request.client else "unknown"


@router.post("/login")
async def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    if await _account_rate_limited(db, form.username):
        log.warning("SECURITY_REJECT ip=%s reason=account_rate_limited path=/api/auth/login", _get_real_ip(request))
        raise HTTPException(status_code=429, detail="Demasiados intentos para esta cuenta — intenta más tarde")

    result = await db.execute(
        text("SELECT id, name, email, password_hash, role, customer_id, is_active, ui_theme FROM users WHERE email = :email"),
        {"email": form.username}
    )
    user = result.mappings().first()
    if not user or not verify_password(form.password, user["password_hash"]):
        await _record_account_failure(db, form.username)
        log.warning("SECURITY_REJECT ip=%s reason=login_failed path=/api/auth/login", _get_real_ip(request))
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="Cuenta suspendida")

    is_reseller = False
    if user["customer_id"]:
        cust = await db.execute(
            text("SELECT status, is_reseller FROM customers WHERE id = :id"), {"id": user["customer_id"]}
        )
        cust_row = cust.mappings().first()
        if cust_row and cust_row["status"] == "deleted":
            raise HTTPException(status_code=403, detail="Cliente desactivado")
        is_reseller = bool(cust_row and cust_row["is_reseller"])

    permissions = await resolve_permissions(db, user["customer_id"])

    # Antes solo se logueaba el login FALLIDO — un login exitoso (incluida una
    # cuenta admin comprometida) no dejaba ningún rastro de cuándo entró, solo
    # de lo que cambió después (vía audit.py). Mismo logger que el rechazo,
    # para que quede en el mismo lugar (journalctl -u voxikam-backend).
    log.info("LOGIN_OK ip=%s user_id=%s role=%s", _get_real_ip(request), user["id"], user["role"])

    token = create_token({"sub": str(user["id"]), "role": user["role"]})
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user["role"],
        "name": user["name"],
        "customer_id": user["customer_id"],
        "is_reseller": is_reseller,
        "permissions": permissions,
        "ui_theme": user["ui_theme"],
    }


@router.get("/me")
async def me(user=Depends(get_current_user)):
    return user


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str
    new_password: str


def _build_reset_link(domain: str, web_port: str) -> str:
    if web_port in ("443", "80", ""):
        return f"https://{domain}/reset-password"
    return f"https://{domain}:{web_port}/reset-password"


@router.post("/forgot-password")
async def forgot_password(request: Request, body: ForgotPasswordIn, db: AsyncSession = Depends(get_db)):
    """
    Auditoría UX v2.58.0: no había forma de recuperar la contraseña — un
    usuario bloqueado necesitaba que alguien con acceso a la DB se la
    reseteara a mano. Responde SIEMPRE el mismo mensaje genérico, exista o
    no la cuenta — lo contrario permite enumerar emails válidos probando
    cuáles devuelven una respuesta distinta.

    Rate limit por IP (no por cuenta, a propósito): a diferencia del login,
    acá "una cuenta" no es el vector de abuso — el vector es alguien
    generando emails de spam hacia bandejas ajenas escribiendo cualquier
    email real que conozca. Limitar por IP corta ese abuso sin bloquear a
    un usuario legítimo reintentando para su propia cuenta.
    """
    ip = _get_real_ip(request)
    if await is_rate_limited(db, f"forgot_password:{ip}", max_count=5, window_seconds=3600):
        log.warning("SECURITY_REJECT ip=%s reason=forgot_password_rate_limited", ip)
        return {"ok": True}

    generic_msg = {"ok": True}

    result = await db.execute(
        text("SELECT id, name, is_active FROM users WHERE email = :email"),
        {"email": body.email}
    )
    user = result.mappings().first()
    if not user or not user["is_active"]:
        return generic_msg

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires_at = datetime.utcnow() + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)

    await db.execute(text("""
        INSERT INTO password_reset_tokens (user_id, token_hash, expires_at)
        VALUES (:uid, :hash, :exp)
    """), {"uid": user["id"], "hash": token_hash, "exp": expires_at})
    await db.commit()

    domain, web_port = await get_domain(db)
    if not domain:
        log.warning("forgot_password: dominio no configurado (Sistema → Dominio), no se puede armar el link — email no enviado para user_id=%s", user["id"])
        return generic_msg

    link = f"{_build_reset_link(domain, web_port)}?token={raw_token}"
    html = f"""
    <div style="font-family:sans-serif;max-width:560px;margin:0 auto;background:#070b14;">
      <div style="background:#0d1526;padding:24px;border-radius:12px 12px 0 0;border:1px solid #1a2744;border-bottom:0;">
        <h1 style="color:#dd8b3d;margin:0;font-size:18px;">Recuperar contraseña</h1>
      </div>
      <div style="background:#070b14;border:1px solid #1a2744;border-top:0;border-radius:0 0 12px 12px;padding:20px 24px;">
        <p style="color:#e7ecf3;font-size:14px;">Hola {user['name']},</p>
        <p style="color:#e7ecf3;font-size:14px;">Pediste restablecer tu contraseña de VoxiKam. Este link vence en {RESET_TOKEN_TTL_MINUTES} minutos:</p>
        <p style="margin:20px 0;"><a href="{link}" style="background:#dd8b3d;color:#070b14;padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:600;">Restablecer contraseña</a></p>
        <p style="color:#5b7390;font-size:12px;">Si no fuiste vos, ignorá este correo — tu contraseña actual sigue funcionando.</p>
      </div>
    </div>
    """
    await send_email(db, body.email, "Recuperar contraseña — VoxiKam", html)
    return generic_msg


@router.post("/reset-password")
async def reset_password(body: ResetPasswordIn, db: AsyncSession = Depends(get_db)):
    if len(body.new_password) < 8:
        raise HTTPException(400, "La contraseña debe tener al menos 8 caracteres")

    token_hash = hashlib.sha256(body.token.encode()).hexdigest()
    result = await db.execute(text("""
        SELECT id, user_id FROM password_reset_tokens
        WHERE token_hash = :hash AND used_at IS NULL AND expires_at > NOW()
    """), {"hash": token_hash})
    row = result.mappings().first()
    if not row:
        raise HTTPException(400, "El link de recuperación es inválido o ya venció — pedí uno nuevo")

    await db.execute(
        text("UPDATE users SET password_hash = :h WHERE id = :id"),
        {"h": hash_password(body.new_password), "id": row["user_id"]}
    )
    # Invalida TODOS los tokens pendientes del usuario, no solo el usado —
    # si alguien pidió varios links seguidos, el más viejo no debe seguir
    # siendo válido después de que uno ya se usó para cambiar la contraseña.
    await db.execute(
        text("UPDATE password_reset_tokens SET used_at = NOW() WHERE user_id = :uid AND used_at IS NULL"),
        {"uid": row["user_id"]}
    )
    await db.commit()
    log.info("PASSWORD_RESET_OK user_id=%s", row["user_id"])
    return {"ok": True}


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


@router.put("/me/password")
async def change_my_password(body: ChangePasswordIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Cambio de contraseña estando logueado (sabe la actual) — complementa
    /forgot-password (para cuando NO la sabe). get_current_user() no trae
    password_hash a propósito (no queda cacheado en memoria 20s), se busca
    acá puntual."""
    if len(body.new_password) < 8:
        raise HTTPException(400, "La contraseña nueva debe tener al menos 8 caracteres")

    row = await db.execute(text("SELECT password_hash FROM users WHERE id = :id"), {"id": user["id"]})
    current_hash = row.scalar()
    if not current_hash or not verify_password(body.current_password, current_hash):
        raise HTTPException(400, "La contraseña actual no es correcta")

    await db.execute(
        text("UPDATE users SET password_hash = :h WHERE id = :id"),
        {"h": hash_password(body.new_password), "id": user["id"]}
    )
    await db.commit()
    return {"ok": True}


@router.put("/me/theme")
async def update_my_theme(body: dict, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Guarda la preferencia visual del usuario logueado (admin o cliente) —
    solo estética, cualquier rol puede cambiar la suya propia sin permisos
    especiales. Valor libre validado contra una lista fija en vez de un ENUM
    de DB, para no necesitar una migración cada vez que se agregue un tema."""
    theme = (body or {}).get("theme")
    if theme not in ("bronce", "papel", "fosforo", "vidrio"):
        raise HTTPException(400, "Tema inválido")
    await db.execute(
        text("UPDATE users SET ui_theme = :theme WHERE id = :id"),
        {"theme": theme, "id": user["id"]}
    )
    await db.commit()
    return {"ui_theme": theme}
