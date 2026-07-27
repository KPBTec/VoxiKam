# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
disconnect_policies.py — Evaluación de disconnect_policies contra
traffic_quality_hourly (ya la agrega cron_quality.py cada minuto).

Igual criterio que alerts.py: NO suspende ni bloquea nada, solo detecta
cuándo un cliente cruza el % de un tipo de corte (503/486/404/etc.) dentro
de una hora y avisa una sola vez por (política, cliente, hora) — el dedup
lo da el UNIQUE KEY de disconnect_policy_alerts, no un flag en memoria.
"""
import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from mailer import send_email, alert_html
from webhooks import dispatch_event
from alerts import get_alert_notify_email

log = logging.getLogger("voxikam.disconnect_policies")

# code_column va interpolado directo en la query (ver abajo) — whitelist defensivo
# además del ENUM de la tabla, nunca confiar solo en la constraint de la DB para un f-string.
_VALID_COLUMNS = {"c_487", "c_486", "c_404", "c_503", "c_other", "short_calls"}


async def check_disconnect_policies(db: AsyncSession) -> None:
    policies = (await db.execute(text(
        "SELECT id, label, code_column, threshold_pct, min_calls FROM disconnect_policies WHERE active = 1"
    ))).mappings().all()
    if not policies:
        return

    for policy in policies:
        col = policy["code_column"]
        if col not in _VALID_COLUMNS:
            log.error("disconnect_policies: code_column inválido ignorado: %r", col)
            continue
        rows = (await db.execute(text(f"""
            SELECT q.customer_id, c.name AS customer_name, q.ts_hour, q.total, q.{col} AS hits
            FROM traffic_quality_hourly q
            JOIN customers c ON c.id = q.customer_id
            WHERE q.ts_hour >= NOW() - INTERVAL 2 HOUR
              AND q.total >= :min_calls
              AND q.{col} / q.total * 100 >= :threshold
        """), {"min_calls": policy["min_calls"], "threshold": policy["threshold_pct"]})).mappings().all()

        for row in rows:
            pct = round(float(row["hits"]) / float(row["total"]) * 100, 2)
            inserted = await db.execute(text("""
                INSERT IGNORE INTO disconnect_policy_alerts
                    (policy_id, customer_id, ts_hour, pct, total_calls)
                VALUES (:policy_id, :customer_id, :ts_hour, :pct, :total)
            """), {
                "policy_id": policy["id"], "customer_id": row["customer_id"],
                "ts_hour": row["ts_hour"], "pct": pct, "total": row["total"],
            })
            await db.commit()
            if inserted.rowcount == 0:
                continue  # ya se avisó esta combinación política+cliente+hora

            to_email = await get_alert_notify_email(db)
            ok = await send_email(
                db, to=to_email,
                subject=f"VoxiKam — {policy['label']} — {row['customer_name']}",
                html=alert_html(
                    policy["label"],
                    [
                        ("Cliente", row["customer_name"]),
                        ("Hora", str(row["ts_hour"])),
                        ("% de la hora", f"{pct}%"),
                        ("Llamadas en la hora", str(row["total"])),
                    ],
                    footer="Esto es informativo — VoxiKam no suspende ni bloquea nada automáticamente.",
                ),
            )
            if not ok:
                log.warning("check_disconnect_policies: no se pudo enviar el correo (policy_id=%s, customer_id=%s)",
                            policy["id"], row["customer_id"])

            asyncio.create_task(dispatch_event("customer.disconnect_policy_breach", {
                "customer_id": row["customer_id"], "customer_name": row["customer_name"],
                "policy_id": policy["id"], "policy_label": policy["label"],
                "code_column": col, "pct": pct, "total_calls": row["total"],
                "ts_hour": str(row["ts_hour"]),
            }))
