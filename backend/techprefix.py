# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Numeración y validación de techprefix — módulo compartido entre
routers/customers.py (admin) y routers/reseller.py. Antes estaba duplicado
palabra por palabra en ambos archivos; unificado acá al mismo tiempo que se
unificó el rango de campañas (ver next_campaign_prefix).

Rangos por tipo de entidad (todos 4 dígitos, sin overlap posible):
  1001+  cliente admin principal          (next_customer_prefix)
  2001+  reseller creado como tal desde el inicio (next_reseller_prefix)
  5000+  sub-cliente principal de reseller (next_sub_customer_prefix, sin cambios)
  7000+  prefijo de campaña, de cualquier tipo de cliente (next_campaign_prefix)

Un cliente promovido a reseller DESPUÉS de creado (make_reseller(), acción
separada) NO regenera su techprefix — ya puede tener tráfico real corriendo.
Los rangos solo reducen la *chance* de colisión; la validación real
(techprefix_conflicts, bidireccional, toda la plataforma) no depende de ellos.
"""
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def techprefix_conflicts(db: AsyncSession, techprefix: str, exclude_id: int | None = None) -> bool:
    """
    Kamailio NO compara techprefix por igualdad — hace un substr($rU, 0, len)
    == techprefix (scripts/gen_dispatcher.py::build_routes_cfg), evaluado en
    bloques if secuenciales. Dos prefijos donde uno es prefijo del otro (ej
    "100" y "1005") son strings DISTINTOS pero colisionan en producción: el
    primero que matchea en el .cfg generado gana, y le roba las llamadas al
    segundo. La validación tiene que ser bidireccional (LIKE en ambos
    sentidos), no un WHERE techprefix = :tp de igualdad exacta.

    Chequea contra `customers.techprefix` (el principal de cada cliente) Y
    `customer_prefixes.techprefix` (prefijos de campaña) de TODA la
    plataforma. `exclude_id` solo excluye la fila propia en `customers`
    (para permitir que un cliente conserve su techprefix actual al editar
    otra cosa) — nunca excluye en bloque los `customer_prefixes` del mismo
    cliente: dos prefijos de campaña del MISMO cliente también pueden
    colisionar entre sí por substring.
    """
    if not techprefix:
        return False
    cust_excl = "AND id != :xid" if exclude_id is not None else ""
    q = f"""
        SELECT 1 FROM (
            SELECT techprefix FROM customers WHERE techprefix IS NOT NULL {cust_excl}
            UNION ALL
            SELECT techprefix FROM customer_prefixes
        ) x
        WHERE :tp LIKE CONCAT(x.techprefix, '%') OR x.techprefix LIKE CONCAT(:tp, '%')
    """
    params = {"tp": techprefix}
    if exclude_id is not None:
        params["xid"] = exclude_id
    r = await db.execute(text(q), params)
    return r.first() is not None


async def assert_techprefix_free(db: AsyncSession, techprefix: str, exclude_id: int | None = None) -> None:
    if await techprefix_conflicts(db, techprefix, exclude_id):
        raise HTTPException(
            409,
            f"El prefijo técnico '{techprefix}' colisiona con otro prefijo ya asignado en la "
            "plataforma (uno es prefijo del otro — Kamailio los enrutaría/facturaría cruzados)",
        )


async def _next_free(db: AsyncSession, start: int) -> str:
    n = start
    while await techprefix_conflicts(db, str(n)):
        n += 1
    return str(n)


async def next_customer_prefix(db: AsyncSession) -> str:
    """Cliente admin principal, creado sin marcar 'es reseller' — 1001+."""
    return await _next_free(db, 1001)


async def next_reseller_prefix(db: AsyncSession) -> str:
    """Cliente admin creado directamente como reseller — 2001+."""
    return await _next_free(db, 2001)


async def next_sub_customer_prefix(db: AsyncSession) -> str:
    """Sub-cliente principal de un reseller — 5000+ (sin cambios)."""
    return await _next_free(db, 5000)


async def next_campaign_prefix(db: AsyncSession) -> str:
    """Prefijo de campaña (customer_prefixes), de cualquier tipo de cliente — 7000+ (unificado)."""
    return await _next_free(db, 7000)
