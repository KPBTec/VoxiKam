# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Re-auditoría v2.56.0, hallazgo CRÍTICO: billingblock=0 no estaba validado en
ningún modelo Pydantic — rating.py::billable_blocks() hace
math.ceil((seconds-initblock)/billingblock), ZeroDivisionError garantizado.
Este archivo fija que los 7 modelos afectados rechazan billingblock<=0.
"""
import pytest
from pydantic import ValidationError

from routers.rates import RateIn, GroupRateIn
from routers.carriers import BuyRateIn, GroupBuyRateIn
from routers.reseller import RateIn as ResellerRateIn, GroupRateIn as ResellerGroupRateIn
from routers.reseller import CarrierBuyRateIn, CarrierGroupBuyRateIn
from routers.pricelists import DraftItemIn

MODELS_WITH_BILLINGBLOCK = [
    (RateIn, dict(prefix_id=1, rateinitial=0.02)),
    (GroupRateIn, dict(group_name="LATAM", rateinitial=0.02)),
    (BuyRateIn, dict(prefix_id=1, buy_rate=0.01)),
    (GroupBuyRateIn, dict(group_name="LATAM", buy_rate=0.01)),
    (ResellerRateIn, dict(prefix_id=1, rateinitial=0.02)),
    (ResellerGroupRateIn, dict(group_name="LATAM", rateinitial=0.02)),
    (CarrierBuyRateIn, dict(prefix_id=1, buy_rate=0.01)),
    (CarrierGroupBuyRateIn, dict(group_name="LATAM", buy_rate=0.01)),
    (DraftItemIn, dict(prefix_id=1, rateinitial=0.02)),
]


@pytest.mark.parametrize("model, base_kwargs", MODELS_WITH_BILLINGBLOCK,
                         ids=[m.__module__ + "." + m.__qualname__ for m, _ in MODELS_WITH_BILLINGBLOCK])
class TestBillingblockValidation:
    def test_rejects_zero(self, model, base_kwargs):
        with pytest.raises(ValidationError):
            model(**base_kwargs, billingblock=0)

    def test_rejects_negative(self, model, base_kwargs):
        with pytest.raises(ValidationError):
            model(**base_kwargs, billingblock=-1)

    def test_accepts_default(self, model, base_kwargs):
        instance = model(**base_kwargs)
        assert instance.billingblock == 1

    def test_accepts_positive(self, model, base_kwargs):
        instance = model(**base_kwargs, billingblock=60)
        assert instance.billingblock == 60


INITBLOCK_MODELS = [
    (RateIn, dict(prefix_id=1, rateinitial=0.02)),
    (GroupRateIn, dict(group_name="LATAM", rateinitial=0.02)),
    (ResellerRateIn, dict(prefix_id=1, rateinitial=0.02)),
    (ResellerGroupRateIn, dict(group_name="LATAM", rateinitial=0.02)),
]


@pytest.mark.parametrize("model, base_kwargs", INITBLOCK_MODELS,
                         ids=[m.__module__ + "." + m.__qualname__ for m, _ in INITBLOCK_MODELS])
class TestInitblockValidation:
    def test_rejects_negative(self, model, base_kwargs):
        with pytest.raises(ValidationError):
            model(**base_kwargs, initblock=-1)

    def test_accepts_zero(self, model, base_kwargs):
        """initblock=0 SÍ es válido — significa "sin bloque inicial", a
        diferencia de billingblock=0 (que rompe la división)."""
        instance = model(**base_kwargs, initblock=0)
        assert instance.initblock == 0
