# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Cliente ClickHouse compartido para sip_traces — mismo shape que database.py
(engine/pool creado una vez, inyectado por dependency) para que los routers
sigan el mismo idiom con Depends(). Solo sip_traces vive acá; todo lo demás
sigue en MariaDB vía database.py.
"""
import asyncio
import os
from urllib.parse import urlparse

import clickhouse_connect
from clickhouse_connect.driver.asyncclient import AsyncClient
from dotenv import load_dotenv

load_dotenv()

_u = urlparse(os.getenv("CLICKHOUSE_URL", ""))
_CH = dict(
    host=_u.hostname or "127.0.0.1",
    port=_u.port or 8123,
    username=_u.username or "voxikam",
    password=_u.password or "",
    database=(_u.path or "/sip_platform").lstrip("/"),
)

_client: AsyncClient | None = None
_client_lock = asyncio.Lock()


async def get_ch() -> AsyncClient:
    """
    Doble-check con lock — mismo patrón que hep_listener.py::_get_pool(), para
    que dos requests concurrentes en el arranque en frío no terminen creando
    dos clientes (uno quedaría huérfano sin cerrarse nunca).
    """
    global _client
    if _client is None:
        async with _client_lock:
            if _client is None:
                _client = await clickhouse_connect.get_async_client(**_CH)
    return _client
