# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
webhooks.py — dispara eventos hacia URLs suscritas (cdr.created,
customer.balance_alert, customer.status_changed).

dispatch_event() abre su PROPIA sesión de DB (AsyncSessionLocal) y está pensado
para llamarse siempre vía BackgroundTasks — nunca in-line en el request path.
El ingest de CDR (`routers/cdrs.py::ingest_cdr`) lo llama Kamailio en cada
llamada colgada: si el dispatch de un webhook lento bloqueara esa response,
un endpoint externo caído podría empezar a frenar el procesamiento de CDRs.
"""
import hashlib
import hmac
import json

import httpx
from sqlalchemy import text

from database import AsyncSessionLocal

_TIMEOUT_S = 8.0


async def _deliver(db, hook, event: str, payload: str, attempt: int = 1) -> None:
    sig = hmac.new(hook["secret"].encode(), payload.encode(), hashlib.sha256).hexdigest()
    status_code, error, success = None, None, False
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            resp = await client.post(
                hook["url"], content=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-VoxiKam-Event": event,
                    "X-VoxiKam-Signature": sig,
                },
            )
            status_code = resp.status_code
            success = 200 <= resp.status_code < 300
    except Exception as e:
        error = str(e)[:500]

    await db.execute(text("""
        INSERT INTO webhook_deliveries (webhook_id, event, payload, status_code, attempt, success, error)
        VALUES (:wid, :event, :payload, :status_code, :attempt, :success, :error)
    """), {
        "wid": hook["id"], "event": event, "payload": payload,
        "status_code": status_code, "attempt": attempt, "success": success, "error": error,
    })
    await db.commit()

    # Un solo reintento inmediato — sin colas ni backoff exponencial, a propósito
    # (esto no es un bus de eventos, es una notificación best-effort).
    if not success and attempt == 1:
        await _deliver(db, hook, event, payload, attempt=2)


async def dispatch_event(event: str, data: dict) -> None:
    async with AsyncSessionLocal() as db:
        r = await db.execute(text(
            "SELECT id, url, secret FROM webhooks WHERE event = :event AND enabled = 1"
        ), {"event": event})
        hooks = r.mappings().all()
        if not hooks:
            return
        payload = json.dumps({"event": event, "data": data}, default=str)
        for hook in hooks:
            await _deliver(db, hook, event, payload)
