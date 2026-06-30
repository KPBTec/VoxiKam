# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from auth import require_admin, require_client, require_module
from database import get_db

router = APIRouter()


def _pct(num, den):
    if not den:
        return 0.0
    return round(num / den * 100, 1)


def _enrich(row: dict) -> dict:
    ans  = row["answered"] or 0
    tot  = row["total"]    or 0
    shrt = row["short_calls"] or 0
    asr  = _pct(ans, tot)
    return {
        **row,
        "asr":         asr,                     # % contestadas
        "short_pct":   _pct(shrt, ans),          # % < 5s del contestado (buzón)
        "asr_color":   "green" if asr >= 50 else ("yellow" if asr >= 30 else "red"),
    }


async def _quality_from_cdrs(db, day: str, customer_id: Optional[int] = None) -> list[dict]:
    """
    Calcula calidad por hora directamente desde cdrs + cdrs_failed.
    Usado para horas que no están en traffic_quality_hourly todavía.
    """
    cid_filter = "AND c.customer_id = :cid" if customer_id else ""
    params: dict = {"day": day}
    if customer_id:
        params["cid"] = customer_id

    answered_sql = f"""
        SELECT HOUR(c.start_ts) AS h, c.customer_id,
               cu.name AS customer_name,
               COUNT(*) AS answered,
               SUM(c.billsec < 5) AS short_calls
        FROM cdrs c
        JOIN customers cu ON c.customer_id = cu.id
        WHERE DATE(c.start_ts) = :day AND c.customer_id IS NOT NULL {cid_filter}
        GROUP BY h, c.customer_id
    """
    failed_sql = f"""
        SELECT HOUR(f.start_ts) AS h, f.customer_id,
               SUM(f.sip_code = 487) AS c_487,
               SUM(f.sip_code = 486) AS c_486,
               SUM(f.sip_code = 404) AS c_404,
               SUM(f.sip_code = 503) AS c_503,
               SUM(f.sip_code NOT IN (487,486,404,503)) AS c_other,
               COUNT(*) AS failed_total
        FROM cdrs_failed f
        WHERE DATE(f.start_ts) = :day AND f.customer_id IS NOT NULL {cid_filter}
        GROUP BY h, f.customer_id
    """
    ra = await db.execute(text(answered_sql), params)
    rf = await db.execute(text(failed_sql),   params)

    answered_map: dict = {}   # (h, cid) → {answered, short_calls, customer_name}
    for row in ra.mappings().all():
        answered_map[(row["h"], row["customer_id"])] = dict(row)

    failed_map: dict = {}     # (h, cid) → failed fields
    for row in rf.mappings().all():
        failed_map[(row["h"], row["customer_id"])] = dict(row)

    all_keys = set(answered_map) | set(failed_map)
    rows = []
    for (h, cid) in sorted(all_keys, key=lambda x: (-x[0], x[1])):
        a = answered_map.get((h, cid), {})
        f = failed_map.get((h, cid),   {})
        ans   = a.get("answered",    0) or 0
        shrt  = a.get("short_calls", 0) or 0
        ftot  = f.get("failed_total",0) or 0
        total = ans + ftot
        rows.append({
            "ts_hour":       f"{h:02d}:00",
            "customer_id":   cid,
            "customer_name": a.get("customer_name", ""),
            "total":         total,
            "answered":      ans,
            "short_calls":   shrt,
            "c_487":         f.get("c_487",  0) or 0,
            "c_486":         f.get("c_486",  0) or 0,
            "c_404":         f.get("c_404",  0) or 0,
            "c_503":         f.get("c_503",  0) or 0,
            "c_other":       f.get("c_other",0) or 0,
        })
    return rows


@router.get("/admin")
async def quality_admin(
    date:        Optional[str] = Query(None, description="YYYY-MM-DD, default hoy"),
    customer_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """
    ASR Dashboard admin — resumen por hora y cliente.
    Consulta CDRs directamente (siempre actualizado, sin depender solo del cron).
    """
    from datetime import date as date_type
    today = date_type.today().isoformat()
    day   = date or today

    rows   = await _quality_from_cdrs(db, day, customer_id)
    totals_map: dict = {}
    for r in rows:
        cid  = r["customer_id"]
        name = r["customer_name"]
        key  = (cid, name)
        if key not in totals_map:
            totals_map[key] = {"customer_id": cid, "customer_name": name,
                               "total":0,"answered":0,"short_calls":0,
                               "c_487":0,"c_486":0,"c_404":0,"c_503":0,"c_other":0}
        for f in ("total","answered","short_calls","c_487","c_486","c_404","c_503","c_other"):
            totals_map[key][f] += r[f]

    totals = [_enrich(v) for v in sorted(totals_map.values(),
                                          key=lambda x: -x["total"])]
    return {"rows": [_enrich(r) for r in rows], "totals": totals}


@router.get("/my")
async def quality_my(
    date: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    auth=Depends(require_module("show_quality")),
):
    """
    ASR Dashboard cliente — solo su propio tráfico.
    """
    customer_id = auth.get("customer_id")
    if not customer_id:
        return {"rows": [], "totals": []}

    params: dict = {"cid": customer_id}
    date_filter = "DATE(q.ts_hour) = :day" if date else "DATE(q.ts_hour) = CURDATE()"
    if date:
        params["day"] = date

    r = await db.execute(text(f"""
        SELECT
            q.ts_hour,
            q.total,
            q.answered,
            q.short_calls,
            q.c_487,
            q.c_486,
            q.c_404,
            q.c_503,
            q.c_other
        FROM traffic_quality_hourly q
        WHERE q.customer_id = :cid AND {date_filter}
        ORDER BY q.ts_hour DESC
    """), params)

    rows = []
    for row in r.mappings().all():
        d = dict(row)
        d["ts_hour"] = d["ts_hour"].strftime("%H:%M") if d["ts_hour"] else ""
        rows.append(_enrich(d))

    total_row = {
        "total":       sum(r["total"]       for r in rows),
        "answered":    sum(r["answered"]    for r in rows),
        "short_calls": sum(r["short_calls"] for r in rows),
        "c_487":       sum(r["c_487"]       for r in rows),
        "c_486":       sum(r["c_486"]       for r in rows),
        "c_404":       sum(r["c_404"]       for r in rows),
        "c_503":       sum(r["c_503"]       for r in rows),
        "c_other":     sum(r["c_other"]     for r in rows),
    }

    return {"rows": rows, "total_day": _enrich(total_row)}
