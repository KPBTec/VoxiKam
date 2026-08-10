# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from auth import require_reseller_permission
from database import get_db

from ._shared import _my_cid

router = APIRouter()


# ── Dashboard de margen ──────────────────────────────────────────────────────

@router.get("/dashboard")
async def dashboard(user=Depends(require_reseller_permission("reseller_dashboard")), db: AsyncSession = Depends(get_db)):
    """
    Margen del reseller = sessionbill - reseller_cost, por sub-cliente y total
    del mes en curso. reseller_cost solo se calcula para CDRs de clientes con
    parent_customer_id — ver backend/routers/cdrs.py::ingest_cdr().

    Días completados del mes → cdr_summary_day_reseller (agregado nocturno,
    mismo filtro exacto que antes se corría en vivo — ver cron_summary.py y el
    comentario en db/schema.sql sobre por qué es tabla aparte). Hoy → cdrs en
    vivo, acotado a su propia partición diaria — mismo patrón híbrido que
    reports.py::report_month() (admin) y portal.py::my_report() (cliente).
    Antes esto escaneaba el mes completo en vivo en cada carga del dashboard,
    cada vez más pesado a medida que avanza el mes.

    Excluye CDRs con reseller_cost IS NULL (no COALESCE a 0): si tratáramos el
    NULL como costo cero, esas llamadas mostrarían el 100% del sessionbill
    como margen — un número falso, no "sin dato". Esto puede pasar con CDRs
    viejos de un cliente que se volvió sub-cliente de un reseller DESPUÉS de
    tener historial (ese historial nunca tuvo reseller_cost calculado).
    """
    import datetime as _dt
    my_cid = _my_cid(user)
    r = await db.execute(text("""
        SELECT cu.id AS customer_id, cu.name AS customer_name,
               SUM(t.nbcall)                              AS calls,
               ROUND(SUM(t.revenue), 4)                    AS revenue,
               ROUND(SUM(t.cost), 4)                        AS cost,
               ROUND(SUM(t.revenue - t.cost), 4)           AS margin
        FROM (
            /* Días completados del mes — tabla de resumen, ya acotado a mis sub-clientes */
            SELECT sd.customer_id, sd.nbcall, sd.revenue, sd.cost
            FROM cdr_summary_day_reseller sd
            JOIN customers subc ON subc.id = sd.customer_id AND subc.parent_customer_id = :pid
            WHERE LEFT(sd.summary_date, 7) = :month
              AND sd.summary_date < CURDATE()

            UNION ALL

            /* Hoy en vivo, mismo alcance */
            SELECT c.customer_id,
                   COUNT(*)              AS nbcall,
                   SUM(c.sessionbill)    AS revenue,
                   SUM(c.reseller_cost)  AS cost
            FROM cdrs c
            JOIN customers subc ON subc.id = c.customer_id AND subc.parent_customer_id = :pid
            WHERE c.disposition = 'ANSWERED'
              AND c.reseller_cost IS NOT NULL
              AND c.start_ts >= CURDATE() AND c.start_ts < CURDATE() + INTERVAL 1 DAY
            GROUP BY c.customer_id
        ) t
        JOIN customers cu ON t.customer_id = cu.id
        GROUP BY cu.id, cu.name
        ORDER BY margin DESC
    """), {"pid": my_cid, "month": _dt.date.today().strftime("%Y-%m")})
    rows = r.mappings().all()
    return {
        "month": _dt.date.today().strftime("%Y-%m"),
        "by_customer": rows,
        "total_margin": round(sum(float(row["margin"] or 0) for row in rows), 4),
    }
