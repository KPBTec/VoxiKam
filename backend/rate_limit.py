# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
rate_limit.py — límite de tasa compartido entre workers, respaldado en
MariaDB (tabla rate_limit_counters, migración 2.56.2).

Re-auditoría v2.56.0 (hallazgo alto): tanto `middleware/security.py::_counters`
(por IP) como `routers/auth.py::_account_fail_counters` (por cuenta) eran
`dict` en memoria — con `uvicorn --workers N` cada proceso mantiene su propio
contador, así que el límite real efectivo quedaba fragmentado en un factor
~N. El equipo ya había diagnosticado y corregido esta MISMA clase de bug para
`cors_state.ALLOWED_ORIGINS` (ver `main.py::_cors_origin_syncer`), pero no
para estos dos rate limiters.

Diseño "fixed window" (bucket = floor(unix_ts / window) * window), no
sliding window real: un sliding window real (fila por intento, con
DELETE+SELECT+INSERT para podar+contar+agregar) son 3 round-trips a la DB
por request — demasiado caro para un middleware que corre en casi todo el
tráfico. El fixed window es UN solo `INSERT ... ON DUPLICATE KEY UPDATE
... RETURNING count`, atómico, probado contra MariaDB 11.8.6 real. Trade-off
aceptado: un cliente que manda ráfagas justo en el borde entre dos ventanas
puede colar hasta ~2x el límite nominal en una ventana muy corta — el mismo
trade-off que usan la mayoría de los rate limiters de producción con este
patrón, y muchísimo más barato que pagar 3 queries por request para
eliminarlo.

La fila de cada (key, window) vieja se auto-purga sola con el tiempo (ver
`main.py::_rate_limit_purger`) — no crece sin límite ni por processo
(estado compartido) ni por cantidad de keys distintas vistas (purga por TTL).
"""
import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def increment(db: AsyncSession, key: str, window_seconds: int) -> int:
    """Incrementa el contador de `key` para la ventana actual y devuelve el
    nuevo valor. SIEMPRE incrementa — el caller decide qué contar como un
    "intento" (ver peek_count() para chequear sin incrementar)."""
    bucket = (int(time.time()) // window_seconds) * window_seconds
    result = await db.execute(text("""
        INSERT INTO rate_limit_counters (rl_key, window_start, count)
        VALUES (:key, :bucket, 1)
        ON DUPLICATE KEY UPDATE count = count + 1
        RETURNING count
    """), {"key": key, "bucket": bucket})
    await db.commit()
    return result.scalar()


async def peek_count(db: AsyncSession, key: str, window_seconds: int) -> int:
    """Lee el contador actual de `key` SIN incrementarlo — para el caso de
    "rechazar antes de intentar" (ej. routers/auth.py: rechazar un login por
    cuenta ya bloqueada sin gastar una query de más buscando al usuario)."""
    bucket = (int(time.time()) // window_seconds) * window_seconds
    result = await db.execute(text(
        "SELECT count FROM rate_limit_counters WHERE rl_key = :key AND window_start = :bucket"
    ), {"key": key, "bucket": bucket})
    row = result.first()
    return row[0] if row else 0


async def is_rate_limited(db: AsyncSession, key: str, max_count: int, window_seconds: int) -> bool:
    """Incrementa y devuelve True si superó `max_count` — para el caso
    "cada request cuenta, sin importar si termina en éxito o error" (ej.
    middleware/security.py: rate limit genérico por IP)."""
    count = await increment(db, key, window_seconds)
    return count > max_count


async def purge_expired(db: AsyncSession, max_window_seconds: int = 3600) -> int:
    """
    Borra filas de ventanas que ya cerraron hace más de `max_window_seconds`
    — llamado periódicamente desde main.py. El valor por defecto (1h) cubre
    con margen la ventana más larga configurada hoy (300s en middleware/
    security.py) sin tener que importar las constantes de cada caller acá.
    """
    cutoff = int(time.time()) - max_window_seconds
    result = await db.execute(text(
        "DELETE FROM rate_limit_counters WHERE window_start < :cutoff"
    ), {"cutoff": cutoff})
    await db.commit()
    return result.rowcount
