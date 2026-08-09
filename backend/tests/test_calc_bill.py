# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Caracterización de main.py::_calc_bill() — el cálculo de tarifas del camino
de RESPALDO (_billing_worker, para CDRs que quedaron con buycost=0). Usa
FakeSession (tests/fakes.py) en vez de una DB real: estos tests fijan el
comportamiento actual (longest-prefix-match, cascada de reseller,
redondeo a 6 decimales) para poder tocar esta función con confianza más
adelante — arrancando por la extracción a un rating.py compartido con
routers/cdrs.py (hallazgo de auditoría v2.55).
"""
import pytest

from main import _calc_bill
from tests.fakes import FakeRow, FakeSession


def is_buy_rate_query(sql, params):
    return "carrier_rates" in sql


def is_reseller_rate_query(sql, params):
    return "rate_plan_id" in sql and "pid" in params


def is_sell_rate_query(sql, params):
    return "rate_plan_id" in sql and "cid" in params and "carrier_rates" not in sql


def make_session(buy_rows=(), sell_rows=(), reseller_rows=()):
    return FakeSession([
        (is_buy_rate_query, buy_rows),
        (is_reseller_rate_query, reseller_rows),
        (is_sell_rate_query, sell_rows),
    ])


@pytest.mark.asyncio
async def test_zero_billsec_never_queries_and_returns_all_zero():
    db = make_session(
        buy_rows=[FakeRow(buy_rate=0.01, billingblock=60, connectcharge=0.0)],
        sell_rows=[FakeRow(rateinitial=0.02, initblock=0, billingblock=60, connectcharge=0.0,
                            minimal_time_charge=0, prefix="51", parent_customer_id=None)],
    )
    result = await _calc_bill(db, customer_id=7, carrier_id=5, dst="51999999999", billsec=0)
    assert result == (0.0, 0.0, None, None)
    assert db.calls == []  # billsec=0 -> ni siquiera se intenta el lookup


@pytest.mark.asyncio
async def test_no_carrier_no_customer_returns_zero():
    db = make_session()
    result = await _calc_bill(db, customer_id=None, carrier_id=None, dst="51999999999", billsec=90)
    assert result == (0.0, 0.0, None, None)


@pytest.mark.asyncio
async def test_buy_rate_only_no_matching_customer():
    db = make_session(
        buy_rows=[FakeRow(buy_rate=0.01, billingblock=60, connectcharge=0.005)],
    )
    buycost, sessionbill, reseller_cost, matched_prefix = await _calc_bill(
        db, customer_id=None, carrier_id=5, dst="51999999999", billsec=90,
    )
    # blocks = _billable_blocks(90, 0, 60) = 120 -> 120/60*0.01 + 0.005 = 0.025
    assert buycost == 0.025
    assert sessionbill == 0.0
    assert reseller_cost is None
    assert matched_prefix is None


@pytest.mark.asyncio
async def test_sell_rate_only_no_matching_carrier():
    db = make_session(
        sell_rows=[FakeRow(rateinitial=0.02, initblock=30, billingblock=6, connectcharge=0.0,
                            minimal_time_charge=0, prefix="51", parent_customer_id=None)],
    )
    buycost, sessionbill, reseller_cost, matched_prefix = await _calc_bill(
        db, customer_id=7, carrier_id=None, dst="51999999999", billsec=45,
    )
    # billable = max(45,0) = 45; blocks = _billable_blocks(45,30,6) = 30 + ceil(15/6)*6 = 48
    # sessionbill = 48/60*0.02 + 0 = 0.016
    assert buycost == 0.0
    assert sessionbill == 0.016
    assert reseller_cost is None
    assert matched_prefix == "51"


@pytest.mark.asyncio
async def test_minimal_time_charge_floors_billable_seconds():
    db = make_session(
        sell_rows=[FakeRow(rateinitial=0.06, initblock=0, billingblock=60, connectcharge=0.0,
                            minimal_time_charge=30, prefix="51", parent_customer_id=None)],
    )
    # billsec=5 pero minimal_time_charge=30 -> se factura como si hubiera durado 30s
    _, sessionbill, _, _ = await _calc_bill(db, customer_id=7, carrier_id=None, dst="51999999999", billsec=5)
    # billable = max(5,30) = 30; blocks = _billable_blocks(30,0,60) = 60; 60/60*0.06 = 0.06
    assert sessionbill == 0.06


@pytest.mark.asyncio
async def test_reseller_cascade_computes_reseller_cost_independently():
    db = make_session(
        sell_rows=[FakeRow(rateinitial=0.02, initblock=0, billingblock=60, connectcharge=0.0,
                            minimal_time_charge=0, prefix="51", parent_customer_id=42)],
        reseller_rows=[FakeRow(rateinitial=0.015, initblock=0, billingblock=60, connectcharge=0.0,
                                minimal_time_charge=0)],
    )
    _, sessionbill, reseller_cost, _ = await _calc_bill(
        db, customer_id=7, carrier_id=None, dst="51999999999", billsec=90,
    )
    # blocks = _billable_blocks(90,0,60) = 120
    assert sessionbill == round(120 / 60 * 0.02, 6)
    assert reseller_cost == round(120 / 60 * 0.015, 6)
    # margen plataforma = reseller_cost - buycost; margen reseller = sessionbill - reseller_cost
    assert sessionbill > reseller_cost  # el reseller le vende más caro al sub-cliente que lo que le cuesta


@pytest.mark.asyncio
async def test_no_parent_customer_never_queries_reseller_rate():
    db = make_session(
        sell_rows=[FakeRow(rateinitial=0.02, initblock=0, billingblock=60, connectcharge=0.0,
                            minimal_time_charge=0, prefix="51", parent_customer_id=None)],
    )
    _, _, reseller_cost, _ = await _calc_bill(db, customer_id=7, carrier_id=None, dst="51999999999", billsec=90)
    assert reseller_cost is None
    assert not db.sql_calls_matching("pid")  # nunca se ejecutó la query de reseller


@pytest.mark.asyncio
async def test_no_matching_prefix_leaves_buycost_zero():
    db = make_session(buy_rows=[])  # sin fila -> sin match de prefijo
    buycost, _, _, _ = await _calc_bill(db, customer_id=None, carrier_id=5, dst="99999999999", billsec=90)
    assert buycost == 0.0


@pytest.mark.asyncio
async def test_rounds_to_six_decimals():
    db = make_session(
        buy_rows=[FakeRow(buy_rate=0.0123456789, billingblock=1, connectcharge=0.0)],
    )
    buycost, _, _, _ = await _calc_bill(db, customer_id=None, carrier_id=5, dst="51999999999", billsec=1)
    assert buycost == round(1 / 60 * 0.0123456789, 6)
    assert len(str(buycost).split(".")[-1]) <= 6
