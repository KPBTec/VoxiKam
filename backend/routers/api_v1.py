# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
API pública para clientes — autenticada con API key (header X-API-Key), no
JWT. Wrapper delgado sobre la misma lógica de consulta que ya usa el portal
web (backend/routers/portal.py::_get_balance/_get_calls) — se reusa la
función, no se copia la query, para que las dos superficies (dashboard y API)
nunca diverjan en el cálculo.

Versionado a propósito (/api/v1, no /api/my) — una integración externa de un
cliente no debe romperse si el portal web cambia de forma un día.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from auth import require_api_key
from database import get_db
from routers.portal import CLIENT_MAX_ROWS, _get_balance, _get_calls

router = APIRouter()


@router.get("/balance")
async def balance(
    auth=Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
):
    return await _get_balance(db, auth["customer_id"])


@router.get("/cdrs")
async def cdrs(
    date_from: Optional[str] = Query(None),
    date_to:   Optional[str] = Query(None),
    limit:     int           = Query(50, ge=1, le=CLIENT_MAX_ROWS),
    offset:    int           = Query(0, ge=0),
    auth=Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
):
    return await _get_calls(db, auth["customer_id"], date_from, date_to, limit, offset)
