# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from auth import require_admin
from database import get_db
from audit import diff_and_record, record_event

router = APIRouter()

EVENTS = ["cdr.created", "customer.balance_alert", "customer.status_changed", "customer.disconnect_policy_breach"]


class WebhookIn(BaseModel):
    url: str
    event: str
    enabled: bool = True


@router.get("/events")
async def list_events(_=Depends(require_admin)):
    return EVENTS


@router.get("")
async def list_webhooks(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text(
        "SELECT id, url, event, enabled, created_at FROM webhooks ORDER BY created_at DESC"
    ))
    return r.mappings().all()


@router.post("", status_code=201)
async def create_webhook(body: WebhookIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    if body.event not in EVENTS:
        raise HTTPException(422, f"Evento inválido — debe ser uno de: {', '.join(EVENTS)}")
    secret = secrets.token_hex(32)
    await db.execute(text(
        "INSERT INTO webhooks (url, event, secret, enabled) VALUES (:url, :event, :secret, :enabled)"
    ), {**body.model_dump(), "secret": secret})
    await db.commit()
    r = await db.execute(text("SELECT LAST_INSERT_ID() AS id"))
    new_id = r.scalar()
    await record_event(db, "webhook", new_id, "created", admin.get("name") or admin.get("email"), f"{body.event} → {body.url}")
    await db.commit()
    # El secret solo se muestra una vez, al crear — igual que una API key.
    return {"id": new_id, "secret": secret}


@router.put("/{wid}")
async def update_webhook(wid: int, body: WebhookIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    if body.event not in EVENTS:
        raise HTTPException(422, f"Evento inválido — debe ser uno de: {', '.join(EVENTS)}")
    r = await db.execute(text("SELECT url, event, enabled FROM webhooks WHERE id = :id"), {"id": wid})
    before = dict(r.mappings().first() or {})
    if not before:
        raise HTTPException(404, "Webhook no encontrado")

    await db.execute(text(
        "UPDATE webhooks SET url=:url, event=:event, enabled=:enabled WHERE id=:id"
    ), {**body.model_dump(), "id": wid})
    await diff_and_record(db, "webhook", wid, before, body.model_dump(), ["url", "event", "enabled"],
                           admin.get("name") or admin.get("email"))
    await db.commit()
    return {"ok": True}


@router.post("/{wid}/rotate-secret")
async def rotate_secret(wid: int, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    secret = secrets.token_hex(32)
    await db.execute(text("UPDATE webhooks SET secret = :secret WHERE id = :id"), {"secret": secret, "id": wid})
    await record_event(db, "webhook", wid, "secret_rotated", admin.get("name") or admin.get("email"))
    await db.commit()
    return {"secret": secret}


@router.delete("/{wid}", status_code=204)
async def delete_webhook(wid: int, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    r = await db.execute(text("SELECT url, event FROM webhooks WHERE id = :id"), {"id": wid})
    hook = r.mappings().first()
    await db.execute(text("DELETE FROM webhooks WHERE id = :id"), {"id": wid})
    if hook:
        await record_event(db, "webhook", wid, "deleted", admin.get("name") or admin.get("email"),
                            f"{hook['event']} → {hook['url']}")
    await db.commit()


@router.get("/{wid}/deliveries")
async def webhook_deliveries(wid: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("""
        SELECT id, event, status_code, attempt, success, error, created_at
        FROM webhook_deliveries WHERE webhook_id = :wid
        ORDER BY created_at DESC LIMIT 50
    """), {"wid": wid})
    return r.mappings().all()
