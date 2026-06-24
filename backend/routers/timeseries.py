# la plataforma anterior — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

from datetime import datetime, timedelta, date as date_type
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from auth import require_admin, get_current_user
from database import get_db

router = APIRouter()

COLORS = ["#6366f1","#22c55e","#f59e0b","#ec4899","#14b8a6","#f97316","#8b5cf6","#06b6d4","#ef4444","#a3e635"]


def _build_series(rows, label_key: str, group_key: str, count_key: str, all_labels: list[str]) -> list[dict]:
    groups: dict[str, dict[str, int]] = {}
    for r in rows:
        name  = r[group_key] or "Sin nombre"
        label = r[label_key]
        count = int(r[count_key] or 0)
        groups.setdefault(name, {})[label] = count

    series = []
    for i, (name, data) in enumerate(groups.items()):
        series.append({
            "name":  name,
            "color": COLORS[i % len(COLORS)],
            "data":  [data.get(lb, 0) for lb in all_labels],
        })
    return series


def _minute_labels(hours: int) -> list[str]:
    now     = datetime.now().replace(second=0, microsecond=0)
    start   = now - timedelta(hours=hours)
    labels, cur = [], start
    while cur <= now:
        labels.append(cur.strftime("%H:%M"))
        cur += timedelta(minutes=1)
    return labels


def _hour_labels_day(day: date_type) -> list[str]:
    return [f"{h:02d}:00" for h in range(24)]


async def _query_live(db, hours: int, customer_id: Optional[int] = None):
    """
    Snapshot por minuto desde calls_timeseries.
    Usa NOW() de MySQL — evita desalineación de zona horaria entre Python y DB.
    """
    cond = "AND ct.customer_id = :cid" if customer_id else ""
    sql = f"""
        SELECT
            DATE_FORMAT(ct.ts, '%H:%i') AS lbl,
            cu.name                      AS customer_name,
            ca.name                      AS carrier_name,
            SUM(ct.answered_count)       AS calls
        FROM calls_timeseries ct
        LEFT JOIN customers cu ON ct.customer_id = cu.id
        LEFT JOIN carriers  ca ON ct.carrier_id  = ca.id
        WHERE ct.ts >= NOW() - INTERVAL :hours HOUR {cond}
        GROUP BY ct.ts, ct.customer_id, ct.carrier_id
        ORDER BY ct.ts ASC
    """
    params: dict = {"hours": hours}
    if customer_id:
        params["cid"] = customer_id
    r = await db.execute(text(sql), params)
    return r.mappings().all()


async def _query_day(db, day: date_type, customer_id: Optional[int] = None):
    """CDRs agrupados por hora para un día completo."""
    cond = "AND c.customer_id = :cid" if customer_id else ""
    sql = f"""
        SELECT
            DATE_FORMAT(c.start_ts, '%H:00') AS lbl,
            cu.name                           AS customer_name,
            ca.name                           AS carrier_name,
            COUNT(*)                          AS calls
        FROM cdrs c
        LEFT JOIN customers cu ON c.customer_id = cu.id
        LEFT JOIN carriers  ca ON c.carrier_id  = ca.id
        WHERE DATE(c.start_ts) = :day {cond}
        GROUP BY HOUR(c.start_ts), c.customer_id, c.carrier_id
        ORDER BY HOUR(c.start_ts) ASC
    """
    params: dict = {"day": day}
    if customer_id:
        params["cid"] = customer_id
    r = await db.execute(text(sql), params)
    return r.mappings().all()


@router.get("/admin")
async def admin_timeseries(
    range: int           = Query(1, ge=1, le=12),
    date:  Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    if date:
        day    = date_type.fromisoformat(date)
        labels = _hour_labels_day(day)
        rows   = await _query_day(db, day)
    else:
        labels = _minute_labels(range)
        rows   = await _query_live(db, range)

    return {
        "labels":      labels,
        "by_customer": _build_series(rows, "lbl", "customer_name", "calls", labels),
        "by_carrier":  _build_series(rows, "lbl", "carrier_name",  "calls", labels),
    }


@router.get("/my")
async def client_timeseries(
    range: int           = Query(1, ge=1, le=12),
    date:  Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    customer_id = user["customer_id"]

    if date:
        day    = date_type.fromisoformat(date)
        labels = _hour_labels_day(day)
        rows   = await _query_day(db, day, customer_id)
    else:
        labels = _minute_labels(range)
        rows   = await _query_live(db, range, customer_id)

    return {
        "labels":     labels,
        "by_carrier": _build_series(rows, "lbl", "carrier_name", "calls", labels),
    }
