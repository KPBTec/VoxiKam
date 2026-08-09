# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

from datetime import datetime, timedelta
from typing import Optional
import hashlib
import hmac
import os
import time

import bcrypt as _bcrypt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db

# Sin fallback inseguro a propósito (encontrado en la auditoría de seguridad
# global, v2.38.0): un "changeme" por defecto significa que si el backend
# arrancara alguna vez sin .env cargado, cualquier JWT firmado con ese secreto
# público conocido pasaría la verificación — falla el arranque en vez de
# aceptar tokens silenciosamente inseguros.
# Revisado en la auditoría de arquitectura (v2.46.0): no hay blacklist de
# tokens ni refresh token, así que en teoría un token robado sirve hasta las
# 8h de acá. En la práctica el hueco real es más chico: get_current_user()
# revalida is_active/customer_status contra la DB cada 20s (ver
# _USER_CACHE_TTL abajo) — desactivar la cuenta comprometida corta el acceso
# en ~20s, no en 8h. El caso que sigue sin cubrir es el que ningún mecanismo
# de revocación resuelve solo: que nadie note el robo y desactive la cuenta.
# No se acortó EXPIRE_MIN acá — es un trade-off real de UX (relogins más
# frecuentes para el staff) que no correspondía decidir de forma unilateral.
SECRET_KEY = os.environ["JWT_SECRET"]
ALGORITHM  = os.getenv("JWT_ALGORITHM", "HS256")
EXPIRE_MIN = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))

CDR_INGEST_SECRET = os.getenv("CDR_INGEST_SECRET", "")


async def require_ingest_secret(x_ingest_secret: str | None = Header(None)) -> None:
    """
    Protege POST /api/admin/cdrs/ingest — encontrado sin ninguna autenticación
    en la auditoría de seguridad global (v2.38.0): identificaba al cliente por
    un campo del propio payload (src_ip), permitiendo a cualquiera en Internet
    drenar el saldo de un cliente con un POST fabricado. No usa JWT porque su
    llamador (si algún día se usa — ver docstring de ingest_cdr) no puede
    loguearse como usuario, es un posible caller máquina-a-máquina.
    """
    # Auditoría v2.55: comparar con != hace short-circuit en el primer byte
    # distinto — canal de temporización que en teoría permite reconstruir el
    # secreto byte a byte. hmac.compare_digest() es constante-en-tiempo.
    if not CDR_INGEST_SECRET or not x_ingest_secret or not hmac.compare_digest(x_ingest_secret, CDR_INGEST_SECRET):
        raise HTTPException(status_code=401, detail="Secreto de ingest inválido o ausente")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# get_current_user() consultaba MySQL en CADA request sin cache — /traces en
# modo "en vivo" hace polling cada 1s, así que cada analista viendo esa
# pantalla generaba una query por segundo solo para validar el token. Sin
# Redis en este stack (a diferencia de VoxiDet), cache simple en memoria por
# worker con TTL corto — no hay invalidación activa al desactivar un usuario,
# así que el TTL se mantiene bajo (20s) para no dejar una cuenta desactivada
# funcionando por mucho tiempo.
_USER_CACHE_TTL = 20
_user_cache: dict[int, tuple[dict, float]] = {}


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

    now = time.monotonic()
    cached = _user_cache.get(user_id)
    if cached and now - cached[1] < _USER_CACHE_TTL:
        return cached[0]

    result = await db.execute(
        text("""
            SELECT u.id, u.name, u.email, u.role, u.customer_id, u.is_active,
                   cu.status AS customer_status
            FROM users u
            LEFT JOIN customers cu ON u.customer_id = cu.id
            WHERE u.id = :id
        """),
        {"id": user_id}
    )
    user = result.mappings().first()
    # customer_status es NULL para admin (customer_id NULL) — solo bloquea a
    # un usuario 'client' cuyo cliente pasó a status='deleted' (desactivado
    # desde el panel). Mismo TTL de 20s que is_active, no hay invalidación activa.
    if not user or not user["is_active"] or user["customer_status"] == "deleted":
        _user_cache.pop(user_id, None)
        raise credentials_exception
    user_dict = dict(user)
    _user_cache[user_id] = (user_dict, now)
    return user_dict


async def require_admin(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Acceso solo para administradores")
    return user


async def require_client(user=Depends(get_current_user)):
    if user["role"] not in ("admin", "client"):
        raise HTTPException(status_code=403, detail="Acceso denegado")
    return user


async def has_permission(db: AsyncSession, customer_id: int, resource_key: str) -> bool:
    """
    Resuelve un permiso puntual — COALESCE(override del cliente, override del
    perfil, default_visible de la plataforma), mismo criterio de precedencia
    que ya usaba require_module() (perfil pisa propio, propio es el fallback,
    acá "propio" es un override en profile_permissions con customer_id en vez
    de una columna directa en `customers`). Usado por require_permission() en
    caliente (una query por request) — para resolver TODOS los permisos de
    un cliente de una sola vez (login, admin) ver resolve_permissions().
    """
    r = await db.execute(text("""
        SELECT COALESCE(cust_ov.can_view, prof_ov.can_view, pr.default_visible) AS val
        FROM permission_resources pr
        JOIN customers cu ON cu.id = :cid
        LEFT JOIN profile_permissions prof_ov
               ON prof_ov.profile_id = cu.profile_id AND prof_ov.resource_key = pr.resource_key
        LEFT JOIN profile_permissions cust_ov
               ON cust_ov.customer_id = cu.id AND cust_ov.resource_key = pr.resource_key
        WHERE pr.resource_key = :key
    """), {"cid": customer_id, "key": resource_key})
    row = r.mappings().first()
    return bool(row and row["val"])


async def resolve_permissions(db: AsyncSession, customer_id: int | None) -> dict:
    """
    Resuelve TODOS los resource_key de una sola vez — usado por login() para
    armar el objeto que el frontend cachea en localStorage (mismo criterio
    que ya usaba el login viejo con los show_*: se resuelve una vez al
    iniciar sesión, no en cada navegación — si un admin cambia un permiso a
    mitad de sesión, el cliente lo ve recién en el próximo login, igual que
    ya pasaba antes de este cambio) y por customers.py para mostrarle al
    admin el permiso YA resuelto de un cliente puntual.
    """
    rows = await db.execute(text("SELECT resource_key, default_visible FROM permission_resources"))
    result = {row["resource_key"]: bool(row["default_visible"]) for row in rows.mappings().all()}
    if not customer_id:
        return result
    # Cliente inexistente (id inválido/huérfano) — el JOIN de abajo no
    # matchea NADA y el for-loop no corrige `result`, dejando silenciosamente
    # los default_visible de la plataforma como si fueran el resuelto real.
    # has_permission() en cambio SÍ deniega (incluso su JOIN sin filas ->
    # COALESCE nunca corre -> False) para el mismo caso — sin este guard,
    # resolve_permissions() (login/get_customer) mostraría módulos como
    # disponibles que has_permission() bloquearía en cada request real.
    exists = await db.execute(text("SELECT 1 FROM customers WHERE id = :cid"), {"cid": customer_id})
    if not exists.first():
        return {k: False for k in result}
    r = await db.execute(text("""
        SELECT pr.resource_key,
               COALESCE(cust_ov.can_view, prof_ov.can_view, pr.default_visible) AS val
        FROM permission_resources pr
        JOIN customers cu ON cu.id = :cid
        LEFT JOIN profile_permissions prof_ov
               ON prof_ov.profile_id = cu.profile_id AND prof_ov.resource_key = pr.resource_key
        LEFT JOIN profile_permissions cust_ov
               ON cust_ov.customer_id = cu.id AND cust_ov.resource_key = pr.resource_key
    """), {"cid": customer_id})
    for row in r.mappings().all():
        result[row["resource_key"]] = bool(row["val"])
    return result


def require_permission(resource_key: str):
    """Factory — dependency que verifica un ítem del árbol de permisos
    granular (permission_resources/profile_permissions, ver db/schema.sql).
    Reemplaza a require_module(). Admin siempre tiene acceso."""
    async def _check(
        user=Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> dict:
        if user["role"] == "admin":
            return user
        cid = user.get("customer_id")
        if not cid:
            raise HTTPException(status_code=403, detail="Sin cliente asociado")
        if not await has_permission(db, cid, resource_key):
            raise HTTPException(status_code=403, detail="Módulo no habilitado para este cliente")
        return user
    return _check


def require_reseller_permission(resource_key: str):
    """Factory — como require_permission(), pero además exige is_reseller=1.
    Reemplaza a require_reseller_module()."""
    async def _check(
        user=Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> dict:
        if user["role"] == "admin":
            return user
        cid = user.get("customer_id")
        if not cid:
            raise HTTPException(status_code=403, detail="Sin cliente asociado")
        r = await db.execute(text("SELECT is_reseller FROM customers WHERE id = :id"), {"id": cid})
        row = r.first()
        if not row or not row[0]:
            raise HTTPException(status_code=403, detail="Esta cuenta no es un reseller")
        if not await has_permission(db, cid, resource_key):
            raise HTTPException(status_code=403, detail="Módulo no habilitado para este reseller")
        return user
    return _check


async def require_api_key(
    x_api_key: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Auth para /api/v1/* — credencial de ENTRADA, a diferencia del secreto de
    webhooks (que se reutiliza para firmar salidas): acá solo se guarda y
    compara el hash, la key en texto plano nunca se recupera de la DB.
    Devuelve una forma distinta a get_current_user() a propósito — un caller
    por API key nunca tiene `role`, es un crédito scoped a un solo customer_id.
    """
    if not x_api_key or not x_api_key.startswith("vk_live_"):
        raise HTTPException(status_code=401, detail="API key inválida o ausente")
    key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()
    r = await db.execute(text("""
        SELECT ak.id, ak.customer_id, cu.status
        FROM api_keys ak JOIN customers cu ON ak.customer_id = cu.id
        WHERE ak.key_hash = :h AND ak.revoked = 0
    """), {"h": key_hash})
    row = r.mappings().first()
    if not row or row["status"] != "active":
        raise HTTPException(status_code=401, detail="API key inválida, revocada, o cliente suspendido")
    await db.execute(text("UPDATE api_keys SET last_used_at = NOW() WHERE id = :id"), {"id": row["id"]})
    await db.commit()
    return {"customer_id": row["customer_id"], "auth_type": "api_key"}


async def require_reseller(user=Depends(require_client), db: AsyncSession = Depends(get_db)) -> dict:
    """
    Reseller no es un role distinto en `users` — es `customers.is_reseller=1`
    (flag que activa el admin a mano, mismo criterio que users.is_superadmin).

    Admin pasa este check sin más (no tiene customer_id asociado, así que un
    admin no tiene "un" reseller propio) — pero eso NO da acceso funcional a
    los datos de un reseller puntual: backend/routers/reseller.py escala todo
    por `user["customer_id"]`, que para admin es NULL, así que las queries
    scoped devuelven vacío. Ver los datos de un reseller específico como
    admin sigue siendo vía /api/admin/customers (sin scope), no este router.
    """
    if user["role"] == "admin":
        return user
    cid = user.get("customer_id")
    if not cid:
        raise HTTPException(status_code=403, detail="Sin cliente asociado")
    r = await db.execute(text("SELECT is_reseller FROM customers WHERE id = :id"), {"id": cid})
    row = r.first()
    if not row or not row[0]:
        raise HTTPException(status_code=403, detail="Esta cuenta no es un reseller")
    return user
