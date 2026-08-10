# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Modelos Pydantic, constantes y helpers compartidos por los submódulos del
panel reseller — ver backend/routers/reseller/__init__.py para la
descripción completa del panel.
"""
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sync_runner import run_sync

SCRIPTS = Path(__file__).parent.parent.parent.parent / "scripts"


def _sync():
    run_sync(SCRIPTS / "gen_dispatcher.py")
    run_sync(SCRIPTS / "gen_nftables.py")


def _my_cid(user: dict) -> int:
    return user["customer_id"]


class SubCustomerIn(BaseModel):
    name: str
    company: Optional[str] = None
    email: EmailStr
    phone: Optional[str] = None
    # Obligatorio a propósito, mismo criterio que customers.py::CustomerIn —
    # un sub-cliente sin plan nunca factura nada, en silencio. Debe ser un
    # plan propio del reseller (se valida al guardar).
    rate_plan_id: int
    # techprefix NO es un campo de entrada: siempre se autogenera en create_sub_customer()
    # y nunca cambia en update_sub_customer() — un reseller no conoce el gotcha de colisión
    # por substring de Kamailio (ver techprefix.techprefix_conflicts), así que no se le deja elegirlo.
    currency: str = "PEN"
    billing_type: str = "prepago"
    notes: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _name_no_control_chars(cls, v: str) -> str:
        """Mismo criterio que customers.py::CustomerIn._name_no_control_chars —
        se embebe sin escapar en un comentario del .cfg de Kamailio generado
        por scripts/gen_dispatcher.py, un salto de línea permitiría escapar
        del comentario e inyectar directivas arbitrarias."""
        if any(ord(c) < 32 or ord(c) == 127 for c in v):
            raise ValueError(
                "El nombre no puede contener saltos de línea ni caracteres de control — "
                "se usa tal cual en un comentario de la configuración de Kamailio generada"
            )
        return v

    @field_validator("company")
    @classmethod
    def _company_no_control_chars(cls, v: Optional[str]) -> Optional[str]:
        """Mismo criterio que customers.py::CustomerIn._company_no_control_chars."""
        if v and any(ord(c) < 32 or ord(c) == 127 for c in v):
            raise ValueError("company no puede contener saltos de línea ni caracteres de control")
        return v


class BalanceIn(BaseModel):
    amount: float


class PlanIn(BaseModel):
    name: str
    currency: str = "PEN"
    description: Optional[str] = None


class RateIn(BaseModel):
    prefix_id: int
    rateinitial: float
    connectcharge: float = 0.0
    # Re-auditoría v2.56.0 (hallazgo crítico): billingblock=0 hace que
    # rating.py::billable_blocks() dispare ZeroDivisionError.
    initblock: int = Field(default=1, ge=0)
    billingblock: int = Field(default=1, ge=1)
    minimal_time_charge: int = 0


class GroupRateIn(BaseModel):
    group_name: str
    rateinitial: float
    connectcharge: float = 0.0
    initblock: int = Field(default=1, ge=0)
    billingblock: int = Field(default=1, ge=1)


class PrefixIn(BaseModel):
    prefix: str
    destination: str
    group_name: str = ""
    country: Optional[str] = None


class CarrierIn(BaseModel):
    name: str
    host: str
    port: int = 5060
    priority: int = 10
    outbound_prefix: str = ""
    remove_prefix: str = ""
    status: str = "active"
    # NULL/vacío = sin límite — mismo criterio que carriers.py::CarrierIn.
    cps_limit: Optional[int] = None
    notes: Optional[str] = None

    @field_validator("cps_limit")
    @classmethod
    def _cps_limit_range(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1 <= v <= 65535):
            raise ValueError("cps_limit debe ser un número positivo (o vacío para sin límite)")
        return v


class CarrierBuyRateIn(BaseModel):
    prefix_id: int
    buy_rate: float
    connectcharge: float = 0.0
    billingblock: int = Field(default=1, ge=1)


class CarrierGroupBuyRateIn(BaseModel):
    group_name: str
    buy_rate: float
    connectcharge: float = 0.0
    billingblock: int = Field(default=1, ge=1)


class CustomerCarrierIn(BaseModel):
    carrier_id: int
    priority: int = 10


class CustomerCarrierGroupIn(BaseModel):
    group_id: int


class RoutingGroupIn(BaseModel):
    group_id: Optional[int] = None


class SubCustomerGroupIn(BaseModel):
    name: str
    algorithm: str = "priority"

    @field_validator("algorithm")
    @classmethod
    def _algorithm_valid(cls, v: str) -> str:
        if v not in ("priority", "round_robin", "percent"):
            raise ValueError("algorithm debe ser 'priority', 'round_robin' o 'percent'")
        return v

    @field_validator("name")
    @classmethod
    def _name_no_control_chars(cls, v: str) -> str:
        """Mismo criterio que customers.py::CustomerIn._name_no_control_chars."""
        if any(ord(c) < 32 or ord(c) == 127 for c in v):
            raise ValueError("El nombre no puede contener saltos de línea ni caracteres de control")
        return v


class GroupMemberIn(BaseModel):
    carrier_id: int
    priority: int = 10
    weight: Optional[int] = None

    @field_validator("weight")
    @classmethod
    def _weight_range(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1 <= v <= 100):
            raise ValueError("weight debe ser un número entre 1 y 100 (o vacío)")
        return v


class CustomerPrefixIn(BaseModel):
    # techprefix NO es un campo de entrada — se autogenera en
    # add_sub_customer_prefix() vía techprefix.next_campaign_prefix() (7000+).
    label: str = ""


_AUDITED_FIELDS = ["billing_type", "rate_plan_id", "techprefix"]  # subset de customers.py::_AUDITED_FIELDS — SubCustomerIn no tiene status/calllimit/cpslimit


async def _own_group_or_404(db: AsyncSession, gid: int, my_cid: int) -> None:
    r = await db.execute(text(
        "SELECT 1 FROM carrier_groups WHERE id = :id AND owner_customer_id = :cid"
    ), {"id": gid, "cid": my_cid})
    if not r.first():
        raise HTTPException(404, "Grupo no encontrado — solo podés editar/borrar los que vos creaste")
