# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Caracterización de routers/invoices.py — plan de remediación fase 3: la
generación de PDF/envío de email de facturas no tenía ningún test pese a que
CLAUDE.md documenta explícitamente la garantía "un fallo de envío nunca
revierte ni bloquea la generación de la factura". Este archivo la fija.
"""
import pytest

from routers.invoices import _send_invoice_email, mark_paid
from tests.fakes import FakeBackgroundTasks, FakeRow, FakeSession, WithRowcount


@pytest.fixture(autouse=True)
def _stub_check_balance_alert(monkeypatch):
    import routers.invoices as invoices_module

    async def _noop(db, customer_id):
        return None

    monkeypatch.setattr(invoices_module, "check_balance_alert", _noop)


@pytest.fixture(autouse=True)
def _stub_record_event(monkeypatch):
    import routers.invoices as invoices_module

    async def _noop(db, *args, **kwargs):
        return None

    monkeypatch.setattr(invoices_module, "record_event", _noop)


def _tmp_pdf(tmp_path):
    p = tmp_path / "invoice.pdf"
    p.write_bytes(b"%PDF-1.4 fake pdf content")
    return p


# ── _send_invoice_email: el fallo de envío no debe bloquear/revertir nada ───

@pytest.mark.asyncio
async def test_email_sent_successfully_marks_emailed_and_commits(monkeypatch, tmp_path):
    import routers.invoices as invoices_module

    async def fake_send_email(db, **kwargs):
        return True

    monkeypatch.setattr(invoices_module, "send_email", fake_send_email)
    db = FakeSession([])
    ok = await _send_invoice_email(
        db, inv_id=1, customer={"email": "cliente@acme.com", "name": "Acme"},
        pdf_path=_tmp_pdf(tmp_path), total=150.0, period_start="2026-07-01", period_end="2026-07-31",
    )
    assert ok is True
    assert db.sql_calls_matching("UPDATE invoices SET emailed_at")
    assert db.committed


@pytest.mark.asyncio
async def test_email_provider_failure_does_not_touch_invoice_status(monkeypatch, tmp_path):
    """La garantía central: si send_email() devuelve False (Resend caído,
    lo que sea), la factura YA GENERADA sigue como estaba — no se revierte,
    no se bloquea, simplemente no queda marcada como enviada."""
    import routers.invoices as invoices_module

    async def fake_send_email(db, **kwargs):
        return False

    monkeypatch.setattr(invoices_module, "send_email", fake_send_email)
    db = FakeSession([])
    ok = await _send_invoice_email(
        db, inv_id=1, customer={"email": "cliente@acme.com", "name": "Acme"},
        pdf_path=_tmp_pdf(tmp_path), total=150.0, period_start="2026-07-01", period_end="2026-07-31",
    )
    assert ok is False
    assert not db.sql_calls_matching("UPDATE invoices SET emailed_at")
    assert not db.committed


@pytest.mark.asyncio
async def test_customer_without_email_skips_send_without_touching_db(tmp_path):
    db = FakeSession([])
    ok = await _send_invoice_email(
        db, inv_id=1, customer={"email": "", "name": "Sin email SRL"},
        pdf_path=_tmp_pdf(tmp_path), total=10.0, period_start="2026-07-01", period_end="2026-07-31",
    )
    assert ok is False
    assert db.calls == []


@pytest.mark.asyncio
async def test_unreadable_pdf_path_returns_false_without_sending(monkeypatch, tmp_path):
    import routers.invoices as invoices_module
    called = []

    async def fake_send_email(db, **kwargs):
        called.append(True)
        return True

    monkeypatch.setattr(invoices_module, "send_email", fake_send_email)
    db = FakeSession([])
    ok = await _send_invoice_email(
        db, inv_id=1, customer={"email": "cliente@acme.com", "name": "Acme"},
        pdf_path=tmp_path / "no-existe.pdf", total=10.0, period_start="2026-07-01", period_end="2026-07-31",
    )
    assert ok is False
    assert called == []


@pytest.mark.asyncio
async def test_customer_name_with_html_is_escaped_in_email_body(monkeypatch, tmp_path):
    """HTML injection vía nombre de cliente — customers.py no bloquea tags,
    solo caracteres de control; el escape tiene que pasar acá."""
    import routers.invoices as invoices_module
    captured = {}

    async def fake_send_email(db, **kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(invoices_module, "send_email", fake_send_email)
    db = FakeSession([])
    await _send_invoice_email(
        db, inv_id=1, customer={"email": "x@acme.com", "name": "<script>alert(1)</script>"},
        pdf_path=_tmp_pdf(tmp_path), total=10.0, period_start="2026-07-01", period_end="2026-07-31",
    )
    assert "<script>" not in captured["html"]
    assert "&lt;script&gt;" in captured["html"]


# ── mark_paid: guarda atómica contra doble crédito ───────────────────────────

def is_invoice_lookup(sql, params):
    return "SELECT customer_id, total, balance_credited_at FROM invoices" in sql


def is_credit_gate(sql, params):
    return "SET balance_credited_at = NOW()" in sql


def is_balance_update(sql, params):
    return "UPDATE customers SET balance = balance +" in sql


def is_balance_select(sql, params):
    return "SELECT balance FROM customers" in sql


@pytest.mark.asyncio
async def test_mark_paid_credits_balance_on_first_call():
    db = FakeSession([
        (is_invoice_lookup, [FakeRow(customer_id=7, total=250.0, balance_credited_at=None)]),
        (is_credit_gate, WithRowcount([], 1)),
        (is_balance_select, [FakeRow(balance=250.0)]),
    ])
    resp = await mark_paid(inv_id=1, db=db, admin={"name": "Admin"})
    assert resp == {"ok": True}
    assert db.sql_calls_matching("UPDATE customers SET balance = balance +")
    assert db.sql_calls_matching("INSERT INTO balance_transactions")


@pytest.mark.asyncio
async def test_mark_paid_does_not_double_credit_if_already_credited():
    """Simula la carrera: el gate atómico afecta 0 filas (otro request ya
    marcó balance_credited_at un instante antes) — no debe acreditar de nuevo."""
    db = FakeSession([
        (is_invoice_lookup, [FakeRow(customer_id=7, total=250.0, balance_credited_at=None)]),
        (is_credit_gate, WithRowcount([], 0)),
    ])
    resp = await mark_paid(inv_id=1, db=db, admin={"name": "Admin"})
    assert resp == {"ok": True}
    assert not db.sql_calls_matching("UPDATE customers SET balance = balance +")
    assert not db.sql_calls_matching("INSERT INTO balance_transactions")


@pytest.mark.asyncio
async def test_mark_paid_unknown_invoice_raises_404():
    from fastapi import HTTPException
    db = FakeSession([(is_invoice_lookup, [])])
    with pytest.raises(HTTPException) as exc_info:
        await mark_paid(inv_id=999, db=db, admin={"name": "Admin"})
    assert exc_info.value.status_code == 404
