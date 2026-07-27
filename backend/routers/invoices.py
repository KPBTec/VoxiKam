# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

import base64
import html
import json
import logging
import re
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path
import os

from alerts import check_balance_alert
from audit import record_event
from auth import require_admin
from database import get_db
from mailer import send_email

router = APIRouter()
INVOICES_DIR = Path(os.getenv("INVOICES_DIR", "/opt/voxikam/invoices"))
# Anidado DENTRO de invoices/ a propósito — ese directorio ya está excluido
# del rsync --delete de cada deploy (ver deploy.sh, fix v2.29.0 por pérdida de
# PDFs); poner el logo acá adentro hace que sobreviva a futuros deploys sin
# tener que acordarse de agregar OTRO exclude.
BRANDING_DIR = INVOICES_DIR / "branding"
log = logging.getLogger("voxikam.invoices")

_TEMPLATE_KEYS = (
    "invoice_logo_enabled", "invoice_logo_ext",
    "invoice_company_enabled", "invoice_company_name", "invoice_company_ruc", "invoice_company_address",
    "invoice_footer_enabled", "invoice_footer_text",
    "invoice_accent_enabled", "invoice_accent_color",
)
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


@router.get("")
async def list_invoices(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("""
        SELECT i.*, c.name AS customer_name
        FROM invoices i JOIN customers c ON i.customer_id = c.id
        ORDER BY i.created_at DESC
    """))
    return r.mappings().all()


async def _fetch_customer(db, customer_id: int) -> dict:
    r = await db.execute(text("""
        SELECT name, company, email, phone FROM customers WHERE id = :id
    """), {"id": customer_id})
    row = r.mappings().first()
    return dict(row) if row else {}


async def _fetch_daily(db, customer_id: int, period_start: str, period_end: str) -> list:
    # start_ts sin envolver en el WHERE — sargable + partition pruning (ver
    # cdrs.py::list_cdrs()). GROUP BY DATE(start_ts) queda igual: para entonces
    # ya está acotado a un cliente + rango de fechas, no a la tabla entera.
    r = await db.execute(text("""
        SELECT
            DATE(start_ts)       AS day,
            COUNT(*)             AS calls,
            SUM(billsec) / 60.0  AS minutes,
            SUM(sessionbill)     AS amount
        FROM cdrs
        WHERE customer_id = :cid
          AND start_ts >= :from_d AND start_ts < DATE_ADD(:to_d, INTERVAL 1 DAY)
          AND disposition = 'ANSWERED'
        GROUP BY DATE(start_ts)
        ORDER BY DATE(start_ts)
    """), {"cid": customer_id, "from_d": period_start, "to_d": period_end})
    return [dict(row) for row in r.mappings().all()]


@router.post("/generate")
async def generate_invoice(
    customer_id: int,
    period_start: str,
    period_end: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_admin),
):
    r = await db.execute(text("""
        SELECT
            COUNT(*)              AS nbcall,
            SUM(billsec) / 60.0   AS total_minutes,
            SUM(sessionbill)      AS subtotal
        FROM cdrs
        WHERE customer_id = :cid
          AND start_ts >= :from_d AND start_ts < DATE_ADD(:to_d, INTERVAL 1 DAY)
          AND disposition = 'ANSWERED'
    """), {"cid": customer_id, "from_d": period_start, "to_d": period_end})
    totals = r.mappings().first()

    subtotal   = float(totals["subtotal"] or 0)
    tax_rate   = 18.0
    tax_amount = round(subtotal * tax_rate / 100, 4)
    total      = round(subtotal + tax_amount, 4)

    await db.execute(text("""
        INSERT INTO invoices (customer_id, period_start, period_end, nbcall,
                              total_minutes, subtotal, tax_rate, tax_amount, total)
        VALUES (:cid, :ps, :pe, :nbcall, :mins, :subtotal, :tax_rate, :tax_amount, :total)
    """), {
        "cid": customer_id, "ps": period_start, "pe": period_end,
        "nbcall": totals["nbcall"], "mins": totals["total_minutes"],
        "subtotal": subtotal, "tax_rate": tax_rate,
        "tax_amount": tax_amount, "total": total,
    })
    await db.commit()
    r2 = await db.execute(text("SELECT LAST_INSERT_ID() AS id"))
    inv_id = r2.scalar()

    await record_event(db, "invoice", inv_id, "generated", admin.get("name") or admin.get("email"),
                        f"customer_id={customer_id} periodo {period_start}..{period_end} total={total}")
    await db.commit()

    customer = await _fetch_customer(db, customer_id)
    pdf_path = None
    try:
        daily    = await _fetch_daily(db, customer_id, period_start, period_end)
        template = await _get_invoice_template(db)
        pdf_path = _generate_pdf(inv_id, customer, period_start, period_end,
                                 totals, daily, subtotal, tax_amount, total, template)
        if pdf_path:
            await db.execute(text("UPDATE invoices SET pdf_path=:p WHERE id=:id"),
                             {"p": str(pdf_path), "id": inv_id})
            await db.commit()
    except Exception:
        # Encontrado en la auditoría global v2.38.0: este bloque tragaba
        # cualquier fallo sin log ni rollback — una factura sin PDF quedaba
        # sin ninguna pista de por qué, y la sesión seguía usándose después
        # (línea de _auto_email_enabled más abajo) en un estado potencialmente
        # inconsistente si el fallo ocurrió a mitad del UPDATE de pdf_path.
        log.exception("generate_invoice: fallo generando/guardando PDF para invoice_id=%s", inv_id)
        await db.rollback()
        pdf_path = None

    if pdf_path and await _auto_email_enabled(db):
        sent = await _send_invoice_email(db, inv_id, customer, pdf_path, total, period_start, period_end)
        if not sent:
            log.warning("generate_invoice: auto-envío habilitado pero falló para invoice_id=%s", inv_id)

    return {"id": inv_id, "total": total, "pdf": f"/api/admin/invoices/{inv_id}/pdf"}


async def _auto_email_enabled(db: AsyncSession) -> bool:
    r = await db.execute(text("SELECT value FROM settings WHERE key_name = 'invoices_auto_email'"))
    row = r.first()
    return bool(row and row[0] == "1")


async def _send_invoice_email(db: AsyncSession, inv_id: int, customer: dict, pdf_path,
                               total: float, period_start: str, period_end: str) -> bool:
    if not customer.get("email"):
        log.warning("_send_invoice_email: cliente sin email — invoice_id=%s", inv_id)
        return False
    try:
        pdf_bytes = Path(pdf_path).read_bytes()
    except OSError as e:
        log.error("_send_invoice_email: no se pudo leer el PDF — %s", e)
        return False

    # customer["name"] es texto libre editable por un admin (customers.py) —
    # sin escapar acá, un nombre con HTML/JS quedaba embebido tal cual en un
    # correo real enviado al cliente (HTML injection vía el propio nombre).
    # El validador de customers.py solo bloquea caracteres de control (para
    # el comentario de Kamailio), no tags HTML — hace falta este escape acá.
    safe_name = html.escape(customer.get("name", ""))
    ok = await send_email(
        db, to=customer["email"],
        subject=f"VoxiKam — Factura #{inv_id} ({period_start} al {period_end})",
        html=f"""
        <div style="font-family:sans-serif;max-width:560px;margin:0 auto;background:#070b14;">
          <div style="background:#0d1526;padding:24px;border-radius:12px 12px 0 0;border:1px solid #1a2744;border-bottom:0;">
            <h1 style="color:#dd8b3d;margin:0;font-size:18px;">Factura #{inv_id}</h1>
          </div>
          <div style="background:#070b14;border:1px solid #1a2744;border-top:0;border-radius:0 0 12px 12px;padding:20px 24px;">
            <p style="color:#e7ecf3;font-size:14px;">Hola {safe_name},</p>
            <p style="color:#e7ecf3;font-size:14px;">Adjuntamos tu factura del período {period_start} al {period_end}.</p>
            <p style="color:#dd8b3d;font-size:20px;font-weight:bold;">S/ {total:,.2f}</p>
          </div>
        </div>
        """,
        attachments=[{
            "filename": f"factura-{inv_id}.pdf",
            "content": base64.b64encode(pdf_bytes).decode(),
        }],
    )
    if ok:
        await db.execute(text(
            "UPDATE invoices SET emailed_at = NOW(), status = IF(status = 'draft', 'sent', status) WHERE id = :id"
        ), {"id": inv_id})
        await db.commit()
    return ok


@router.get("/{inv_id}/pdf")
async def download_pdf(inv_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("SELECT pdf_path FROM invoices WHERE id=:id"), {"id": inv_id})
    row = r.first()
    if not row or not row[0]:
        raise HTTPException(404, "PDF no encontrado")
    return FileResponse(row[0], media_type="application/pdf", filename=f"invoice-{inv_id}.pdf")


@router.post("/{inv_id}/regen-pdf")
async def regen_pdf(inv_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    """Regenera el PDF de una factura existente."""
    r = await db.execute(text("""
        SELECT i.*, c.name AS customer_name
        FROM invoices i JOIN customers c ON i.customer_id = c.id
        WHERE i.id = :id
    """), {"id": inv_id})
    row = r.mappings().first()
    if not row:
        raise HTTPException(404, "Factura no encontrada")

    customer = await _fetch_customer(db, row["customer_id"])
    daily    = await _fetch_daily(db, row["customer_id"],
                                  str(row["period_start"]), str(row["period_end"]))
    totals   = {"nbcall": row["nbcall"], "total_minutes": row["total_minutes"]}
    template = await _get_invoice_template(db)
    pdf_path = _generate_pdf(
        inv_id, customer,
        str(row["period_start"]), str(row["period_end"]),
        totals, daily,
        float(row["subtotal"]), float(row["tax_amount"]), float(row["total"]),
        template,
    )
    if not pdf_path:
        raise HTTPException(500, "No se pudo generar el PDF — revisa logs del backend")

    await db.execute(text("UPDATE invoices SET pdf_path=:p WHERE id=:id"),
                     {"p": str(pdf_path), "id": inv_id})
    await db.commit()
    return {"ok": True, "pdf": f"/api/admin/invoices/{inv_id}/pdf"}


@router.post("/{inv_id}/mark-paid")
async def mark_paid(inv_id: int, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    """
    Marcar pagada AHORA SÍ acredita el total de la factura al balance del
    cliente — antes eran dos sistemas totalmente desconectados (una factura
    pagada no bajaba la deuda acumulada en `customers.balance`, así que ese
    balance solo crecía para siempre y nunca reflejaba lo ya cobrado).

    `balance_credited_at` guarda cuándo se acreditó — evita un doble crédito
    si esta ruta se llama de nuevo sobre una factura que ya estaba pagada
    (reintento del admin, doble click, etc).
    """
    r = await db.execute(text(
        "SELECT customer_id, total, balance_credited_at FROM invoices WHERE id=:id"
    ), {"id": inv_id})
    inv = r.mappings().first()
    if not inv:
        raise HTTPException(404, "Factura no encontrada")

    await db.execute(text("UPDATE invoices SET status='paid', paid_at=NOW() WHERE id=:id"), {"id": inv_id})

    # Guarda atómica contra doble crédito por carrera (dos requests simultáneos
    # sobre la misma factura — doble click del admin, reintento de red, etc).
    # Leer balance_credited_at aparte y decidir en Python (como antes) es un
    # TOCTOU clásico: ambos requests pueden leer NULL antes de que cualquiera
    # de los dos comitee. El UPDATE condicional hace que MySQL serialice el
    # acceso a la fila — el segundo request, al desbloquearse, re-evalúa el
    # WHERE contra el valor ya comiteado por el primero y afecta 0 filas.
    credit_gate = await db.execute(text(
        "UPDATE invoices SET balance_credited_at = NOW() WHERE id = :id AND balance_credited_at IS NULL"
    ), {"id": inv_id})
    credited_now = credit_gate.rowcount == 1

    if credited_now:
        amount = float(inv["total"])
        await db.execute(text("UPDATE customers SET balance = balance + :amount WHERE id = :id"),
                          {"amount": amount, "id": inv["customer_id"]})
        bal_row = await db.execute(text("SELECT balance FROM customers WHERE id = :id"), {"id": inv["customer_id"]})
        new_balance = bal_row.scalar()
        await db.execute(text("""
            INSERT INTO balance_transactions (customer_id, type, amount, balance_after, reference, created_by)
            VALUES (:cid, 'invoice_payment', :amount, :bal, :ref, :by)
        """), {"cid": inv["customer_id"], "amount": amount, "bal": new_balance,
                "ref": f"Factura #{inv_id} pagada", "by": admin.get("name") or admin.get("email")})

    await record_event(db, "invoice", inv_id, "marked_paid", admin.get("name") or admin.get("email"))
    await db.commit()
    if credited_now:
        await check_balance_alert(db, inv["customer_id"])
    return {"ok": True}


# ── Reset del módulo (background job) ───────────────────────────────────────
# v2.52.0 lo hizo síncrono y se colgó en producción real: la subquery
# correlacionada del UPDATE escaneaba TODOS los cdrs (4.5M+) una vez POR
# CLIENTE, y el DELETE de balance_transactions puede ser casi tan grande como
# cdrs (una fila por llamada facturada) — nginx corta en 60s (ver
# nginx/voxikam.conf) y esto tardaba más. Mismo mecanismo exacto que
# billing_recalc.py (job_id + archivo de estado, sondeado por el frontend) —
# ese router ya tuvo este mismo bug con el mismo síntoma (request colgado en
# un rango de 1M+ CDRs) y ya se resolvió así una vez.
RESET_JOBS_DIR = Path("/var/lib/voxikam/billing_reset_jobs")


def _reset_job_path(job_id: str) -> Path:
    return RESET_JOBS_DIR / f"{job_id}.json"


def _write_reset_job(job_id: str, data: dict) -> None:
    RESET_JOBS_DIR.mkdir(parents=True, exist_ok=True)
    _reset_job_path(job_id).write_text(json.dumps(data, default=str))


def _read_reset_job(job_id: str) -> dict | None:
    try:
        return json.loads(_reset_job_path(job_id).read_text())
    except Exception:
        return None


async def _run_reset_job(job_id: str, applied_by: str | None) -> None:
    """Corre en background — sesión de DB propia (AsyncSessionLocal), la del
    request original ya cerró para cuando esto arranca."""
    from database import AsyncSessionLocal
    _write_reset_job(job_id, {"status": "running", "step": "backup"})
    try:
        async with AsyncSessionLocal() as db:
            inv_rows = (await db.execute(text("SELECT * FROM invoices"))).mappings().all()

            # balance_transactions puede tener tantas filas como cdrs
            # contestados (una por llamada facturada) — para un cliente de
            # alto volumen eso es fácil que sean millones. Volcarlas fila por
            # fila a JSON en memoria es justo el mismo tipo de problema que
            # colgó el request original; acá alcanza con un resumen agregado
            # por cliente y tipo (para saber "cuánto representaba" sin cargar
            # cada fila), que es una sola query GROUP BY liviana.
            tx_summary = (await db.execute(text("""
                SELECT customer_id, type, COUNT(*) AS n, SUM(amount) AS total_amount
                FROM balance_transactions
                GROUP BY customer_id, type
            """))).mappings().all()
            tx_count = sum(row["n"] for row in tx_summary)

            bal_rows = (await db.execute(text("SELECT id, name, balance FROM customers"))).mappings().all()

            install_dir = Path(os.getenv("INSTALL_DIR", "/opt/voxikam"))
            backup_dir = install_dir / "logs" / "billing_reset_backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / f"billing_reset_{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
            backup_path.write_text(json.dumps({
                "invoices":                        [dict(r) for r in inv_rows],
                "balance_transactions_summary":     [dict(r) for r in tx_summary],
                "customers_balance_before":         [dict(r) for r in bal_rows],
            }, default=str, indent=2), encoding="utf-8")

            _write_reset_job(job_id, {"status": "running", "step": "pdfs"})
            for inv in inv_rows:
                p = inv.get("pdf_path")
                if not p:
                    continue
                try:
                    fp = Path(p).resolve()
                    if fp.is_file() and fp.is_relative_to(INVOICES_DIR.resolve()) and fp.parent != BRANDING_DIR.resolve():
                        fp.unlink()
                except Exception:
                    log.warning("reset-module: no se pudo borrar PDF %s", p, exc_info=True)

            _write_reset_job(job_id, {"status": "running", "step": "delete"})
            await db.execute(text("DELETE FROM balance_transactions"))
            await db.execute(text("DELETE FROM invoices"))

            _write_reset_job(job_id, {"status": "running", "step": "recalc_balance"})
            # Un solo pase con JOIN (agregado UNA vez para todos los
            # clientes) en vez de una subquery correlacionada que reescaneaba
            # cdrs completo POR CADA cliente — es la causa real del cuelgue.
            # Consumo histórico total, negado: como si nunca se hubiera
            # acreditado ni un pago ni una recarga.
            await db.execute(text("""
                UPDATE customers c
                LEFT JOIN (
                    SELECT customer_id, SUM(sessionbill) AS total
                    FROM cdrs
                    WHERE disposition = 'ANSWERED'
                    GROUP BY customer_id
                ) t ON t.customer_id = c.id
                SET c.balance = -COALESCE(t.total, 0),
                    c.last_topup_amount = NULL,
                    c.last_alert_rule_id = NULL
            """))

            await record_event(
                db, "invoices", 0, "billing_module_reset", applied_by or "—",
                f"{len(inv_rows)} factura(s) + {tx_count} movimiento(s) borrados — backup: {backup_path.name}",
            )
            await db.commit()

            _write_reset_job(job_id, {
                "status": "done",
                "result": {
                    "backup_file": str(backup_path),
                    "invoices_deleted": len(inv_rows),
                    "balance_transactions_deleted": tx_count,
                    "customers_reset": len(bal_rows),
                },
            })
    except Exception as e:
        log.exception("reset-module job failed")
        _write_reset_job(job_id, {"status": "error", "error": str(e)})


@router.post("/reset-module")
async def reset_billing_module(background_tasks: BackgroundTasks, admin=Depends(require_admin)):
    """
    Lanza en background el borrado de TODAS las facturas y TODO el ledger de
    balance_transactions, de TODOS los clientes, y el recálculo de
    customers.balance como si nunca se hubiera acreditado ni un pago — puro
    consumo histórico en negativo. Devuelve un job_id de inmediato; el
    resultado se consulta con GET /reset-module/jobs/{job_id} (mismo patrón
    que billing_recalc.py).

    Pedido explícito del admin tras encontrar facturas duplicadas/de prueba
    para el mismo período (ver #5-#12 de un cliente, generadas mientras se
    probaba el módulo) que dejaron el balance sin sentido. Confirmado que
    estas facturas son PDFs internos sin validez tributaria (sin SUNAT), así
    que un DELETE liso es aceptable acá.
    """
    job_id = str(uuid.uuid4())
    background_tasks.add_task(_run_reset_job, job_id, admin.get("name") or admin.get("email"))
    return {"job_id": job_id}


@router.get("/reset-module/jobs/{job_id}")
async def get_reset_job(job_id: str, _=Depends(require_admin)):
    job = _read_reset_job(job_id)
    if not job:
        raise HTTPException(404, "Job no encontrado — puede haber expirado")
    return job


@router.post("/{inv_id}/send-email")
async def send_invoice_email(inv_id: int, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    """Envío manual — funciona sin importar si el auto-envío está habilitado o no (ej. reenvíos)."""
    r = await db.execute(text("""
        SELECT i.pdf_path, i.total, i.period_start, i.period_end, i.customer_id
        FROM invoices i WHERE i.id = :id
    """), {"id": inv_id})
    inv = r.mappings().first()
    if not inv:
        raise HTTPException(404, "Factura no encontrada")
    if not inv["pdf_path"]:
        raise HTTPException(422, "Esta factura todavía no tiene PDF generado")

    customer = await _fetch_customer(db, inv["customer_id"])
    ok = await _send_invoice_email(db, inv_id, customer, inv["pdf_path"],
                                    float(inv["total"]), str(inv["period_start"]), str(inv["period_end"]))
    if not ok:
        raise HTTPException(502, "No se pudo enviar el correo — revisa la configuración de correo en Sistema → Correo")
    await record_event(db, "invoice", inv_id, "email_sent_manual", admin.get("name") or admin.get("email"),
                        customer.get("email", ""))
    await db.commit()
    return {"ok": True}


class AutoEmailIn(BaseModel):
    enabled: bool


@router.get("/settings/auto-email")
async def get_auto_email(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    return {"enabled": await _auto_email_enabled(db)}


@router.put("/settings/auto-email")
async def set_auto_email(body: AutoEmailIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    await db.execute(text("""
        INSERT INTO settings (key_name, value, description)
        VALUES ('invoices_auto_email', :v, 'Enviar la factura por correo automáticamente al generarla')
        ON DUPLICATE KEY UPDATE value = :v
    """), {"v": "1" if body.enabled else "0"})
    await record_event(db, "invoice_settings", 0, "auto_email_toggled",
                        admin.get("name") or admin.get("email"), "on" if body.enabled else "off")
    await db.commit()
    return {"ok": True}


# ── Plantilla del PDF de factura ────────────────────────────────────────────
# Datos de marca opcionales — cada uno con su propio toggle, el admin decide
# si se usa o no. La estructura del PDF (tabla de llamadas, totales, IGV)
# queda hardcoded tal cual está — esto es solo lo que rodea ese contenido.

class InvoiceTemplateIn(BaseModel):
    logo_enabled: bool = False
    company_enabled: bool = False
    company_name: str = ""
    company_ruc: str = ""
    company_address: str = ""
    footer_enabled: bool = False
    footer_text: str = ""
    accent_enabled: bool = False
    accent_color: str = "#dd8b3d"


async def _get_invoice_template(db: AsyncSession) -> dict:
    r = await db.execute(text(
        f"SELECT key_name, value FROM settings WHERE key_name IN ({','.join(':k'+str(i) for i in range(len(_TEMPLATE_KEYS)))})"
    ), {f"k{i}": k for i, k in enumerate(_TEMPLATE_KEYS)})
    s = {row[0]: row[1] for row in r.all()}
    logo_ext = s.get("invoice_logo_ext") or ""
    logo_path = BRANDING_DIR / f"logo{logo_ext}" if logo_ext else None
    return {
        "logo_enabled": s.get("invoice_logo_enabled") == "1",
        "logo_path": logo_path if (logo_path and logo_path.exists()) else None,
        "company_enabled": s.get("invoice_company_enabled") == "1",
        "company_name": s.get("invoice_company_name") or "",
        "company_ruc": s.get("invoice_company_ruc") or "",
        "company_address": s.get("invoice_company_address") or "",
        "footer_enabled": s.get("invoice_footer_enabled") == "1",
        "footer_text": s.get("invoice_footer_text") or "",
        "accent_enabled": s.get("invoice_accent_enabled") == "1",
        "accent_color": s.get("invoice_accent_color") or "#dd8b3d",
    }


@router.get("/template")
async def get_invoice_template(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    tpl = await _get_invoice_template(db)
    return {**{k: v for k, v in tpl.items() if k != "logo_path"}, "has_logo": tpl["logo_path"] is not None}


@router.put("/template")
async def set_invoice_template(body: InvoiceTemplateIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    if body.accent_enabled and not _HEX_COLOR_RE.match(body.accent_color):
        raise HTTPException(400, "accent_color debe ser un color hex válido, ej. #dd8b3d")

    values = {
        "invoice_logo_enabled":    "1" if body.logo_enabled else "0",
        "invoice_company_enabled": "1" if body.company_enabled else "0",
        "invoice_company_name":    body.company_name,
        "invoice_company_ruc":     body.company_ruc,
        "invoice_company_address": body.company_address,
        "invoice_footer_enabled":  "1" if body.footer_enabled else "0",
        "invoice_footer_text":     body.footer_text,
        "invoice_accent_enabled":  "1" if body.accent_enabled else "0",
        "invoice_accent_color":    body.accent_color,
    }
    for key, value in values.items():
        await db.execute(text("""
            INSERT INTO settings (key_name, value, description)
            VALUES (:k, :v, 'Plantilla de factura — Sistema → Facturas → Plantilla')
            ON DUPLICATE KEY UPDATE value = :v
        """), {"k": key, "v": value})
    await record_event(db, "invoice_settings", 0, "template_updated", admin.get("name") or admin.get("email"))
    await db.commit()
    return {"ok": True}


_LOGO_MAGIC = {
    b"\x89PNG\r\n\x1a\n": ".png",
    b"\xff\xd8\xff": ".jpeg",  # cubre .jpg y .jpeg — mismo formato, misma firma
}
_LOGO_MAX_BYTES = 2 * 1024 * 1024  # 2MB — de sobra para un logo, evita llenar disco


@router.post("/template/logo")
async def upload_invoice_logo(file: UploadFile = File(...), db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg"):
        raise HTTPException(400, "El logo debe ser .png, .jpg o .jpeg")

    # La extensión del nombre no prueba nada — se valida el contenido real
    # (firma binaria) antes de guardar. Sin esto, alguien podía subir
    # cualquier archivo renombrado a .png y quedaba servido tal cual por
    # GET /template/logo (FileResponse no valida tipo de contenido real).
    body = await file.read()
    if len(body) > _LOGO_MAX_BYTES:
        raise HTTPException(400, "El logo no puede pesar más de 2MB")
    if not any(body.startswith(magic) for magic in _LOGO_MAGIC):
        raise HTTPException(400, "El archivo no es una imagen PNG/JPEG válida (la firma del contenido no coincide)")

    BRANDING_DIR.mkdir(parents=True, exist_ok=True)
    # Borra cualquier logo previo con otra extensión, para no dejar huérfanos
    for old in BRANDING_DIR.glob("logo.*"):
        old.unlink(missing_ok=True)

    dest = BRANDING_DIR / f"logo{ext}"
    dest.write_bytes(body)

    await db.execute(text("""
        INSERT INTO settings (key_name, value, description)
        VALUES ('invoice_logo_ext', :v, 'Extensión del logo de factura subido — Sistema → Facturas → Plantilla')
        ON DUPLICATE KEY UPDATE value = :v
    """), {"v": ext})
    await record_event(db, "invoice_settings", 0, "logo_uploaded", admin.get("name") or admin.get("email"), ext)
    await db.commit()
    return {"ok": True}


@router.get("/template/logo")
async def get_invoice_logo(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    tpl = await _get_invoice_template(db)
    if not tpl["logo_path"]:
        raise HTTPException(404, "Sin logo cargado")
    return FileResponse(tpl["logo_path"])


@router.delete("/template/logo")
async def delete_invoice_logo(db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    for old in BRANDING_DIR.glob("logo.*"):
        old.unlink(missing_ok=True)
    await db.execute(text("DELETE FROM settings WHERE key_name = 'invoice_logo_ext'"))
    await record_event(db, "invoice_settings", 0, "logo_deleted", admin.get("name") or admin.get("email"))
    await db.commit()
    return {"ok": True}


def _generate_pdf(inv_id, customer: dict, period_start, period_end,
                  totals, daily: list, subtotal, tax_amount, total,
                  template: dict | None = None) -> Path | None:
    try:
        from fpdf import FPDF, XPos, YPos
    except ImportError:
        return None

    tpl = template or {}
    accent_rgb = (221, 139, 61)  # #dd8b3d — mismo ámbar del resto de VoxiKam, default si no hay accent propio
    if tpl.get("accent_enabled") and tpl.get("accent_color"):
        hexc = tpl["accent_color"].lstrip("#")
        accent_rgb = tuple(int(hexc[i:i + 2], 16) for i in (0, 2, 4))

    try:
        INVOICES_DIR.mkdir(parents=True, exist_ok=True)

        pdf = FPDF()
        pdf.add_page()
        pdf.set_margins(20, 20, 20)
        NL = {"new_x": XPos.LMARGIN, "new_y": YPos.NEXT}

        # ── Logo + datos de marca (opcionales, cada uno con su propio toggle) ──
        top_y = pdf.get_y()
        if tpl.get("logo_enabled") and tpl.get("logo_path"):
            try:
                pdf.image(str(tpl["logo_path"]), x=20, y=top_y, h=16)
                pdf.set_y(top_y + 20)
            except Exception:
                pass  # logo corrupto/formato no soportado por fpdf2 — seguir sin logo, no romper la factura

        if tpl.get("company_enabled") and tpl.get("company_name"):
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(*accent_rgb)
            pdf.cell(0, 6, tpl["company_name"], **NL)
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(100, 100, 100)
            if tpl.get("company_ruc"):
                pdf.cell(0, 5, f"RUC: {tpl['company_ruc']}", **NL)
            if tpl.get("company_address"):
                pdf.cell(0, 5, tpl["company_address"], **NL)
            pdf.ln(3)

        # ── Encabezado ────────────────────────────────────────────────────────
        pdf.set_font("Helvetica", "B", 20)
        pdf.set_text_color(*accent_rgb)
        pdf.cell(0, 10, f"Factura #{inv_id}", **NL)

        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(120, 120, 120)
        pdf.cell(0, 6, f"Periodo: {period_start}  al  {period_end}", **NL)
        pdf.ln(4)

        # ── Datos del cliente ─────────────────────────────────────────────────
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, "Cliente", **NL)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(60, 60, 60)

        if customer.get("name"):
            pdf.cell(0, 5, customer["name"], **NL)
        if customer.get("company"):
            pdf.cell(0, 5, customer["company"], **NL)
        if customer.get("email"):
            pdf.cell(0, 5, customer["email"], **NL)
        if customer.get("phone"):
            pdf.cell(0, 5, customer["phone"], **NL)

        pdf.ln(6)

        # ── Separador ─────────────────────────────────────────────────────────
        pdf.set_draw_color(200, 200, 200)
        pdf.line(20, pdf.get_y(), 190, pdf.get_y())
        pdf.ln(6)

        # ── Resumen ───────────────────────────────────────────────────────────
        pdf.set_text_color(0, 0, 0)
        col_w = (pdf.w - 40) / 2

        def row(label: str, value: str, bold=False):
            style = "B" if bold else ""
            pdf.set_font("Helvetica", style, 11)
            pdf.cell(col_w, 8, label)
            pdf.cell(col_w, 8, value, align="R", **NL)

        row("Llamadas contestadas", f"{int(totals['nbcall'] or 0):,}")
        row("Minutos facturados",   f"{float(totals['total_minutes'] or 0):,.2f} min")
        pdf.ln(4)
        row("Subtotal",             f"S/ {subtotal:,.4f}")
        row("IGV (18%)",            f"S/ {tax_amount:,.4f}")
        pdf.ln(2)
        pdf.set_draw_color(200, 200, 200)
        pdf.line(20, pdf.get_y(), 190, pdf.get_y())
        pdf.ln(3)
        pdf.set_text_color(*accent_rgb)
        row("TOTAL",                f"S/ {total:,.4f}", bold=True)
        pdf.set_text_color(0, 0, 0)

        # ── Desglose por día ─────────────────────────────────────────────────
        if daily:
            pdf.ln(10)
            pdf.set_draw_color(200, 200, 200)
            pdf.line(20, pdf.get_y(), 190, pdf.get_y())
            pdf.ln(5)

            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(0, 7, "Detalle por día", **NL)
            pdf.ln(2)

            # Cabecera de tabla
            W = pdf.w - 40
            C = [W * 0.28, W * 0.22, W * 0.25, W * 0.25]  # Fecha | Llamadas | Minutos | Importe
            pdf.set_fill_color(245, 245, 245)
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(80, 80, 80)
            headers = ["Fecha", "Llamadas", "Minutos", "Importe"]
            aligns  = ["L", "R", "R", "R"]
            for h, w, a in zip(headers, C, aligns):
                pdf.cell(w, 7, h, align=a, fill=True)
            pdf.ln(7)

            # Filas
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(0, 0, 0)
            for i, d in enumerate(daily):
                fill = i % 2 == 1
                pdf.set_fill_color(250, 250, 250)
                vals = [
                    str(d["day"]),
                    f"{int(d['calls'] or 0):,}",
                    f"{float(d['minutes'] or 0):,.2f}",
                    f"S/ {float(d['amount'] or 0):,.4f}",
                ]
                for v, w, a in zip(vals, C, aligns):
                    pdf.cell(w, 6, v, align=a, fill=fill)
                pdf.ln(6)

                # Salto de página si queda poco espacio
                if pdf.get_y() > pdf.h - 30:
                    pdf.add_page()
                    pdf.set_font("Helvetica", "B", 9)
                    for h, w, a in zip(headers, C, aligns):
                        pdf.cell(w, 7, h, align=a, fill=True)
                    pdf.ln(7)
                    pdf.set_font("Helvetica", "", 9)

        if tpl.get("footer_enabled") and tpl.get("footer_text"):
            pdf.ln(10)
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(140, 140, 140)
            pdf.multi_cell(0, 4, tpl["footer_text"], align="C")

        path = INVOICES_DIR / f"invoice-{inv_id}.pdf"
        pdf.output(str(path))
        return path

    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("PDF generation failed for invoice %s: %s", inv_id, exc, exc_info=True)
        return None
