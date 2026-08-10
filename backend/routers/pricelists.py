# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Pricelists: borrador/aprobación de tarifas antes de tocar `rates` en vivo.

El billing worker (`main.py::_billing_worker`) y el ingest de CDR
(`routers/cdrs.py::ingest_cdr`) leen ÚNICAMENTE la tabla `rates` — nunca un
draft. Mientras un draft esté en estado 'draft', es indistinguible de que no
existiera para efectos de facturación. Solo `POST /drafts/{id}/publish`
escribe en `rates`, y lo hace en una sola transacción.
"""
import csv
import io

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from auth import require_admin
from database import get_db
from audit import record_event

router = APIRouter()

CSV_COLUMNS = ["prefix", "rateinitial", "connectcharge", "billingblock", "minimal_time_charge"]


class DraftIn(BaseModel):
    rate_plan_id: int
    label: str


class DraftItemIn(BaseModel):
    prefix_id: int
    rateinitial: float
    connectcharge: float = 0.0
    billingblock: int = Field(default=1, ge=1)
    minimal_time_charge: int = 0


@router.get("/drafts")
async def list_drafts(rate_plan_id: Optional[int] = None,
                       db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    where = "WHERE d.rate_plan_id = :plan_id" if rate_plan_id else ""
    params = {"plan_id": rate_plan_id} if rate_plan_id else {}
    r = await db.execute(text(f"""
        SELECT d.*, rp.name AS rate_plan_name,
               (SELECT COUNT(*) FROM rate_plan_draft_items i WHERE i.draft_id = d.id) AS item_count
        FROM rate_plan_drafts d
        JOIN rate_plans rp ON rp.id = d.rate_plan_id
        {where}
        ORDER BY d.created_at DESC
    """), params)
    return r.mappings().all()


@router.post("/drafts", status_code=201)
async def create_draft(body: DraftIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    await db.execute(text("""
        INSERT INTO rate_plan_drafts (rate_plan_id, label, created_by)
        VALUES (:rate_plan_id, :label, :created_by)
    """), {**body.model_dump(), "created_by": admin.get("name") or admin.get("email")})
    await db.commit()
    r = await db.execute(text("SELECT LAST_INSERT_ID() AS id"))
    return {"id": r.scalar()}


@router.get("/drafts/{draft_id}")
async def get_draft(draft_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    """Items del draft + su tarifa actual en vivo, para mostrar el diff antes de publicar."""
    d = await db.execute(text("""
        SELECT d.*, rp.name AS rate_plan_name FROM rate_plan_drafts d
        JOIN rate_plans rp ON rp.id = d.rate_plan_id WHERE d.id = :id
    """), {"id": draft_id})
    draft = d.mappings().first()
    if not draft:
        raise HTTPException(404, "Draft no encontrado")

    items = await db.execute(text("""
        SELECT i.prefix_id, p.prefix, p.destination, p.group_name,
               i.rateinitial AS new_rateinitial, i.connectcharge AS new_connectcharge,
               i.billingblock AS new_billingblock, i.minimal_time_charge AS new_minimal_time_charge,
               r.rateinitial AS current_rateinitial, r.connectcharge AS current_connectcharge
        FROM rate_plan_draft_items i
        JOIN prefixes p ON p.id = i.prefix_id
        LEFT JOIN rates r ON r.rate_plan_id = :plan_id AND r.prefix_id = i.prefix_id
        WHERE i.draft_id = :draft_id
        ORDER BY p.prefix
    """), {"draft_id": draft_id, "plan_id": draft["rate_plan_id"]})

    return {"draft": dict(draft), "items": items.mappings().all()}


@router.put("/drafts/{draft_id}/items")
async def upsert_items(draft_id: int, body: List[DraftItemIn],
                        db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    d = await db.execute(text("SELECT status FROM rate_plan_drafts WHERE id = :id"), {"id": draft_id})
    row = d.first()
    if not row:
        raise HTTPException(404, "Draft no encontrado")
    if row[0] != "draft":
        raise HTTPException(409, "Este draft ya fue publicado o descartado — no se puede editar")

    for item in body:
        await db.execute(text("""
            INSERT INTO rate_plan_draft_items
                (draft_id, prefix_id, rateinitial, connectcharge, billingblock, minimal_time_charge)
            VALUES (:draft_id, :prefix_id, :rateinitial, :connectcharge, :billingblock, :minimal_time_charge)
            ON DUPLICATE KEY UPDATE
                rateinitial = VALUES(rateinitial), connectcharge = VALUES(connectcharge),
                billingblock = VALUES(billingblock), minimal_time_charge = VALUES(minimal_time_charge)
        """), {**item.model_dump(), "draft_id": draft_id})
    await db.commit()
    return {"ok": True, "updated": len(body)}


@router.delete("/drafts/{draft_id}/items/{prefix_id}", status_code=204)
async def remove_item(draft_id: int, prefix_id: int,
                       db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text(
        "DELETE FROM rate_plan_draft_items WHERE draft_id = :draft_id AND prefix_id = :prefix_id"
    ), {"draft_id": draft_id, "prefix_id": prefix_id})
    if r.rowcount == 0:
        raise HTTPException(404, "Item no encontrado en el draft")
    await db.commit()


@router.post("/drafts/{draft_id}/publish")
async def publish_draft(draft_id: int, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    d = await db.execute(text("SELECT * FROM rate_plan_drafts WHERE id = :id"), {"id": draft_id})
    draft = d.mappings().first()
    if not draft:
        raise HTTPException(404, "Draft no encontrado")
    if draft["status"] != "draft":
        raise HTTPException(409, "Este draft ya fue publicado o descartado")

    items = (await db.execute(text(
        "SELECT * FROM rate_plan_draft_items WHERE draft_id = :id"
    ), {"id": draft_id})).mappings().all()
    if not items:
        raise HTTPException(422, "El draft no tiene tarifas cargadas")

    for item in items:
        await db.execute(text("""
            INSERT INTO rates (rate_plan_id, prefix_id, rateinitial, connectcharge, billingblock, minimal_time_charge, status)
            VALUES (:plan_id, :prefix_id, :rateinitial, :connectcharge, :billingblock, :minimal_time_charge, 'active')
            ON DUPLICATE KEY UPDATE
                rateinitial = VALUES(rateinitial), connectcharge = VALUES(connectcharge),
                billingblock = VALUES(billingblock), minimal_time_charge = VALUES(minimal_time_charge)
        """), {
            "plan_id": draft["rate_plan_id"], "prefix_id": item["prefix_id"],
            "rateinitial": item["rateinitial"], "connectcharge": item["connectcharge"],
            "billingblock": item["billingblock"], "minimal_time_charge": item["minimal_time_charge"],
        })

    by = admin.get("name") or admin.get("email")
    await db.execute(text("""
        UPDATE rate_plan_drafts SET status='published', published_at=NOW(), published_by=:by WHERE id=:id
    """), {"by": by, "id": draft_id})
    await record_event(db, "rate_plan_draft", draft_id, "published", by,
                        f"{len(items)} tarifas publicadas en plan '{draft['label']}'")
    await db.commit()
    return {"ok": True, "published": len(items)}


@router.post("/drafts/{draft_id}/discard")
async def discard_draft(draft_id: int, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    r = await db.execute(text("SELECT status, label FROM rate_plan_drafts WHERE id = :id"), {"id": draft_id})
    row = r.mappings().first()
    if not row:
        raise HTTPException(404, "Draft no encontrado")
    if row["status"] != "draft":
        raise HTTPException(409, "Este draft ya fue publicado o descartado")

    await db.execute(text("UPDATE rate_plan_drafts SET status='discarded' WHERE id=:id"), {"id": draft_id})
    await record_event(db, "rate_plan_draft", draft_id, "discarded",
                        admin.get("name") or admin.get("email"), row["label"])
    await db.commit()
    return {"ok": True}


@router.post("/drafts/{draft_id}/import-csv")
async def import_csv(draft_id: int, file: UploadFile,
                      db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    """
    Columnas: prefix, rateinitial, connectcharge (opcional), billingblock (opcional),
    minimal_time_charge (opcional). El prefijo debe existir ya en Tarifas → Prefijos —
    a propósito NO crea prefijos nuevos desde acá, eso es una acción aparte.
    """
    d = await db.execute(text("SELECT status FROM rate_plan_drafts WHERE id = :id"), {"id": draft_id})
    row = d.first()
    if not row:
        raise HTTPException(404, "Draft no encontrado")
    if row[0] != "draft":
        raise HTTPException(409, "Este draft ya fue publicado o descartado — no se puede editar")

    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))

    imported, errors = 0, []
    for i, row_data in enumerate(reader, start=2):  # línea 1 = encabezado
        prefix_val = (row_data.get("prefix") or "").strip()
        if not prefix_val:
            errors.append(f"Línea {i}: falta 'prefix'")
            continue
        try:
            rateinitial = float(row_data["rateinitial"])
        except (KeyError, ValueError):
            errors.append(f"Línea {i} ({prefix_val}): 'rateinitial' inválido")
            continue

        pfx_row = await db.execute(text("SELECT id FROM prefixes WHERE prefix = :p"), {"p": prefix_val})
        pfx = pfx_row.first()
        if not pfx:
            errors.append(f"Línea {i}: prefijo '{prefix_val}' no existe — crearlo primero en Tarifas → Prefijos")
            continue

        # Re-auditoría v2.56.0 (hallazgo crítico): `int(row_data.get("billingblock")
        # or 1)` solo cubre la columna AUSENTE o vacía — un CSV con "0" explícito
        # (string no vacío, por lo tanto truthy) pasaba de largo con
        # billingblock=0, que rating.py::billable_blocks() no soporta
        # (ZeroDivisionError). Este import no pasa por DraftItemIn (arma el
        # INSERT a mano), así que el Field(ge=1) del modelo no alcanza a
        # cubrirlo — se valida acá explícitamente, como una fila más con error.
        try:
            billingblock = int(row_data.get("billingblock") or 1)
            if billingblock < 1:
                raise ValueError
        except (KeyError, ValueError):
            errors.append(f"Línea {i} ({prefix_val}): 'billingblock' debe ser un entero ≥ 1")
            continue

        await db.execute(text("""
            INSERT INTO rate_plan_draft_items
                (draft_id, prefix_id, rateinitial, connectcharge, billingblock, minimal_time_charge)
            VALUES (:draft_id, :prefix_id, :rateinitial, :connectcharge, :billingblock, :minimal_time_charge)
            ON DUPLICATE KEY UPDATE
                rateinitial = VALUES(rateinitial), connectcharge = VALUES(connectcharge),
                billingblock = VALUES(billingblock), minimal_time_charge = VALUES(minimal_time_charge)
        """), {
            "draft_id": draft_id, "prefix_id": pfx[0], "rateinitial": rateinitial,
            "connectcharge": float(row_data.get("connectcharge") or 0),
            "billingblock": billingblock,
            "minimal_time_charge": int(row_data.get("minimal_time_charge") or 0),
        })
        imported += 1

    await db.commit()
    return {"imported": imported, "errors": errors}


@router.get("/drafts/{draft_id}/export-csv")
async def export_draft_csv(draft_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    exists = await db.execute(text("SELECT 1 FROM rate_plan_drafts WHERE id = :id"), {"id": draft_id})
    if not exists.first():
        raise HTTPException(404, "Draft no encontrado")
    r = await db.execute(text("""
        SELECT p.prefix, i.rateinitial, i.connectcharge, i.billingblock, i.minimal_time_charge
        FROM rate_plan_draft_items i JOIN prefixes p ON p.id = i.prefix_id
        WHERE i.draft_id = :id ORDER BY p.prefix
    """), {"id": draft_id})
    return _csv_response(r.mappings().all(), f"draft_{draft_id}.csv")


def _csv_response(rows, filename: str) -> StreamingResponse:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row[k] for k in CSV_COLUMNS})
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
