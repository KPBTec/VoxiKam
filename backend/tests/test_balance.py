# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Caracterización de balance.py::apply_balance_change() — la extracción
compartida detrás de customers.py::adjust_balance() y
reseller.py::adjust_sub_customer_balance() (ver docstring de balance.py para
qué NO está migrado todavía y por qué). Estos tests fijan exactamente el SQL
que dispara — columnas del INSERT, orden de UPDATE→SELECT→INSERT, y el
scoping extra vía extra_where/extra_params — para poder migrar los otros 4
call sites más adelante con la misma confianza.
"""
import pytest

from balance import apply_balance_change
from tests.fakes import FakeRow, FakeSession


def make_session(balance_after: float):
    return FakeSession([
        (lambda sql, params: "SELECT balance FROM customers" in sql, [FakeRow(balance=balance_after)]),
    ])


@pytest.mark.asyncio
async def test_credit_updates_reads_back_and_inserts_ledger_row():
    db = make_session(balance_after=142.5)
    new_balance = await apply_balance_change(
        db, customer_id=7, amount=42.5, type="manual",
        reference="Ajuste manual desde panel", created_by="admin@acme.com",
    )
    assert new_balance == 142.5

    update_calls = db.sql_calls_matching("UPDATE customers SET balance = balance + :amount WHERE id = :id")
    assert len(update_calls) == 1
    assert update_calls[0][1] == {"amount": 42.5, "id": 7}

    insert_calls = db.sql_calls_matching("INSERT INTO balance_transactions")
    assert len(insert_calls) == 1
    p = insert_calls[0][1]
    assert p == {"cid": 7, "type": "manual", "amount": 42.5, "bal": 142.5,
                 "ref": "Ajuste manual desde panel", "by": "admin@acme.com"}


@pytest.mark.asyncio
async def test_negative_amount_is_a_debit():
    db = make_session(balance_after=-10.0)
    new_balance = await apply_balance_change(
        db, customer_id=3, amount=-25.0, type="cdr", reference="call-123",
    )
    assert new_balance == -10.0
    update_calls = db.sql_calls_matching("UPDATE customers SET balance = balance + :amount")
    assert update_calls[0][1]["amount"] == -25.0


@pytest.mark.asyncio
async def test_created_by_defaults_to_none_when_omitted():
    db = make_session(balance_after=5.0)
    await apply_balance_change(db, customer_id=1, amount=5.0, type="cdr", reference="call-1")
    insert_calls = db.sql_calls_matching("INSERT INTO balance_transactions")
    assert insert_calls[0][1]["by"] is None


@pytest.mark.asyncio
async def test_extra_where_and_params_scope_the_update():
    """Caso reseller.py::adjust_sub_customer_balance() — el reseller no puede
    tocar el balance de un cliente que no es su propio sub-cliente."""
    db = make_session(balance_after=99.0)
    await apply_balance_change(
        db, customer_id=55, amount=20.0, type="manual",
        reference="Ajuste manual desde panel reseller", created_by="reseller@acme.com",
        extra_where=" AND parent_customer_id = :pid", extra_params={"pid": 12},
    )
    update_calls = db.sql_calls_matching("UPDATE customers SET balance")
    sql, params = update_calls[0]
    assert "AND parent_customer_id = :pid" in sql
    assert params == {"amount": 20.0, "id": 55, "pid": 12}


@pytest.mark.asyncio
async def test_does_not_commit_caller_controls_transaction():
    db = make_session(balance_after=10.0)
    await apply_balance_change(db, customer_id=1, amount=10.0, type="manual", reference="x")
    assert db.committed is False
