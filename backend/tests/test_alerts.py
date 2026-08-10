# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Caracterización de alerts.py::check_balance_alert(). El test central de este
archivo (test_prepago_multiple_thresholds_crossed_notifies_most_severe) se
escribió ANTES de corregir el bug de la re-auditoría v2.56.0 ("check_balance_alert()
nunca escala a la alerta más severa para clientes prepago") — corría en rojo
contra el código viejo (la rama prepago no tenía el `break` que sí tiene la
rama postpago dos líneas más abajo), confirmando el hallazgo, y pasa a verde
después del fix de una línea. Es la red de seguridad para que esto no vuelva
a romperse en silencio.
"""
import pytest

import alerts
from tests.fakes import FakeRow, FakeSession, WithRowcount


def is_customer_lookup(sql, params):
    return "FROM customers WHERE id" in sql


def is_rules_lookup(sql, params):
    return "FROM balance_alert_rules" in sql


def is_settings_lookup(sql, params):
    return "FROM settings" in sql


def is_alert_update(sql, params):
    return "UPDATE customers SET last_alert_rule_id" in sql


async def _fake_dispatch_event(*args, **kwargs):
    return None


def make_session(*, customer, rules, update_rowcount=1):
    return FakeSession([
        (is_customer_lookup, [customer]),
        (is_rules_lookup, rules),
        (is_settings_lookup, []),
        (is_alert_update, WithRowcount([], update_rowcount)),
    ])


@pytest.fixture(autouse=True)
def _stub_side_effects(monkeypatch):
    sent = []

    async def fake_send_email(db, **kwargs):
        sent.append(kwargs)
        return True

    monkeypatch.setattr(alerts, "send_email", fake_send_email)
    monkeypatch.setattr(alerts, "dispatch_event", _fake_dispatch_event)
    return sent


@pytest.mark.asyncio
async def test_prepago_single_threshold_crossed_notifies(_stub_side_effects):
    sent = _stub_side_effects
    customer = FakeRow(id=7, name="Acme", balance=250.0, billing_type="prepago",
                        last_topup_amount=1000.0, last_alert_rule_id=None)
    rules = [FakeRow(id=1, label="30%", threshold=30), FakeRow(id=2, label="20%", threshold=20)]
    db = make_session(customer=customer, rules=rules)

    await alerts.check_balance_alert(db, 7)

    assert len(sent) == 1
    assert "30%" in sent[0]["subject"]


@pytest.mark.asyncio
async def test_prepago_multiple_thresholds_crossed_notifies_most_severe(_stub_side_effects):
    """
    Cliente prepago con reglas 30%/20% (la config semilla real, ver
    db/schema.sql) ya notificado en el umbral del 30% (last_alert_rule_id=1).
    El balance cae directo a 15% — cruza AMBOS umbrales en la misma
    evaluación. Se espera que se notifique el 20% (más severo, y distinto
    del ya notificado) — no que se quede callado porque la iteración sin
    `break` termina sobreescribiendo `breached` con la regla del 30% ya
    notificada.
    """
    sent = _stub_side_effects
    customer = FakeRow(id=7, name="Acme", balance=150.0, billing_type="prepago",
                        last_topup_amount=1000.0, last_alert_rule_id=1)
    rules = [FakeRow(id=1, label="30%", threshold=30), FakeRow(id=2, label="20%", threshold=20)]
    db = make_session(customer=customer, rules=rules)

    await alerts.check_balance_alert(db, 7)

    update_calls = db.sql_calls_matching("UPDATE customers SET last_alert_rule_id")
    assert len(update_calls) == 1, "se esperaba que SÍ se notifique el umbral del 20%, más severo"
    assert update_calls[0][1]["rid"] == 2, "debería quedarse con la regla del 20% (id=2), no la del 30% ya notificada"
    assert len(sent) == 1
    assert "20%" in sent[0]["subject"]


@pytest.mark.asyncio
async def test_postpago_multiple_thresholds_crossed_already_notifies_most_severe(_stub_side_effects):
    """Control: la rama postpago ya tiene el `break` — sirve como referencia
    de que el comportamiento correcto (escalar a la más severa) es alcanzable
    con el mismo tipo de configuración, solo para la otra rama."""
    sent = _stub_side_effects
    customer = FakeRow(id=9, name="Beta SRL", balance=-500.0, billing_type="postpago",
                        last_topup_amount=None, last_alert_rule_id=10)
    # postpago: threshold negativo, más severo = más negativo. Reglas ya ordenadas más negativo primero.
    rules = [FakeRow(id=11, label="-100", threshold=-100), FakeRow(id=10, label="-50", threshold=-50)]
    db = make_session(customer=customer, rules=rules)

    await alerts.check_balance_alert(db, 9)

    update_calls = db.sql_calls_matching("UPDATE customers SET last_alert_rule_id")
    assert len(update_calls) == 1
    assert update_calls[0][1]["rid"] == 11
    assert "-100" in sent[0]["subject"]


@pytest.mark.asyncio
async def test_already_notified_the_only_breached_rule_does_not_renotify(_stub_side_effects):
    sent = _stub_side_effects
    customer = FakeRow(id=7, name="Acme", balance=250.0, billing_type="prepago",
                        last_topup_amount=1000.0, last_alert_rule_id=1)
    rules = [FakeRow(id=1, label="30%", threshold=30), FakeRow(id=2, label="20%", threshold=20)]
    db = make_session(customer=customer, rules=rules)

    await alerts.check_balance_alert(db, 7)

    assert not db.sql_calls_matching("UPDATE customers SET last_alert_rule_id")
    assert len(sent) == 0


@pytest.mark.asyncio
async def test_no_topup_recorded_never_updates_or_notifies(_stub_side_effects):
    """La query de reglas SÍ corre siempre (pasa antes del check de
    last_topup_amount en el código real) — lo que importa es que sin
    recarga registrada no hay referencia para calcular % y no debe evaluarse
    ningún breach ni enviarse ninguna notificación."""
    sent = _stub_side_effects
    db = FakeSession([
        (is_customer_lookup, [FakeRow(id=7, name="Acme", balance=100.0, billing_type="prepago",
                                       last_topup_amount=None, last_alert_rule_id=None)]),
        (is_rules_lookup, [FakeRow(id=1, label="30%", threshold=30)]),
    ])
    await alerts.check_balance_alert(db, 7)
    assert not db.sql_calls_matching("UPDATE customers SET last_alert_rule_id")
    assert len(sent) == 0


@pytest.mark.asyncio
async def test_balance_back_above_all_thresholds_clears_last_alert_rule_id():
    customer = FakeRow(id=7, name="Acme", balance=900.0, billing_type="prepago",
                        last_topup_amount=1000.0, last_alert_rule_id=1)
    rules = [FakeRow(id=1, label="30%", threshold=30), FakeRow(id=2, label="20%", threshold=20)]
    db = FakeSession([
        (is_customer_lookup, [customer]),
        (is_rules_lookup, rules),
    ])
    await alerts.check_balance_alert(db, 7)
    clear_calls = db.sql_calls_matching("SET last_alert_rule_id = NULL")
    assert len(clear_calls) == 1
    assert clear_calls[0][1]["id"] == 7


@pytest.mark.asyncio
async def test_concurrent_calls_only_one_sends_the_alert(_stub_side_effects):
    """
    Regresión de seguridad de v2.56.0: el UPDATE condicional
    (`WHERE last_alert_rule_id IS NULL OR last_alert_rule_id != :rid`) es lo
    que evita el envío duplicado si dos CDRs del mismo cliente cruzan el
    umbral casi al mismo tiempo en dos procesos (--workers>1). Simulado acá
    forzando rowcount=0 en el UPDATE (como si otro proceso ya lo hubiera
    marcado un instante antes) — check_balance_alert() debe retornar sin
    enviar nada.
    """
    sent = _stub_side_effects
    customer = FakeRow(id=7, name="Acme", balance=250.0, billing_type="prepago",
                        last_topup_amount=1000.0, last_alert_rule_id=None)
    rules = [FakeRow(id=1, label="30%", threshold=30), FakeRow(id=2, label="20%", threshold=20)]
    db = make_session(customer=customer, rules=rules, update_rowcount=0)

    await alerts.check_balance_alert(db, 7)

    assert len(sent) == 0
