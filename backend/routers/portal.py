# la plataforma anterior — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2025 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2025 – Todos los derechos reservados.

"""Portal del cliente — solo ve sus propios datos."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import os

from auth import require_client, get_current_user, require_module
from database import get_db

router = APIRouter()


def _customer_id(user: dict) -> int:
    return user["customer_id"]


@router.get("/today")
async def today(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cid = _customer_id(user)

    stats = await db.execute(text("""
        SELECT
            COUNT(*)                            AS calls_today,
            SUM(billsec) / 60.0                 AS minutes_today,
            SUM(sessionbill)                    AS cost_today,
            SUM(disposition = 'ANSWERED') * 100.0
              / NULLIF(COUNT(*), 0)             AS asr_today
        FROM cdrs
        WHERE customer_id = :cid AND DATE(start_ts) = CURDATE()
    """), {"cid": cid})

    active = await db.execute(text("""
        SELECT
            ac.call_id, ac.src_number, ac.dst_number, ac.codec,
            TIMESTAMPDIFF(SECOND, ac.started_at, NOW()) AS duration_sec
        FROM active_calls ac
        WHERE ac.customer_id = :cid
        ORDER BY ac.started_at
    """), {"cid": cid})

    balance = await db.execute(text(
        "SELECT balance, credit_limit, currency FROM customers WHERE id=:cid"
    ), {"cid": cid})

    last5 = await db.execute(text("""
        SELECT src_number, dst_number, billsec, sessionbill, disposition, start_ts
        FROM cdrs WHERE customer_id=:cid AND DATE(start_ts)=CURDATE()
        ORDER BY start_ts DESC LIMIT 5
    """), {"cid": cid})

    s = dict(stats.mappings().first() or {})
    b = dict(balance.mappings().first() or {})

    return {
        **s,
        **b,
        "available": float(b.get("balance", 0)) - float(s.get("cost_today") or 0),
        "active_calls": active.mappings().all(),
        "last_calls":   last5.mappings().all(),
    }


CLIENT_MAX_ROWS = 200   # techo absoluto para clientes — no negociable

@router.get("/calls")
async def my_calls(
    date_from: Optional[str] = Query(None),
    date_to:   Optional[str] = Query(None),
    limit:     int           = Query(50, ge=1, le=CLIENT_MAX_ROWS),
    offset:    int           = Query(0, ge=0),
    user=Depends(require_module("show_calls")),
    db: AsyncSession = Depends(get_db),
):
    cid = _customer_id(user)
    # Hard cap: aunque el cliente manipule el parámetro, nunca supera CLIENT_MAX_ROWS
    limit = min(limit, CLIENT_MAX_ROWS)

    params = {"cid": cid, "limit": limit, "offset": offset}
    filters = ["customer_id = :cid"]

    if date_from: filters.append("DATE(start_ts) >= :date_from"); params["date_from"] = date_from
    if date_to:   filters.append("DATE(start_ts) <= :date_to");   params["date_to"]   = date_to

    where = " AND ".join(filters)
    r = await db.execute(text(f"""
        SELECT call_id, src_number, dst_number, billsec, sessionbill,
               disposition, start_ts, answer_ts, end_ts
        FROM cdrs WHERE {where}
        ORDER BY start_ts DESC LIMIT :limit OFFSET :offset
    """), params)

    # COUNT acotado a CLIENT_MAX_ROWS — evita full scan en tablas grandes
    count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}
    total_r = await db.execute(text(f"""
        SELECT COUNT(*) FROM (
            SELECT 1 FROM cdrs WHERE {where} LIMIT {CLIENT_MAX_ROWS}
        ) t
    """), count_params)

    total = total_r.scalar()
    return {
        "total":    total,
        "capped":   total >= CLIENT_MAX_ROWS,   # true = hay más registros no mostrados
        "limit":    limit,
        "offset":   offset,
        "rows":     r.mappings().all(),
    }


@router.get("/report")
async def my_report(
    month: Optional[str] = Query(None),
    user=Depends(require_module("show_reports")),
    db: AsyncSession = Depends(get_db),
):
    """Resumen mensual + desglose diario desde CDRs en vivo."""
    import datetime as _dt
    cid = _customer_id(user)
    mon = month or _dt.date.today().strftime("%Y-%m")

    r = await db.execute(text("""
        SELECT
            DATE(start_ts)                                                     AS fecha,
            SUM(disposition = 'ANSWERED')                                      AS llamadas,
            SUM(disposition != 'ANSWERED')                                     AS fallidas,
            SUM(CASE WHEN disposition = 'ANSWERED' THEN billsec ELSE 0 END)   AS segundos,
            ROUND(SUM(CASE WHEN disposition = 'ANSWERED' THEN billsec ELSE 0 END) / 60.0, 2) AS minutos,
            ROUND(SUM(sessionbill), 4)                                         AS costo,
            ROUND(
                SUM(disposition = 'ANSWERED') * 100.0
                / NULLIF(COUNT(*), 0), 1
            )                                                                  AS asr
        FROM cdrs
        WHERE customer_id = :cid
          AND DATE_FORMAT(start_ts, '%Y-%m') = :month
        GROUP BY DATE(start_ts)
        ORDER BY fecha DESC
    """), {"cid": cid, "month": mon})

    rows = [
        {
            "fecha":    str(row["fecha"]),
            "llamadas": int(row["llamadas"] or 0),
            "fallidas": int(row["fallidas"] or 0),
            "segundos": int(row["segundos"] or 0),
            "minutos":  float(row["minutos"] or 0),
            "costo":    float(row["costo"] or 0),
            "asr":      float(row["asr"] or 0),
        }
        for row in r.mappings().all()
    ]

    total_llamadas = sum(d["llamadas"] for d in rows)
    total_fallidas = sum(d["fallidas"] for d in rows)
    total_segundos = sum(d["segundos"] for d in rows)
    total_costo    = round(sum(d["costo"] for d in rows), 4)

    monthly = {
        "mes":      mon,
        "llamadas": total_llamadas,
        "segundos": total_segundos,
        "minutos":  round(total_segundos / 60.0, 2),
        "costo":    total_costo,
        "asr":      round(
            total_llamadas * 100.0 / max(total_llamadas + total_fallidas, 1), 1
        ),
    }

    return {"month": mon, "monthly": monthly, "daily": rows}


@router.get("/invoices")
async def my_invoices(
    user=Depends(require_module("show_invoices", default_allow=False)),
    db: AsyncSession = Depends(get_db),
):
    cid = _customer_id(user)
    r = await db.execute(text("""
        SELECT id, period_start, period_end, nbcall, total_minutes,
               subtotal, tax_amount, total, currency, status, created_at
        FROM invoices WHERE customer_id = :cid ORDER BY created_at DESC
    """), {"cid": cid})
    return r.mappings().all()


@router.get("/trunk-guide")
async def trunk_guide(
    user=Depends(require_module("show_trunk_guide")),
    db: AsyncSession = Depends(get_db),
):
    """Manual de trunk Asterisk personalizado con datos del cliente."""
    cid = _customer_id(user)
    r = await db.execute(text(
        "SELECT name, techprefix, currency FROM customers WHERE id=:cid"
    ), {"cid": cid})
    customer = dict(r.mappings().first() or {})

    public_ip = os.getenv("PUBLIC_IP", "")
    domain    = os.getenv("DOMAIN", "")

    return {
        "customer":  customer,
        "sbc_host":  public_ip,
        "sbc_port":  5060,
        "sbc_domain": domain,
        "prefix":    customer.get("techprefix", ""),
        "sip_conf": f"""[kaplabilling-trunk]
type=peer
host={public_ip}
port=5060
insecure=port,invite
context=from-kaplabilling
disallow=all
allow=ulaw,alaw,g729""",
        "dialplan": f"""[kaplabilling-outbound]
; Marcar 51912345678 → tu Asterisk envía: {customer.get('techprefix', 'XXXX')}51912345678
exten => _X.,1,Dial(SIP/{customer.get('techprefix', '')}${{EXTEN}}@kaplabilling-trunk)
 same  => n,Hangup()""",
    }
