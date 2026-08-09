# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Caracterización de rating.billable_blocks(): el cálculo más chico y con más
impacto de plata de todo el backend (define cuántos "minutos" se cobran de
cada llamada).

Hasta la extracción a rating.py (auditoría v2.55, hallazgo "extraer rating.py
compartido") esto existía DUPLICADO byte a byte en main.py (camino de
respaldo, _billing_worker) y routers/cdrs.py (camino síncrono, ingest_cdr).
Este archivo se escribió originalmente contra esas dos copias — ahora que
main.py y routers/cdrs.py importan la MISMA función desde rating.py, no hay
nada que puedan divergir entre sí; el test de identidad de abajo
(test_both_callers_use_the_same_function_object) es la red de seguridad
equivalente: si algún día alguien reintroduce una copia local en cualquiera
de los dos archivos, esto lo detecta.
"""
import pytest

import main as main_module
import rating
from routers import cdrs

billable_blocks = rating.billable_blocks


class TestBillableBlocksBehavior:
    def test_under_initblock_charges_full_initblock(self):
        # Llamada de 30s con initblock=60 igual cobra el bloque inicial completo.
        assert billable_blocks(30, 60, 6) == 60

    def test_exact_initblock_boundary(self):
        assert billable_blocks(60, 60, 6) == 60

    def test_rounds_up_remainder_to_next_billingblock(self):
        # 61s con initblock=60, billingblock=6 -> 60 + ceil(1/6)*6 = 66
        assert billable_blocks(61, 60, 6) == 66

    def test_zero_initblock_degenerates_to_plain_blocks(self):
        # carrier_rates no tiene columna initblock -> siempre 0 acá, y el
        # comportamiento histórico (pre-v2.38.0) era "todo en bloques de billingblock".
        assert billable_blocks(1, 0, 60) == 60
        assert billable_blocks(60, 0, 60) == 60
        assert billable_blocks(61, 0, 60) == 120

    def test_billingblock_of_one_second_is_passthrough(self):
        assert billable_blocks(37, 0, 1) == 37

    def test_zero_seconds_with_no_initblock(self):
        assert billable_blocks(0, 0, 60) == 0

    def test_zero_seconds_still_charges_initblock(self):
        assert billable_blocks(0, 60, 6) == 60


def test_both_callers_use_the_same_function_object():
    """
    main.py::_billable_blocks/_calc_bill y routers/cdrs.py::calc_bill son
    re-exports/imports directos de rating.py — no copias. Si algún día
    alguien "arregla algo rápido" reintroduciendo una copia local en
    cualquiera de los dos archivos, este assert de identidad (no de
    comportamiento) lo detecta inmediatamente, incluso antes de que el
    comportamiento llegue a divergir.
    """
    assert main_module._billable_blocks is rating.billable_blocks
    assert main_module._calc_bill is rating.calc_bill
    assert cdrs.calc_bill is rating.calc_bill
