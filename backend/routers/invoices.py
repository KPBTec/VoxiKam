# la plataforma anterior — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path
import os

from auth import require_admin
from database import get_db

router = APIRouter()
INVOICES_DIR = Path(os.getenv("INVOICES_DIR", "/opt/kaplabilling/invoices"))


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
    r = await db.execute(text("""
        SELECT
            DATE(start_ts)       AS day,
            COUNT(*)             AS calls,
            SUM(billsec) / 60.0  AS minutes,
            SUM(sessionbill)     AS amount
        FROM cdrs
        WHERE customer_id = :cid
          AND DATE(start_ts) BETWEEN :from_d AND :to_d
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
    _=Depends(require_admin),
):
    r = await db.execute(text("""
        SELECT
            COUNT(*)              AS nbcall,
            SUM(billsec) / 60.0   AS total_minutes,
            SUM(sessionbill)      AS subtotal
        FROM cdrs
        WHERE customer_id = :cid
          AND DATE(start_ts) BETWEEN :from_d AND :to_d
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

    try:
        customer = await _fetch_customer(db, customer_id)
        daily    = await _fetch_daily(db, customer_id, period_start, period_end)
        pdf_path = _generate_pdf(inv_id, customer, period_start, period_end,
                                 totals, daily, subtotal, tax_amount, total)
        if pdf_path:
            await db.execute(text("UPDATE invoices SET pdf_path=:p WHERE id=:id"),
                             {"p": str(pdf_path), "id": inv_id})
            await db.commit()
    except Exception:
        pass

    return {"id": inv_id, "total": total, "pdf": f"/api/admin/invoices/{inv_id}/pdf"}


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
    pdf_path = _generate_pdf(
        inv_id, customer,
        str(row["period_start"]), str(row["period_end"]),
        totals, daily,
        float(row["subtotal"]), float(row["tax_amount"]), float(row["total"])
    )
    if not pdf_path:
        raise HTTPException(500, "No se pudo generar el PDF — revisa logs del backend")

    await db.execute(text("UPDATE invoices SET pdf_path=:p WHERE id=:id"),
                     {"p": str(pdf_path), "id": inv_id})
    await db.commit()
    return {"ok": True, "pdf": f"/api/admin/invoices/{inv_id}/pdf"}


@router.post("/{inv_id}/mark-paid")
async def mark_paid(inv_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(text("UPDATE invoices SET status='paid', paid_at=NOW() WHERE id=:id"), {"id": inv_id})
    await db.commit()
    return {"ok": True}


def _generate_pdf(inv_id, customer: dict, period_start, period_end,
                  totals, daily: list, subtotal, tax_amount, total) -> Path | None:
    try:
        from fpdf import FPDF, XPos, YPos
    except ImportError:
        return None

    try:
        INVOICES_DIR.mkdir(parents=True, exist_ok=True)

        pdf = FPDF()
        pdf.add_page()
        pdf.set_margins(20, 20, 20)
        NL = {"new_x": XPos.LMARGIN, "new_y": YPos.NEXT}

        # ── Encabezado ────────────────────────────────────────────────────────
        pdf.set_font("Helvetica", "B", 20)
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
        row("TOTAL",                f"S/ {total:,.4f}", bold=True)

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

        path = INVOICES_DIR / f"invoice-{inv_id}.pdf"
        pdf.output(str(path))
        return path

    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("PDF generation failed for invoice %s: %s", inv_id, exc, exc_info=True)
        return None
