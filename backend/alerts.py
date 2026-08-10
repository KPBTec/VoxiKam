# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
alerts.py — Evaluación de balance_alert_rules contra el balance real de un cliente.

Se llama después de CUALQUIER cambio de balance (CDR facturado en el billing
worker, o ajuste manual desde el panel). No decide nada de negocio por sí solo
(no suspende clientes) — solo detecta cuándo se cruza un umbral nuevo y avisa
por correo al operador, una sola vez por nivel (se resetea si el cliente
vuelve a estar por encima de todos los umbrales activos).
"""

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from mailer import send_email, alert_html
from webhooks import dispatch_event

log = logging.getLogger("voxikam.alerts")


async def get_alert_notify_email(db: AsyncSession) -> str:
    row = await db.execute(text(
        "SELECT value FROM settings WHERE key_name = 'alert_notify_email'"
    ))
    r = row.first()
    if r and r[0]:
        return r[0]
    import os
    return os.getenv("ADMIN_EMAIL", "admin@localhost")


async def check_balance_alert(db: AsyncSession, customer_id: int) -> None:
    row = await db.execute(text("""
        SELECT id, name, balance, billing_type, last_topup_amount, last_alert_rule_id
        FROM customers WHERE id = :id
    """), {"id": customer_id})
    c = row.mappings().first()
    if not c:
        return

    rules_res = await db.execute(text("""
        SELECT id, label, threshold FROM balance_alert_rules
        WHERE billing_type = :bt AND active = 1
    """), {"bt": c["billing_type"]})
    rules = rules_res.mappings().all()

    breached = None
    if c["billing_type"] == "prepago":
        if not c["last_topup_amount"] or float(c["last_topup_amount"]) <= 0:
            return  # sin recarga registrada todavía — no hay referencia para calcular %
        pct_remaining = float(c["balance"]) / float(c["last_topup_amount"]) * 100
        # Re-auditoría v2.56.0: faltaba este break (la rama postpago, dos
        # líneas más abajo, ya lo tenía). Sin él, cuando el balance cruza
        # varios umbrales a la vez la última iteración (el threshold más
        # GRANDE que todavía cumple, o sea el MENOS severo) sobreescribía
        # `breached` — quedando con la regla menos severa en vez de la más
        # severa, justo lo opuesto del comentario de arriba. El primer match
        # en orden ascendente es, por construcción, el más severo.
        for r in sorted(rules, key=lambda r: r["threshold"]):  # más severo = menor %
            if pct_remaining <= float(r["threshold"]):
                breached = r
                break
    else:  # postpago — threshold negativo, más severo = más negativo
        for r in sorted(rules, key=lambda r: r["threshold"]):  # ya ordenado más negativo primero
            if float(c["balance"]) <= float(r["threshold"]):
                breached = r
                break

    already = c["last_alert_rule_id"]

    if breached is None:
        if already is not None:
            await db.execute(text(
                "UPDATE customers SET last_alert_rule_id = NULL WHERE id = :id"
            ), {"id": customer_id})
            await db.commit()
        return

    if breached["id"] == already:
        return  # mismo nivel ya notificado, no repetir en cada CDR

    # Auditoría v2.55: antes esto era check-then-act puro (leído arriba,
    # escrito acá sin condición) — con --workers>1, dos CDRs del mismo
    # cliente en dos procesos distintos podían cruzar el mismo umbral en la
    # misma ventana y ambos leer last_alert_rule_id todavía sin actualizar,
    # duplicando el correo/webhook. El WHERE de abajo lo vuelve atómico:
    # InnoDB hace un "current read" al evaluar el UPDATE (no la foto vieja de
    # la transacción), así que el segundo proceso en llegar ve el valor que
    # el primero ya escribió y su propio UPDATE afecta 0 filas — mismo
    # patrón que ya usan mark_paid()/disconnect_policies.py en este repo.
    result = await db.execute(text(
        "UPDATE customers SET last_alert_rule_id = :rid "
        "WHERE id = :id AND (last_alert_rule_id IS NULL OR last_alert_rule_id != :rid)"
    ), {"rid": breached["id"], "id": customer_id})
    await db.commit()
    if result.rowcount == 0:
        return  # otro proceso ya lo marcó en esta misma ventana — no duplicar el aviso

    to_email = await get_alert_notify_email(db)
    ok = await send_email(
        db, to=to_email,
        subject=f"VoxiKam — {breached['label']} — {c['name']}",
        html=alert_html(
            breached["label"],
            [
                ("Cliente", c["name"]),
                ("Tipo de facturación", c["billing_type"]),
                ("Balance actual", f"{c['balance']}"),
            ],
            footer="Revisá el detalle en Alertas → Alerta consumo dentro del panel de VoxiKam.",
        ),
    )
    if not ok:
        log.warning("check_balance_alert: no se pudo enviar el correo para cliente_id=%s", customer_id)

    # Fire-and-forget: no bloquear el resto del batch del billing worker en un webhook lento.
    asyncio.create_task(dispatch_event("customer.balance_alert", {
        "customer_id": customer_id, "customer_name": c["name"],
        "rule_id": breached["id"], "rule_label": breached["label"],
        "billing_type": c["billing_type"], "balance": float(c["balance"]),
    }))
