# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from auth import create_token, verify_password, get_current_user, resolve_permissions
from database import get_db
from rate_limit import increment, peek_count

router = APIRouter()
log = logging.getLogger("voxikam-security")

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
