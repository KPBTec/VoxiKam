# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from auth import require_admin
from database import get_db

router = APIRouter()

@router.get("/day")
async def report_day(
    date: str,
    customer_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """
    Para un día específico:
    - Si es hoy  → agrega desde cdrs en vivo.
    - Si es ayer o antes → lee de cdr_summary_day (rápido).
    """
    from datetime import date as _date
    params: dict = {"date": date}
    cid_filter = "AND sd.customer_id = :cid" if customer_id else ""
    if customer_id:
        params["cid"] = customer_id

    is_today = date == str(_date.today())

    if is_today:
        cid_live = "AND cd.customer_id = :cid" if customer_id else ""
        r = await db.execute(text(f"""
            SELECT c.id AS customer_id, c.name AS customer_name,
                   ca.id AS carrier_id, ca.name AS carrier_name,
                   SUM(cd.disposition = 'ANSWERED')                          AS nbcall,
                   SUM(cd.disposition != 'ANSWERED')                         AS nbcall_fail,
                   SUM(CASE WHEN cd.disposition='ANSWERED' THEN cd.billsec ELSE 0 END) AS sessiontime,
                   ROUND(SUM(cd.buycost), 4)                                 AS buycost,
                   ROUND(SUM(cd.sessionbill), 4)                             AS sessionbill,
                   ROUND(SUM(cd.sessionbill - cd.buycost), 4)               AS lucro,
                   ROUND(SUM(cd.disposition='ANSWERED') * 100.0
                         / NULLIF(COUNT(*), 0), 2)                           AS asr,
                   ROUND(AVG(CASE WHEN cd.disposition='ANSWERED'
                         THEN cd.billsec END), 2)                            AS aloc
            FROM cdrs cd
            JOIN customers c  ON cd.customer_id = c.id
            LEFT JOIN carriers ca ON cd.carrier_id = ca.id
            WHERE cd.customer_id IS NOT NULL
              AND DATE(cd.start_ts) = :date {cid_live}
            GROUP BY c.id, c.name, ca.id, ca.name
            ORDER BY sessionbill DESC
        """), params)
    else:
        r = await db.execute(text(f"""
            SELECT c.id AS customer_id, c.name AS customer_name,
                   ca.id AS carrier_id, ca.name AS carrier_name,
                   SUM(sd.nbcall)                                             AS nbcall,
                   SUM(sd.nbcall_fail)                                        AS nbcall_fail,
                   SUM(sd.sessiontime)                                        AS sessiontime,
                   ROUND(SUM(sd.buycost), 4)                                  AS buycost,
                   ROUND(SUM(sd.sessionbill), 4)                              AS sessionbill,
                   ROUND(SUM(sd.lucro), 4)                                    AS lucro,
                   ROUND(SUM(sd.nbcall) * 100.0
                         / NULLIF(SUM(sd.nbcall) + SUM(sd.nbcall_fail), 0), 2) AS asr,
                   ROUND(SUM(sd.sessiontime) * 1.0
                         / NULLIF(SUM(sd.nbcall), 0), 2)                     AS aloc
            FROM cdr_summary_day sd
            JOIN customers c  ON sd.customer_id = c.id
            LEFT JOIN carriers ca ON sd.carrier_id = ca.id
            WHERE sd.summary_date = :date {cid_filter}
            GROUP BY c.id, c.name, ca.id, ca.name
            ORDER BY sessionbill DESC
        """), params)

    return [dict(row) for row in r.mappings().all()]


@router.get("/month")
async def report_month(
    month: str,
    customer_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """
    Para un mes:
    - Días completados → cdr_summary_day (veloz).
    - Hoy (si es el mes actual) → cdrs en vivo via UNION.
    Agrupa por customer + carrier.
    """
    from datetime import date as _date
    params: dict = {"month": month}
    cid_filter = "AND customer_id = :cid" if customer_id else ""
    if customer_id:
        params["cid"] = customer_id

    r = await db.execute(text(f"""
        SELECT c.id AS customer_id, c.name AS customer_name,
               ca.id AS carrier_id, ca.name AS carrier_name,
               SUM(t.nbcall)       AS nbcall,
               SUM(t.nbcall_fail)  AS nbcall_fail,
               SUM(t.sessiontime)  AS sessiontime,
               ROUND(SUM(t.buycost), 4)     AS buycost,
               ROUND(SUM(t.sessionbill), 4) AS sessionbill,
               ROUND(SUM(t.lucro), 4)       AS lucro,
               ROUND(SUM(t.nbcall) * 100.0
                     / NULLIF(SUM(t.nbcall) + SUM(t.nbcall_fail), 0), 2) AS asr,
               ROUND(SUM(t.sessiontime) * 1.0
                     / NULLIF(SUM(t.nbcall), 0), 2)                      AS aloc
        FROM (
            /* Días anteriores al de hoy — tabla de resumen */
            SELECT customer_id, carrier_id,
                   nbcall, nbcall_fail, sessiontime,
                   buycost, sessionbill, lucro
            FROM   cdr_summary_day
            WHERE  LEFT(summary_date, 7) = :month
              AND  summary_date < CURDATE()
              {cid_filter}

            UNION ALL

            /* Hoy en vivo (solo si pertenece al mes pedido) */
            SELECT customer_id, carrier_id,
                   SUM(disposition = 'ANSWERED')                             AS nbcall,
                   SUM(disposition != 'ANSWERED')                            AS nbcall_fail,
                   SUM(CASE WHEN disposition='ANSWERED' THEN billsec ELSE 0 END) AS sessiontime,
                   SUM(buycost)                                              AS buycost,
                   SUM(sessionbill)                                          AS sessionbill,
                   SUM(sessionbill - buycost)                                AS lucro
            FROM   cdrs
            WHERE  DATE_FORMAT(start_ts, '%Y-%m') = :month
              AND  DATE(start_ts) = CURDATE()
              AND  customer_id IS NOT NULL
              {cid_filter.replace('customer_id', 'cdrs.customer_id') if customer_id else ''}
            GROUP  BY customer_id, carrier_id
        ) t
        JOIN customers c  ON t.customer_id = c.id
        LEFT JOIN carriers ca ON t.carrier_id = ca.id
        GROUP BY c.id, c.name, ca.id, ca.name
        ORDER BY sessionbill DESC
    """), params)

    return [dict(row) for row in r.mappings().all()]


@router.get("/dashboard")
async def dashboard(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    """KPIs de hoy para el dashboard admin."""
    today = await db.execute(text("""
        SELECT
            COUNT(*)                              AS calls_today,
            SUM(billsec)                          AS seconds_today,
            SUM(buycost)                          AS buycost_today,
            SUM(sessionbill)                      AS sessionbill_today,
            SUM(sessionbill - buycost)            AS lucro_today,
            SUM(disposition = 'ANSWERED') * 100.0
              / NULLIF(COUNT(*), 0)               AS asr_today
        FROM cdrs WHERE DATE(start_ts) = CURDATE()
    """))
    active = await db.execute(text("SELECT COUNT(*) FROM active_calls"))
    return {**dict(today.mappings().first()), "active_calls": active.scalar()}
