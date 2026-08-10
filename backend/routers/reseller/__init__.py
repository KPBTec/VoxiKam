# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Panel del reseller — un cliente con customers.is_reseller=1 que administra
sus propios sub-clientes y sus propios rate plans (rate_plans.owner_customer_id).

No reusa backend/routers/customers.py ni rates.py tal cual — esos son 100%
admin, sin scope. Acá CADA query lleva `parent_customer_id`/`owner_customer_id`
incondicional, para que sea estructuralmente imposible que un reseller vea o
edite datos de otro reseller o de la plataforma.

Este paquete agrupa los endpoints por recurso — ver _shared.py (modelos y
helpers comunes), sub_customers.py, carriers.py, rate_plans.py,
carrier_groups.py, dashboard.py y billing_recalc.py.
"""
from fastapi import APIRouter

from . import billing_recalc, carrier_groups, carriers, dashboard, rate_plans, sub_customers
from ._shared import CarrierBuyRateIn, CarrierGroupBuyRateIn, GroupRateIn, RateIn

router = APIRouter()
router.include_router(sub_customers.router)
router.include_router(carriers.router)
router.include_router(rate_plans.router)
router.include_router(carrier_groups.router)
router.include_router(dashboard.router)
router.include_router(billing_recalc.router)
