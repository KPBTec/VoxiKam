# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from auth import require_admin
from database import get_db
from audit import diff_and_record, record_event

router = APIRouter()
SCRIPTS = Path(__file__).parent.parent.parent / "scripts"


class AreaIn(BaseModel):
    name: str
    description: Optional[str] = None
    country_code: str = "PE"


@router.get("")
async def list_areas(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("""
        SELECT a.id, a.name, a.description, a.country_code, c.name AS country_name, a.created_at,
               COUNT(p.id) AS prefix_count
        FROM areas a
        LEFT JOIN countries c ON c.code = a.country_code
        LEFT JOIN prefixes p ON p.group_name = a.name
        GROUP BY a.id
        ORDER BY a.name
    """))
    return r.mappings().all()


@router.get("/countries")
async def list_countries(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("SELECT code, name FROM countries ORDER BY name"))
    return r.mappings().all()


@router.post("", status_code=201)
async def create_area(body: AreaIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    # Único por (name, country_code), no por name solo — el mismo nombre de área
    # puede repetirse en países distintos (ej. "MOVILES" en PE y en otro país).
    exists = await db.execute(text("SELECT id FROM areas WHERE name = :name AND country_code = :country_code"),
                               {"name": body.name, "country_code": body.country_code})
    if exists.first():
        raise HTTPException(409, "Ya existe un área con ese nombre en ese país")
    await db.execute(text(
        "INSERT INTO areas (name, description, country_code) VALUES (:name, :description, :country_code)"
    ), body.model_dump())
    await db.commit()
    r = await db.execute(text("SELECT LAST_INSERT_ID() AS id"))
    new_id = r.scalar()
    await record_event(db, "area", new_id, "created", admin.get("name") or admin.get("email"), body.name)
    await db.commit()
    return {"id": new_id}


@router.put("/{aid}")
async def update_area(aid: int, body: AreaIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    r = await db.execute(text("SELECT * FROM areas WHERE id = :id"), {"id": aid})
    before = r.mappings().first()
    if not before:
        raise HTTPException(404, "Área no encontrada")

    if body.name != before["name"] or body.country_code != before["country_code"]:
        dup = await db.execute(text(
            "SELECT id FROM areas WHERE name = :name AND country_code = :country_code AND id != :id"
        ), {"name": body.name, "country_code": body.country_code, "id": aid})
        if dup.first():
            raise HTTPException(409, "Ya existe un área con ese nombre en ese país")

    await db.execute(text(
        "UPDATE areas SET name=:name, description=:description, country_code=:country_code WHERE id=:id"
    ), {**body.model_dump(), "id": aid})

    # Rename-safe: cascadea a prefixes.group_name (mismo nombre de acople que usan rates.py/carriers.py)
    if body.name != before["name"]:
        await db.execute(text(
            "UPDATE prefixes SET group_name = :new WHERE group_name = :old"
        ), {"new": body.name, "old": before["name"]})

    await diff_and_record(db, "area", aid, dict(before), body.model_dump(),
                           ["name", "description", "country_code"],
                           admin.get("name") or admin.get("email"))
    await db.commit()
    return {"ok": True}


@router.delete("/{aid}", status_code=204)
async def delete_area(aid: int, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    r = await db.execute(text("SELECT * FROM areas WHERE id = :id"), {"id": aid})
    area = r.mappings().first()
    if not area:
        raise HTTPException(404, "Área no encontrada")

    cnt = await db.execute(text("SELECT COUNT(*) FROM prefixes WHERE group_name = :name"), {"name": area["name"]})
    if cnt.scalar() > 0:
        raise HTTPException(409, "El área tiene prefijos asignados — reasígnalos antes de eliminarla")

    await db.execute(text("DELETE FROM areas WHERE id = :id"), {"id": aid})
    await record_event(db, "area", aid, "deleted", admin.get("name") or admin.get("email"), area["name"])
    await db.commit()


async def _area_report_rows(
    db: AsyncSession,
    date_from: Optional[str], date_to: Optional[str],
    customer_id: Optional[int],
    by: str = "area",
) -> list[dict]:
    """
    Compartido entre areas.py::area_report() (admin, global o por cliente si
    se pasa customer_id) y portal.py::my_report_by_area() (cliente, siempre
    con su propio customer_id) — mismo criterio que _get_balance()/_get_calls()
    ya compartidos entre portal.py/api_v1.py.

    Rentabilidad + ASR/ACD/PDD por área (grupo de prefijos), usando
    cdrs.prefix_matched — el prefijo real que ganó el longest-prefix-match al
    tarifar (ver backend/routers/cdrs.py::ingest_cdr). LEFT JOIN a propósito:
    CDRs sin match (histórico previo a esta versión, o sin prefijo
    configurado) caen en "Sin área" en vez de desaparecer del reporte.

    Días completados → cdr_summary_day_area (agregado nocturno, rápido). Hoy →
    cdrs en vivo, acotado a su propia partición diaria — mismo patrón híbrido
    que ya usan reports.py/portal.py/reseller.py en esta misma sesión.

    by="area" (default) agrupa por el área resuelta (prefixes.group_name,
    "Sin área" si no matcheó ningún prefijo configurado) — son los grupos que
    se gestionan en /areas. by="prefix" agrupa por el prefijo crudo que
    matcheó (t.prefix_matched), sin pasar por group_name — vista plana que
    no existía antes. by="country" agrupa por el país del área asignada
    (areas.country_code → countries.name, vía el mismo group_name), no por
    prefixes.country (columna vieja de texto libre, desacoplada de la FK real).
    Las tres vistas alimentan el toggle "Por país / Por área / Por prefijo".
    """
    if by == "country":
        group_expr = "COALESCE(c2.name, 'Sin país')"
    elif by == "prefix":
        group_expr = "COALESCE(NULLIF(t.prefix_matched, ''), 'Sin prefijo')"
    else:
        group_expr = "COALESCE(NULLIF(p.group_name, ''), 'Sin área')"
    day_filters = ["sd.summary_date < CURDATE()"]
    live_filters = ["c.disposition != 'RESTART_ORPHANED'", "c.customer_id IS NOT NULL",
                     "c.start_ts >= CURDATE()", "c.start_ts < CURDATE() + INTERVAL 1 DAY"]
    params: dict = {}
    if date_from:
        day_filters.append("sd.summary_date >= :date_from")
        live_filters.append("c.start_ts >= :date_from")
        params["date_from"] = date_from
    if date_to:
        day_filters.append("sd.summary_date <= :date_to")
        # Sin DATE() envolviendo start_ts — ver comentario en cdrs.py::list_cdrs()
        # (sargable + partition pruning en la tabla particionada por mes).
        live_filters.append("c.start_ts < DATE_ADD(:date_to, INTERVAL 1 DAY)")
        params["date_to"] = date_to
    if customer_id:
        day_filters.append("sd.customer_id = :customer_id")
        live_filters.append("c.customer_id = :customer_id")
        params["customer_id"] = customer_id
    day_where  = " AND ".join(day_filters)
    live_where = " AND ".join(live_filters)

    r = await db.execute(text(f"""
        SELECT
            {group_expr} AS area,
            SUM(t.nbcall)                     AS nbcall,
            SUM(t.nbcall_fail)                 AS nbcall_fail,
            SUM(t.sessiontime)                 AS sessiontime,
            SUM(t.pdd_ms_sum)                  AS pdd_ms_sum,
            SUM(t.buycost)                     AS buycost,
            SUM(t.sessionbill)                 AS sessionbill,
            SUM(t.sessionbill - t.buycost)     AS lucro,
            ROUND(SUM(t.nbcall) * 100.0 / NULLIF(SUM(t.nbcall) + SUM(t.nbcall_fail), 0), 1) AS asr,
            ROUND(SUM(t.sessiontime) * 1.0 / NULLIF(SUM(t.nbcall), 0), 1)                    AS acd,
            ROUND(SUM(t.pdd_ms_sum) * 1.0 / NULLIF(SUM(t.nbcall), 0), 0)                     AS pdd_ms
        FROM (
            /* Días completados del rango pedido — tabla de resumen */
            SELECT sd.prefix_matched, sd.nbcall, sd.nbcall_fail, sd.sessiontime,
                   sd.pdd_ms_sum, sd.buycost, sd.sessionbill
            FROM cdr_summary_day_area sd
            WHERE {day_where}

            UNION ALL

            /* Hoy en vivo, acotado a su propia partición diaria */
            SELECT COALESCE(c.prefix_matched, '') AS prefix_matched,
                   SUM(c.disposition = 'ANSWERED')                              AS nbcall,
                   SUM(c.disposition NOT IN ('ANSWERED', 'RESTART_ORPHANED'))    AS nbcall_fail,
                   SUM(CASE WHEN c.disposition = 'ANSWERED' THEN c.billsec ELSE 0 END) AS sessiontime,
                   SUM(CASE WHEN c.answer_ts IS NOT NULL
                            THEN TIMESTAMPDIFF(MICROSECOND, c.start_ts, c.answer_ts) / 1000
                            ELSE 0 END)                                          AS pdd_ms_sum,
                   SUM(c.buycost)        AS buycost,
                   SUM(c.sessionbill)    AS sessionbill
            FROM cdrs c
            WHERE {live_where}
            GROUP BY COALESCE(c.prefix_matched, '')
        ) t
        LEFT JOIN prefixes p   ON p.prefix   = t.prefix_matched
        -- a2 se resuelve por (group_name, country) y no solo por nombre: desde
        -- que el área dejó de ser única globalmente (mismo nombre permitido en
        -- países distintos), un join solo por nombre podría matchear el área
        -- equivocada. p.country ya viene fijado por el selector país→área en
        -- cascada de /prefixes, así que siempre coincide con el área real.
        LEFT JOIN areas    a2  ON a2.name    = p.group_name AND a2.country_code = p.country
        LEFT JOIN countries c2 ON c2.code    = a2.country_code
        GROUP BY area
        ORDER BY lucro DESC
    """), params)
    return [dict(row) for row in r.mappings().all()]


@router.get("/report")
async def area_report(
    date_from: Optional[str] = Query(None),
    date_to:   Optional[str] = Query(None),
    customer_id: Optional[int] = Query(None),
    by: str = Query("area", pattern="^(area|prefix|country)$"),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """Global por default (todos los clientes) — pasar customer_id para ver solo uno."""
    return await _area_report_rows(db, date_from, date_to, customer_id, by)


@router.get("/backfill-status")
async def backfill_status(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    """
    Cuántos CDRs contestados todavía no tienen prefix_matched — para decidir
    si vale la pena correr el backfill. Lee de un cache en `settings`
    (scripts/cron_areas_backfill_status.py, cada hora) en vez de contar en
    vivo: sin filtro de fecha posible (hay que ver TODO el histórico), y
    cdrs está particionada por mes — contar en vivo en cada carga de /areas
    escaneaba las 4M+ filas históricas cada vez.

    Si el cache todavía no existe (deploy recién hecho, el cron no corrió
    ni una vez todavía) lo dice explícito en vez de devolver 0/0 — un 0/0
    falso escondería que sí hace falta backfill.
    """
    r = await db.execute(text(
        "SELECT key_name, value, updated_at FROM settings "
        "WHERE key_name IN ('areas_backfill_sin_match', 'areas_backfill_total')"
    ))
    stored = {row["key_name"]: row for row in r.mappings().all()}
    if len(stored) < 2:
        return {"sin_match": 0, "total": 0, "computed_at": None, "stale": True}

    computed_at = min(row["updated_at"] for row in stored.values())
    return {
        "sin_match": int(stored["areas_backfill_sin_match"]["value"]),
        "total": int(stored["areas_backfill_total"]["value"]),
        "computed_at": computed_at.isoformat(),
        "stale": False,
    }


@router.post("/backfill-prefix-matched")
async def run_backfill(admin=Depends(require_admin)):
    """
    Dispara scripts/backfill_prefix_matched.py --yes en background — recalcula
    prefix_matched para todo el histórico de CDRs contestados (necesario para que
    el reporte de arriba agrupe correctamente CDRs de antes de v2.13.0, que
    quedaron con prefix_matched NULL/no confiable). Solo toca esa columna, nunca
    buycost/sessionbill — no afecta nada ya facturado.
    """
    subprocess.Popen([sys.executable, str(SCRIPTS / "backfill_prefix_matched.py"), "--yes"])
    return {"ok": True, "started": True}
