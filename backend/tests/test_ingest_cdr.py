# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Caracterización de routers/cdrs.py::ingest_cdr() — el camino SÍNCRONO de
facturación (el que de verdad corre en producción para llamadas nuevas).
A diferencia de main.py::_calc_bill(), acá también se normaliza dst_number
(quitar techprefix del cliente y outbound_prefix del carrier) ANTES de
buscar tarifa — si esa normalización se rompe, el longest-prefix-match no
matchea nada y la llamada se factura en $0 silenciosamente. Estos tests
fijan ese comportamiento.

check_balance_alert se reemplaza por un no-op: sus propias queries
(customers, balance_alert_rules) son responsabilidad de
tests/test_alerts.py-que-no-existe-todavía, no de esta suite — acá interesa
la matemática de facturación, no el efecto secundario del correo de alerta.
"""
import pytest

from routers import cdrs
from tests.fakes import FakeBackgroundTasks, FakeRow, FakeSession


@pytest.fixture(autouse=True)
def _stub_balance_alert(monkeypatch):
    async def _noop(db, customer_id):
        return None
    monkeypatch.setattr(cdrs, "check_balance_alert", _noop)


def is_customer_ip_lookup(sql, params):
    return "customer_ips" in sql


def is_techprefix_lookup(sql, params):
    return "techprefix FROM customers" in sql


def is_carrier_host_lookup(sql, params):
    return "FROM carriers WHERE host" in sql


def is_outbound_prefix_lookup(sql, params):
    return "outbound_prefix FROM carriers" in sql


def is_buy_rate_query(sql, params):
    return "carrier_rates" in sql


def is_reseller_rate_query(sql, params):
    return "rate_plan_id" in sql and "pid" in params


def is_sell_rate_query(sql, params):
    return "rate_plan_id" in sql and "cid" in params and "carrier_rates" not in sql


def is_balance_select(sql, params):
    return "SELECT balance FROM customers" in sql


def make_body(**overrides):
    defaults = dict(
        call_id="call-1", src_ip="10.0.0.5", src_number="5199999999",
        dst_number="800199999999999", carrier_host="carrier.example.com",
        billsec=90, sessiontime=95, disposition="ANSWERED", sip_code=200,
    )
    defaults.update(overrides)
    return cdrs.CdrIngestIn(**defaults)


def make_session(*, customer_ip_rows=(), techprefix_rows=(), carrier_host_rows=(),
                  outbound_prefix_rows=(), buy_rows=(), sell_rows=(), reseller_rows=()):
    return FakeSession([
        (is_customer_ip_lookup, customer_ip_rows),
        (is_techprefix_lookup, techprefix_rows),
        (is_carrier_host_lookup, carrier_host_rows),
        (is_outbound_prefix_lookup, outbound_prefix_rows),
        (is_buy_rate_query, buy_rows),
        (is_reseller_rate_query, reseller_rows),
        (is_sell_rate_query, sell_rows),
        (is_balance_select, [FakeRow(balance=42.0)]),
    ])


def get_insert_params(db):
    inserts = db.sql_calls_matching("INSERT INTO cdrs")
    assert len(inserts) == 1, "se esperaba exactamente un INSERT INTO cdrs"
    return inserts[0][1]


@pytest.mark.asyncio
async def test_techprefix_and_outbound_prefix_are_stripped_before_rating():
    # cliente con techprefix "8001", dst enviado como 8001+número real.
    # carrier con outbound_prefix "00" — Kamailio puede haber reescrito el
    # R-URI antes de generar el CDR, este endpoint tiene que revertirlo.
    db = make_session(
        customer_ip_rows=[FakeRow(customer_id=7)],
        techprefix_rows=[FakeRow(techprefix="8001")],
        carrier_host_rows=[FakeRow(id=5)],
        outbound_prefix_rows=[FakeRow(outbound_prefix="00")],
        buy_rows=[FakeRow(buy_rate=0.01, billingblock=60, connectcharge=0.0)],
        sell_rows=[FakeRow(rateinitial=0.02, initblock=0, billingblock=60, connectcharge=0.0,
                            minimal_time_charge=0, prefix="51", parent_customer_id=None)],
    )
    body = make_body(dst_number="800100519999999")  # techprefix 8001 + "00" outbound + "519999999"
    resp = await cdrs.ingest_cdr(body, FakeBackgroundTasks(), db)

    insert_params = get_insert_params(db)
    # 8001 se quita primero (techprefix del cliente), después 00 (outbound del carrier)
    assert insert_params["dst_number"] == "519999999"
    assert insert_params["prefix_matched"] == "51"
    assert resp["buycost"] > 0 and resp["sessionbill"] > 0


@pytest.mark.asyncio
async def test_unknown_source_ip_never_matches_customer_and_bills_nothing():
    db = make_session(customer_ip_rows=[])  # IP no registrada en customer_ips
    body = make_body(src_ip="203.0.113.9")
    resp = await cdrs.ingest_cdr(body, FakeBackgroundTasks(), db)

    insert_params = get_insert_params(db)
    assert insert_params["customer_id"] is None
    assert resp["sessionbill"] == 0.0
    # sin customer_id, nunca se debería tocar el balance
    assert not db.sql_calls_matching("UPDATE customers SET balance")


@pytest.mark.asyncio
async def test_sessionbill_debits_customer_balance():
    db = make_session(
        customer_ip_rows=[FakeRow(customer_id=7)],
        techprefix_rows=[FakeRow(techprefix="")],
        sell_rows=[FakeRow(rateinitial=0.02, initblock=0, billingblock=60, connectcharge=0.0,
                            minimal_time_charge=0, prefix="51", parent_customer_id=None)],
    )
    body = make_body(dst_number="51999999999", carrier_host="")
    resp = await cdrs.ingest_cdr(body, FakeBackgroundTasks(), db)

    assert resp["sessionbill"] > 0
    debit_calls = db.sql_calls_matching("UPDATE customers SET balance")
    assert len(debit_calls) == 1
    assert debit_calls[0][1]["bill"] == resp["sessionbill"]
    assert db.sql_calls_matching("INSERT INTO balance_transactions")
    assert db.committed


@pytest.mark.asyncio
async def test_zero_billsec_call_bills_nothing_and_skips_balance_update():
    db = make_session(
        customer_ip_rows=[FakeRow(customer_id=7)],
        sell_rows=[FakeRow(rateinitial=0.02, initblock=0, billingblock=60, connectcharge=0.0,
                            minimal_time_charge=0, prefix="51", parent_customer_id=None)],
    )
    body = make_body(dst_number="51999999999", billsec=0, disposition="NO_ANSWER")
    resp = await cdrs.ingest_cdr(body, FakeBackgroundTasks(), db)

    assert resp["buycost"] == 0.0
    assert resp["sessionbill"] == 0.0
    assert not db.sql_calls_matching("UPDATE customers SET balance")
    insert_params = get_insert_params(db)
    assert insert_params["call_state"] == "CANCELLED"  # _state_map["NO_ANSWER"]


@pytest.mark.asyncio
async def test_background_task_dispatches_cdr_created_event():
    db = make_session(customer_ip_rows=[])
    bg = FakeBackgroundTasks()
    body = make_body()
    await cdrs.ingest_cdr(body, bg, db)

    assert len(bg.tasks) == 1
    func, args, kwargs = bg.tasks[0]
    assert func.__name__ == "dispatch_event"
    assert args[0] == "cdr.created"
    assert args[1]["call_id"] == "call-1"
