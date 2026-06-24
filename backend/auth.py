# la plataforma anterior — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

from datetime import datetime, timedelta
from typing import Optional
import os

import bcrypt as _bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db

SECRET_KEY = os.getenv("JWT_SECRET", "changeme")
ALGORITHM  = os.getenv("JWT_ALGORITHM", "HS256")
EXPIRE_MIN = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


def create_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=EXPIRE_MIN)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido o expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: Optional[int] = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(
        text("SELECT id, name, email, role, customer_id, is_active FROM users WHERE id = :id"),
        {"id": user_id}
    )
    user = result.mappings().first()
    if not user or not user["is_active"]:
        raise credentials_exception
    return dict(user)


async def require_admin(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Acceso solo para administradores")
    return user


async def require_client(user=Depends(get_current_user)):
    if user["role"] not in ("admin", "client"):
        raise HTTPException(status_code=403, detail="Acceso denegado")
    return user


def require_module(column: str, default_allow: bool = True):
    """Factory — dependency que verifica si un módulo del portal está habilitado.

    default_allow=True  → si la columna aún no existe (migration pendiente) se permite el acceso.
    default_allow=False → si la columna no existe se deniega (ej: show_invoices).
    Admin siempre tiene acceso sin importar el valor.
    """
    async def _check(
        user=Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> dict:
        if user["role"] == "admin":
            return user
        cid = user.get("customer_id")
        if not cid:
            raise HTTPException(status_code=403, detail="Sin cliente asociado")
        try:
            r = await db.execute(
                text(f"""
                    SELECT COALESCE(cp.`{column}`, cu.`{column}`) AS val
                    FROM customers cu
                    LEFT JOIN customer_profiles cp ON cu.profile_id = cp.id
                    WHERE cu.id = :id
                """),
                {"id": cid},
            )
            row = r.mappings().first()
            if row is None or not row["val"]:
                raise HTTPException(status_code=403, detail="Módulo no habilitado para este cliente")
        except HTTPException:
            raise
        except Exception:
            if not default_allow:
                raise HTTPException(status_code=403, detail="Módulo no disponible")
        return user
    return _check
