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

router = APIRouter()
log = logging.getLogger("voxikam-security")


def _get_real_ip(request: Request) -> str:
    cf = request.headers.get("CF-Connecting-IP")
    if cf:
        return cf.strip().split(",")[0].strip()
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/login")
async def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT id, name, email, password_hash, role, customer_id, is_active FROM users WHERE email = :email"),
        {"email": form.username}
    )
    user = result.mappings().first()
    if not user or not verify_password(form.password, user["password_hash"]):
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
    }


@router.get("/me")
async def me(user=Depends(get_current_user)):
    return user
