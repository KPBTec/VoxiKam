# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import time as _time

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from auth import require_admin
from database import get_db

router = APIRouter()
log = logging.getLogger("live")

_SNAPSHOT_FILE = Path("/var/lib/voxikam/live_snapshot.json")


def _read_snapshot() -> dict:
    try:
        return json.loads(_SNAPSHOT_FILE.read_text())
    except Exception:
        return {}


async def _prefix_map(db) -> dict[str, dict]:
    """techprefix → {id, name}"""
    r = await db.execute(text(
        "SELECT id, techprefix, name FROM customers "
        "WHERE techprefix IS NOT NULL AND techprefix != '' "
        "ORDER BY LENGTH(techprefix) DESC"
    ))
    return {row["techprefix"]: {"id": row["id"], "name": row["name"]}
            for row in r.mappings().all()}


def _resolve(prefijo: str, prefix_map: dict) -> dict | None:
    return prefix_map.get(prefijo)


@router.get("")
async def live_calls(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    snap    = _read_snapshot()
    resumen = snap.get("resumen", {})
    por_pfx = snap.get("resumen_por_prefijo", [])

    ongoing    = resumen.get("llamadas_activas", 0)
    timbrando  = resumen.get("timbrando", 0)
    total      = resumen.get("total", 0)

    # Zombie cleanup silencioso
    total_db = (await db.execute(text("SELECT COUNT(*) FROM active_calls"))).scalar() or 0
    if total_db > ongoing + 5:
        deleted = await db.execute(text("""
            DELETE FROM active_calls
            WHERE call_id NOT IN (
                SELECT call_id FROM (
                    SELECT call_id FROM active_calls
                    ORDER BY started_at DESC LIMIT :lim
                ) sub
            )
        """), {"lim": max(ongoing, 0)})
        await db.commit()
        if deleted.rowcount:
            log.warning("Auto-sync: %d zombie(s) eliminados", deleted.rowcount)

    # Enriquecer resumen_por_prefijo con nombre de cliente
    pmap = await _prefix_map(db)
    by_customer = []
    for entry in por_pfx:
        pfx  = entry.get("prefijo", "")
        cust = _resolve(pfx, pmap)
        by_customer.append({
            "prefijo":         pfx,
            "customer_id":     cust["id"]   if cust else None,
            "customer_name":   cust["name"] if cust else pfx,
            "active_calls":    entry.get("llamadas_activas", 0),
            "timbrando":       entry.get("timbrando", 0),
            "total":           entry.get("total", 0),
        })
    by_customer.sort(key=lambda x: -x["active_calls"])

    return {
        "total":       total,
        "by_customer": by_customer,
        "kamailio": {
            "ongoing":     ongoing,
            "connecting":  timbrando,
            "starting":    0,
            "available":   bool(snap),
            "snapshot_ts": snap.get("ts", ""),
        },
    }


@router.get("/detail")
async def live_detail(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    snap  = _read_snapshot()
    calls = snap.get("llamadas", [])

    if not calls:
        # Fallback: active_calls DB
        r = await db.execute(text("""
            SELECT ac.call_id, ac.src_number AS origen, ac.dst_number AS destino,
                   ac.src_ip AS ip_origen, ac.started_at,
                   c.name AS customer_name,
                   TIMESTAMPDIFF(SECOND, ac.started_at, NOW()) AS duration_sec
            FROM active_calls ac
            JOIN customers c ON ac.customer_id = c.id
            ORDER BY ac.started_at
        """))
        rows = []
        for row in r.mappings().all():
            d = dict(row)
            if d.get("started_at"):
                d["started_at"] = d["started_at"].isoformat()
            rows.append(d)
        return rows

    pmap = await _prefix_map(db)
    now_ts = int(_time.time())

    result = []
    for c in calls:
        pfx     = c.get("prefijo", "")
        cust    = _resolve(pfx, pmap)
        start_ts = c.get("start_ts", 0)
        dur_sec  = max(now_ts - start_ts, 0) if start_ts else 0

        result.append({
            "call_id":       c.get("call_id", ""),
            "ip_origen":     c.get("ip_origen", ""),
            "origen":        c.get("origen", ""),
            "destino":       c.get("destino", ""),
            "prefijo":       pfx,
            "customer_name": cust["name"] if cust else pfx,
            "tiempo":        c.get("tiempo", "00:00:00"),
            "duration_sec":  dur_sec,
            # ISO UTC para que el browser muestre hora local correcta
            "started_at":    datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat() if start_ts else None,
        })

    return sorted(result, key=lambda x: -(x.get("duration_sec") or 0))


@router.get("/connecting")
async def live_connecting(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("""
        SELECT
            st.call_id,
            st.from_uri                                          AS src_number,
            REGEXP_REPLACE(st.to_uri, '^[0-9]{2,6}(51[0-9]+)$', '\\\\1')
                                                                 AS dst_number,
            st.to_uri                                            AS dst_raw,
            MIN(st.captured_at)                                  AS started_at,
            TIMESTAMPDIFF(SECOND, MIN(st.captured_at), NOW())   AS ring_sec,
            COALESCE(cu.name, 'Desconocido')                     AS customer_name
        FROM sip_traces st
        LEFT JOIN customer_ips ci ON ci.ip = st.src_ip
        LEFT JOIN customers    cu ON cu.id = ci.customer_id
        WHERE st.captured_at >= NOW() - INTERVAL 3 MINUTE
          AND st.sip_method   = 'INVITE'
          AND st.call_id NOT IN (
              SELECT DISTINCT s2.call_id
              FROM sip_traces s2
              WHERE s2.captured_at >= NOW() - INTERVAL 3 MINUTE
                AND (s2.sip_status = 200 OR s2.sip_method IN ('BYE','CANCEL')
                     OR s2.sip_status >= 300)
          )
        GROUP BY st.call_id, st.from_uri, st.to_uri, cu.name
        ORDER BY started_at ASC
        LIMIT 500
    """))
    rows = []
    for r_ in r.mappings().all():
        rows.append({
            "call_id":       r_["call_id"],
            "src_number":    r_["src_number"],
            "dst_number":    r_["dst_number"] or r_["dst_raw"],
            "started_at":    r_["started_at"].isoformat() if r_["started_at"] else None,
            "ring_sec":      r_["ring_sec"],
            "customer_name": r_["customer_name"],
        })
    return rows


@router.delete("/stale")
async def cleanup_stale(
    max_minutes: int = 60,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    r = await db.execute(text("""
        DELETE FROM active_calls
        WHERE TIMESTAMPDIFF(MINUTE, started_at, NOW()) > :max_min
    """), {"max_min": max_minutes})
    await db.commit()
    return {"deleted": r.rowcount, "max_minutes": max_minutes}
