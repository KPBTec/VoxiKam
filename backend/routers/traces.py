# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from auth import require_admin
from database import get_db

router = APIRouter()


def _classify_query(q: str) -> tuple[str, str]:
    """
    Devuelve (cond_sql, q_valor) según el tipo de búsqueda:
    - Call-ID   → exact match en call_id          (usa idx_call_id, instantáneo)
    - Teléfono  → trailing wildcard en from/to_uri (puede usar índice)
    - Vacío     → sin filtro (lista todas del día)
    - Otro      → LIKE '%q%' fallback (lento, pero cubre casos raros)
    """
    q = q.strip()
    if not q:
        return ("", "")

    # Call-ID: hexadecimal/alfanumérico largo, sin @, sin espacios (>= 20 chars)
    if len(q) >= 20 and "@" not in q and " " not in q:
        return ("AND call_id = :q", q)

    # Número de teléfono: solo dígitos, +, -, máx 20 chars
    stripped = q.lstrip("+").replace("-", "").replace(" ", "")
    if stripped.isdigit() and len(stripped) >= 4:
        return ("AND (from_uri LIKE :q OR to_uri LIKE :q)", f"{q}%")

    # Fallback: LIKE bilateral (slow path — avisa con LIMIT bajo)
    return ("AND (call_id LIKE :q OR from_uri LIKE :q OR to_uri LIKE :q)", f"%{q}%")


@router.get("/calls")
async def search_calls(
    date: str  = Query(...,  description="Fecha YYYY-MM-DD"),
    q:    str  = Query("",  description="Búsqueda: Call-ID completo o número de teléfono"),
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
):
    """
    Lista de llamadas con traza SIP para una fecha.
    Detección automática del tipo de búsqueda:
    - Call-ID >= 20 chars sin @ → exact match (índice, <50ms)
    - Número de teléfono → trailing LIKE (índice parcial)
    - Vacío → lista todas las llamadas del día
    """
    cond, q_val = _classify_query(q)
    params: dict = {"date_from": date, "lim": limit}
    if q_val:
        params["q"] = q_val

    rows = await db.execute(
        text(f"""
            SELECT
                call_id,
                MIN(captured_at)                                     AS first_ts,
                MAX(captured_at)                                     AS last_ts,
                COUNT(*)                                             AS msg_count,
                MAX(CASE WHEN sip_method='INVITE' THEN 1 ELSE 0 END) AS has_invite,
                MAX(CASE WHEN sip_status IS NOT NULL
                         THEN sip_status ELSE 0 END)                AS final_status,
                MAX(from_uri)                                        AS from_uri,
                MAX(to_uri)                                          AS to_uri,
                GROUP_CONCAT(
                    COALESCE(sip_method, sip_status)
                    ORDER BY captured_at, id
                    SEPARATOR ','
                )                                                    AS method_seq
            FROM sip_traces
            WHERE captured_at >= :date_from
              AND captured_at <  DATE_ADD(:date_from, INTERVAL 1 DAY)
              {cond}
            GROUP BY call_id
            ORDER BY first_ts DESC
            LIMIT :lim
        """),
        params,
    )
    calls = []
    for r in rows.mappings().all():
        calls.append({
            "call_id":      r["call_id"],
            "first_ts":     r["first_ts"].isoformat() if r["first_ts"] else None,
            "last_ts":      r["last_ts"].isoformat()  if r["last_ts"]  else None,
            "msg_count":    r["msg_count"],
            "has_invite":   bool(r["has_invite"]),
            "final_status": r["final_status"] or None,
            "from_uri":     r["from_uri"],
            "to_uri":       r["to_uri"],
            "methods":      (r["method_seq"] or "").split(","),
        })
    return {"date": date, "count": len(calls), "calls": calls}


@router.get("/stream")
async def get_stream(
    since_id: int = Query(0,   description="Devuelve mensajes con id > since_id"),
    limit:    int = Query(200, le=500),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
):
    """
    Feed de todos los mensajes SIP recientes — para la vista live.
    Llamar con `since_id` del último mensaje recibido para obtener solo los nuevos.
    """
    rows = await db.execute(
        text("""
            SELECT id, captured_at, call_id, src_ip, src_port, dst_ip, dst_port,
                   sip_method, sip_status, from_uri, to_uri, cseq, user_agent, reason
            FROM sip_traces
            WHERE id > :sid
              AND captured_at >= CURDATE()
            ORDER BY id DESC
            LIMIT :lim
        """),
        {"sid": since_id, "lim": limit},
    )
    msgs = []
    for r in rows.mappings().all():
        msgs.append({
            "id":         r["id"],
            "ts":         r["captured_at"].isoformat() if r["captured_at"] else None,
            "call_id":    r["call_id"],
            "src_ip":     r["src_ip"],
            "src_port":   r["src_port"],
            "dst_ip":     r["dst_ip"],
            "dst_port":   r["dst_port"],
            "method":     r["sip_method"],
            "status":     r["sip_status"],
            "from_uri":   r["from_uri"],
            "to_uri":     r["to_uri"],
            "cseq":       r["cseq"],
            "user_agent": r["user_agent"],
            "reason":     r["reason"],
        })
    # Devolver en orden cronológico (más antiguo primero)
    msgs.reverse()
    return {"count": len(msgs), "messages": msgs}


@router.get("")
async def get_trace(
    call_id: str = Query(..., description="Call-ID SIP exacto"),
    since_id: int = Query(0, description="Devuelve solo mensajes con id > since_id (para polling live)"),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
):
    """
    Todos los mensajes SIP de una llamada en orden cronológico.
    Usar `since_id` para polling incremental en modo en vivo.
    """
    rows = await db.execute(
        text("""
            SELECT id, captured_at, src_ip, src_port, dst_ip, dst_port,
                   sip_method, sip_status, from_uri, to_uri, raw_message
            FROM sip_traces
            WHERE call_id = :cid AND id > :sid
            ORDER BY captured_at, id
        """),
        {"cid": call_id, "sid": since_id},
    )
    msgs = []
    for r in rows.mappings().all():
        msgs.append({
            "id":       r["id"],
            "ts":       r["captured_at"].isoformat() if r["captured_at"] else None,
            "src_ip":   r["src_ip"],
            "src_port": r["src_port"],
            "dst_ip":   r["dst_ip"],
            "dst_port": r["dst_port"],
            "method":   r["sip_method"],
            "status":   r["sip_status"],
            "from_uri": r["from_uri"],
            "to_uri":   r["to_uri"],
            "raw":      r["raw_message"],
        })
    return {"call_id": call_id, "count": len(msgs), "messages": msgs}
