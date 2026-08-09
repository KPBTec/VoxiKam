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
"""
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from alerts import check_balance_alert
from audit import diff_and_record, record_event
from auth import require_reseller_permission
from balance import apply_balance_change
from database import get_db
from techprefix import (
    techprefix_conflicts, next_campaign_prefix, next_sub_customer_prefix,
)
from routers.billing_recalc import RecalcRequest, _start_job, _read_job
from sync_runner import run_sync

router = APIRouter()
SCRIPTS = Path(__file__).parent.parent.parent / "scripts"


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
    initblock: int = 1
    billingblock: int = 1
    minimal_time_charge: int = 0


class GroupRateIn(BaseModel):
    group_name: str
    rateinitial: float
    connectcharge: float = 0.0
    initblock: int = 1
    billingblock: int = 1


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
    billingblock: int = 1


class CarrierGroupBuyRateIn(BaseModel):
    group_name: str
    buy_rate: float
    connectcharge: float = 0.0
    billingblock: int = 1


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


# ── Sub-clientes ────────────────────────────────────────────────────────────

@router.get("/sub-customers")
async def list_sub_customers(include_deleted: bool = False,
                              user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    # Mismo criterio que customers.py::list_customers() — desactivados
    # ocultos por defecto, no mezclados sin distinción con los activos.
    where = "" if include_deleted else "AND c.status != 'deleted'"
    r = await db.execute(text(f"""
        SELECT c.*, rp.name AS rate_plan_name
        FROM customers c
        LEFT JOIN rate_plans rp ON c.rate_plan_id = rp.id
        WHERE c.parent_customer_id = :pid {where}
        ORDER BY c.name
    """), {"pid": _my_cid(user)})
    return r.mappings().all()


@router.post("/sub-customers", status_code=201)
async def create_sub_customer(body: SubCustomerIn, user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)

    # rate_plan_id, si se manda, debe ser un plan propio del reseller — nunca
    # uno de la plataforma ni de otro reseller.
    if body.rate_plan_id:
        rp = await db.execute(text(
            "SELECT 1 FROM rate_plans WHERE id = :id AND owner_customer_id = :cid"
        ), {"id": body.rate_plan_id, "cid": my_cid})
        if not rp.first():
            raise HTTPException(400, "rate_plan_id no es un plan propio de este reseller")

    data = body.model_dump()
    data["techprefix"] = await next_sub_customer_prefix(db)   # siempre autogenerado, nunca desde el body
    data["parent_customer_id"] = my_cid   # nunca confiar en un valor mandado por el cliente
    result = await db.execute(text("""
        INSERT INTO customers (parent_customer_id, name, company, email, phone,
                               rate_plan_id, techprefix, currency, billing_type, notes)
        VALUES (:parent_customer_id, :name, :company, :email, :phone,
                :rate_plan_id, :techprefix, :currency, :billing_type, :notes)
    """), data)
    await record_event(db, "customer", result.lastrowid, "created_by_reseller",
                        user.get("name") or user.get("email"), f"{body.name} <{body.email}>")
    await db.commit()
    return {"id": result.lastrowid}


@router.get("/sub-customers/{cid}")
async def get_sub_customer(cid: int, user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    r = await db.execute(text("""
        SELECT c.*, rp.name AS rate_plan_name
        FROM customers c
        LEFT JOIN rate_plans rp ON c.rate_plan_id = rp.id
        WHERE c.id = :id AND c.parent_customer_id = :pid
    """), {"id": cid, "pid": _my_cid(user)})
    row = r.mappings().first()
    if not row:
        raise HTTPException(404, "Sub-cliente no encontrado")
    # Mismo criterio que customers.py::get_customer() — grupos HABILITADOS
    # para este sub-cliente (customer_carrier_groups), no todos los grupos
    # propios del reseller. Sin esto, el panel reseller no tenía forma de
    # saber qué ya está habilitado al reabrir un sub-cliente.
    groups = await db.execute(text("""
        SELECT ccg.group_id, ccg.display_label, cg.name, cg.algorithm
        FROM customer_carrier_groups ccg JOIN carrier_groups cg ON ccg.group_id = cg.id
        WHERE ccg.customer_id = :id
    """), {"id": cid})
    return {**dict(row), "groups": groups.mappings().all()}


@router.put("/sub-customers/{cid}")
async def update_sub_customer(cid: int, body: SubCustomerIn, user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    existing = await db.execute(text(
        "SELECT billing_type, rate_plan_id, techprefix FROM customers WHERE id = :id AND parent_customer_id = :pid"
    ), {"id": cid, "pid": my_cid})
    before_row = existing.mappings().first()
    if not before_row:
        raise HTTPException(404, "Sub-cliente no encontrado")
    before = dict(before_row)

    if body.rate_plan_id:
        rp = await db.execute(text(
            "SELECT 1 FROM rate_plans WHERE id = :id AND owner_customer_id = :cid"
        ), {"id": body.rate_plan_id, "cid": my_cid})
        if not rp.first():
            raise HTTPException(400, "rate_plan_id no es un plan propio de este reseller")

    data = body.model_dump(); data["id"] = cid; data["pid"] = my_cid
    data["techprefix"] = before["techprefix"]   # nunca editable por el reseller — fijado al crear
    await db.execute(text("""
        UPDATE customers SET name=:name, company=:company, email=:email, phone=:phone,
        rate_plan_id=:rate_plan_id, techprefix=:techprefix, currency=:currency,
        billing_type=:billing_type, notes=:notes
        WHERE id=:id AND parent_customer_id=:pid
    """), data)
    # Mismo criterio que customers.py::update_customer() — diff de campo, no
    # solo un evento genérico. Antes esta función no dejaba ningún rastro en
    # Auditoría, a diferencia de create_sub_customer() (record_event).
    await diff_and_record(db, "customer", cid, before, data, _AUDITED_FIELDS,
                           user.get("name") or user.get("email"))
    await db.commit()
    return {"ok": True}


@router.post("/sub-customers/{cid}/balance")
async def adjust_sub_customer_balance(cid: int, body: BalanceIn, user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    existing = await db.execute(text(
        "SELECT status FROM customers WHERE id = :id AND parent_customer_id = :pid"
    ), {"id": cid, "pid": my_cid})
    row = existing.first()
    if not row:
        raise HTTPException(404, "Sub-cliente no encontrado")
    if row[0] == "deleted":
        # Solo el admin puede reactivar (POST /admin/customers/{cid}/reactivate)
        # — el reseller no tiene ese endpoint, por eso el mensaje no le pide
        # que lo haga él mismo.
        raise HTTPException(409, "El sub-cliente está desactivado — pedile al administrador que lo reactive")

    new_balance = await apply_balance_change(
        db, cid, body.amount, type="manual", reference="Ajuste manual desde panel reseller",
        created_by=user.get("name") or user.get("email"),
        extra_where=" AND parent_customer_id = :pid", extra_params={"pid": my_cid},
    )
    await db.commit()
    # Mismo hook que customers.py::adjust_balance() — sin esto, un ajuste hecho
    # por un reseller nunca dispara la alerta de saldo bajo del operador.
    await check_balance_alert(db, cid)
    return {"ok": True, "balance": new_balance}


# ── Prefijos propios ─────────────────────────────────────────────────────────
# El reseller es un "mini admin" (mismo criterio que MagnusBilling): puede
# crear sus propios prefijos/destinos, igual que el admin crea los de la
# plataforma (backend/routers/rates.py). "El admin ve lo suyo y el reseller ve
# lo suyo" — cada quien administra (crea/edita/borra) solo lo que creó, pero
# el listado de abajo SÍ incluye los de la plataforma (owner NULL) además de
# los propios, porque el reseller necesita poder tarifar también destinos que
# ya existen (Lima, Provincia, etc.) al armar sus propios rate plans — nunca
# ve los prefijos privados de OTRO reseller. El motor de tarifación
# (cdrs.py::ingest_cdr) no filtra por owner: hace longest-prefix-match contra
# toda la tabla, así que un prefijo privado del reseller tarifa igual de bien
# en cuanto le carga una tarifa en su propio rate plan.

@router.get("/prefixes")
async def list_prefixes(user=Depends(require_reseller_permission("reseller_rates")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    r = await db.execute(text("""
        SELECT *, (owner_customer_id = :cid) AS is_own
        FROM prefixes
        WHERE owner_customer_id IS NULL OR owner_customer_id = :cid
        ORDER BY prefix
    """), {"cid": my_cid})
    return r.mappings().all()


@router.post("/prefixes", status_code=201)
async def create_prefix(body: PrefixIn, user=Depends(require_reseller_permission("reseller_rates")), db: AsyncSession = Depends(get_db)):
    dup = await db.execute(text("SELECT id FROM prefixes WHERE prefix = :prefix"), {"prefix": body.prefix})
    if dup.first():
        raise HTTPException(409, "Ya existe un prefijo con ese código")
    data = body.model_dump(); data["owner_customer_id"] = _my_cid(user)
    result = await db.execute(text("""
        INSERT INTO prefixes (prefix, destination, group_name, country, owner_customer_id)
        VALUES (:prefix, :destination, :group_name, :country, :owner_customer_id)
    """), data)
    await record_event(db, "prefix", result.lastrowid, "created_by_reseller",
                        user.get("name") or user.get("email"), f"{body.prefix} — {body.destination}")
    await db.commit()
    return {"id": result.lastrowid, "ok": True}


async def _own_prefix_or_404(db: AsyncSession, pid: int, my_cid: int) -> None:
    r = await db.execute(text(
        "SELECT 1 FROM prefixes WHERE id = :id AND owner_customer_id = :cid"
    ), {"id": pid, "cid": my_cid})
    if not r.first():
        raise HTTPException(404, "Prefijo no encontrado — solo podés editar/borrar los que vos creaste")


@router.put("/prefixes/{pid}")
async def update_prefix(pid: int, body: PrefixIn, user=Depends(require_reseller_permission("reseller_rates")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    await _own_prefix_or_404(db, pid, my_cid)
    dup = await db.execute(text("SELECT id FROM prefixes WHERE prefix = :prefix AND id != :id"),
                            {"prefix": body.prefix, "id": pid})
    if dup.first():
        raise HTTPException(409, "Ya existe un prefijo con ese código")
    r_before = await db.execute(text("SELECT * FROM prefixes WHERE id = :id"), {"id": pid})
    before = r_before.mappings().first()
    data = body.model_dump(); data["id"] = pid
    await db.execute(text(
        "UPDATE prefixes SET prefix=:prefix, destination=:destination, group_name=:group_name, country=:country WHERE id=:id"
    ), data)
    if before:
        await diff_and_record(db, "prefix", pid, dict(before), body.model_dump(),
                               ["prefix", "destination", "group_name"], user.get("name") or user.get("email"))
    await db.commit()
    return {"ok": True}


@router.delete("/prefixes/{pid}", status_code=204)
async def delete_prefix(pid: int, user=Depends(require_reseller_permission("reseller_rates")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    await _own_prefix_or_404(db, pid, my_cid)
    cnt = await db.execute(text("SELECT COUNT(*) FROM rates WHERE prefix_id = :id"), {"id": pid})
    if cnt.scalar() > 0:
        raise HTTPException(409, "Este prefijo tiene tarifas cargadas — bórralas antes de eliminarlo")
    r = await db.execute(text("SELECT prefix, destination FROM prefixes WHERE id = :id"), {"id": pid})
    row = r.first()
    await db.execute(text("DELETE FROM prefixes WHERE id = :id"), {"id": pid})
    await record_event(db, "prefix", pid, "deleted_by_reseller", user.get("name") or user.get("email"),
                        f"{row[0]} — {row[1]}" if row else "")
    await db.commit()


# ── Rate plans propios ──────────────────────────────────────────────────────

@router.get("/rate-plans")
async def list_rate_plans(user=Depends(require_reseller_permission("reseller_rates")), db: AsyncSession = Depends(get_db)):
    r = await db.execute(text(
        "SELECT * FROM rate_plans WHERE owner_customer_id = :cid ORDER BY name"
    ), {"cid": _my_cid(user)})
    return r.mappings().all()


@router.post("/rate-plans", status_code=201)
async def create_rate_plan(body: PlanIn, user=Depends(require_reseller_permission("reseller_rates")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    # Nombre único entre los planes de ESTE reseller — mismo criterio de
    # scoping que el resto del router (no puede haber dos planes "Standard"
    # del mismo reseller, sí puede haber uno por cada reseller distinto).
    dup = await db.execute(text(
        "SELECT 1 FROM rate_plans WHERE owner_customer_id = :cid AND name = :name"
    ), {"cid": my_cid, "name": body.name})
    if dup.first():
        raise HTTPException(409, "Ya tenés un plan con ese nombre")

    data = body.model_dump(); data["owner_customer_id"] = my_cid
    result = await db.execute(text("""
        INSERT INTO rate_plans (name, owner_customer_id, currency, description, status)
        VALUES (:name, :owner_customer_id, :currency, :description, 'active')
    """), data)
    await record_event(db, "rate_plan", result.lastrowid, "created_by_reseller",
                        user.get("name") or user.get("email"), body.name)
    await db.commit()
    return {"id": result.lastrowid}


async def _own_plan_or_404(db: AsyncSession, pid: int, my_cid: int) -> None:
    r = await db.execute(text(
        "SELECT 1 FROM rate_plans WHERE id = :id AND owner_customer_id = :cid"
    ), {"id": pid, "cid": my_cid})
    if not r.first():
        raise HTTPException(404, "Plan no encontrado")


@router.get("/rate-plans/{pid}/rates")
async def get_rate_plan_rates(pid: int, user=Depends(require_reseller_permission("reseller_rates")), db: AsyncSession = Depends(get_db)):
    await _own_plan_or_404(db, pid, _my_cid(user))
    r = await db.execute(text("""
        SELECT r.*, p.prefix, p.destination, p.group_name, p.country
        FROM rates r JOIN prefixes p ON r.prefix_id = p.id
        WHERE r.rate_plan_id = :pid ORDER BY p.prefix
    """), {"pid": pid})
    return r.mappings().all()


@router.post("/rate-plans/{pid}/rates", status_code=201)
async def set_rate(pid: int, body: RateIn, user=Depends(require_reseller_permission("reseller_rates")), db: AsyncSession = Depends(get_db)):
    await _own_plan_or_404(db, pid, _my_cid(user))
    data = body.model_dump(); data["rate_plan_id"] = pid
    await db.execute(text("""
        INSERT INTO rates (rate_plan_id, prefix_id, rateinitial, connectcharge,
                           initblock, billingblock, minimal_time_charge, status)
        VALUES (:rate_plan_id, :prefix_id, :rateinitial, :connectcharge,
                :initblock, :billingblock, :minimal_time_charge, 'active')
        ON DUPLICATE KEY UPDATE rateinitial=:rateinitial, connectcharge=:connectcharge,
            initblock=:initblock, billingblock=:billingblock
    """), data)
    await record_event(db, "rate_plan", pid, "rate_set", user.get("name") or user.get("email"),
                        f"prefix_id={body.prefix_id} → {body.rateinitial}/min")
    await db.commit()
    return {"ok": True}


@router.post("/rate-plans/{pid}/group-rates", status_code=201)
async def add_group_rate(pid: int, body: GroupRateIn, user=Depends(require_reseller_permission("reseller_rates")), db: AsyncSession = Depends(get_db)):
    await _own_plan_or_404(db, pid, _my_cid(user))
    r = await db.execute(text("SELECT id FROM prefixes WHERE group_name = :g"), {"g": body.group_name})
    prefix_ids = [row[0] for row in r.fetchall()]
    # Auditoría v2.55: antes un INSERT por prefijo en loop — mismo criterio que
    # carriers.py::add_group_buy_rate (executemany en un solo round-trip).
    if prefix_ids:
        await db.execute(text("""
            INSERT INTO rates (rate_plan_id, prefix_id, rateinitial, connectcharge,
                               initblock, billingblock, minimal_time_charge, status)
            VALUES (:pid, :pfx, :rate, :cc, :ib, :bb, 0, 'active')
            ON DUPLICATE KEY UPDATE rateinitial=:rate, connectcharge=:cc,
                initblock=:ib, billingblock=:bb
        """), [{"pid": pid, "pfx": pfx_id, "rate": body.rateinitial, "cc": body.connectcharge,
                "ib": body.initblock, "bb": body.billingblock} for pfx_id in prefix_ids])
    await record_event(db, "rate_plan", pid, "group_rate_set", user.get("name") or user.get("email"),
                        f"grupo {body.group_name} → {body.rateinitial}/min ({len(prefix_ids)} prefijos)")
    await db.commit()
    return {"ok": True, "updated": len(prefix_ids)}


@router.delete("/rate-plans/{pid}/rates/{rid}", status_code=204)
async def delete_rate(pid: int, rid: int, user=Depends(require_reseller_permission("reseller_rates")), db: AsyncSession = Depends(get_db)):
    await _own_plan_or_404(db, pid, _my_cid(user))
    await db.execute(text("DELETE FROM rates WHERE id=:id AND rate_plan_id=:pid"), {"id": rid, "pid": pid})
    await record_event(db, "rate_plan", pid, "rate_deleted", user.get("name") or user.get("email"), f"rate_id={rid}")
    await db.commit()


# ── Carriers propios ─────────────────────────────────────────────────────────
# Mismo criterio "mini admin" que prefixes/rate_plans (modelo MagnusBilling,
# a pedido explícito del usuario) — el reseller carga su propia troncal SIP
# real, con sus propios buy-rates. gen_dispatcher.py NO necesita saber de
# esto: un carrier entra a un grupo (carrier_group_members) sin importar
# quién es su dueño — por eso no hizo falta tocar ese script para nada.

@router.get("/carriers")
async def list_carriers(user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    r = await db.execute(text("""
        SELECT ca.*, (SELECT COUNT(*) FROM carrier_rates cr WHERE cr.carrier_id = ca.id) AS rate_count
        FROM carriers ca WHERE ca.owner_customer_id = :cid ORDER BY ca.priority DESC, ca.name
    """), {"cid": _my_cid(user)})
    return r.mappings().all()


@router.get("/carriers/assignable")
async def list_assignable_carriers(user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    """
    Propios + de plataforma, pero de plataforma SOLO los que el admin le
    asignó explícitamente a este reseller — un carrier de plataforma es
    miembro del grupo Principal PROPIO del reseller (customers.
    routing_group_id sobre la propia fila de customers del reseller, ver
    customers.py::_ensure_own_group / assign_carrier — el admin lo asigna
    exactamente igual que a cualquier cliente normal). Antes esto devolvía
    TODOS los carriers de plataforma (owner_customer_id IS NULL) sin
    filtrar, así que un reseller sin ningún carrier asignado por el admin
    igual veía y podía asignar cualquiera a sus sub-clientes — sin admin no
    debe ver ninguno. Se gatea por show_reseller_customers (no
    show_reseller_carriers) porque lo consume la página de Sub-clientes al
    asignar carriers — un reseller sin la página "Carriers propios"
    habilitada igual puede asignar carriers de plataforma que el admin ya
    le concedió.
    """
    r = await db.execute(text("""
        SELECT c.id, c.name, c.status, (c.owner_customer_id = :cid) AS is_own,
               (SELECT COUNT(*) FROM carrier_rates cr WHERE cr.carrier_id = c.id) AS rate_count
        FROM carriers c
        WHERE c.owner_customer_id = :cid
           OR (c.owner_customer_id IS NULL
               AND EXISTS (
                   SELECT 1 FROM carrier_group_members m
                   JOIN customers rc ON rc.routing_group_id = m.group_id
                   WHERE rc.id = :cid AND m.carrier_id = c.id
               ))
        ORDER BY is_own DESC, c.priority DESC, c.name
    """), {"cid": _my_cid(user)})
    return r.mappings().all()


@router.post("/carriers", status_code=201)
async def create_carrier(body: CarrierIn, user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    data = body.model_dump(); data["owner_customer_id"] = my_cid
    result = await db.execute(text("""
        INSERT INTO carriers (name, host, port, priority, outbound_prefix, remove_prefix,
                              status, cps_limit, notes, owner_customer_id)
        VALUES (:name, :host, :port, :priority, :outbound_prefix, :remove_prefix,
                :status, :cps_limit, :notes, :owner_customer_id)
    """), data)
    await record_event(db, "carrier", result.lastrowid, "created_by_reseller",
                        user.get("name") or user.get("email"), body.name)
    await db.commit()
    _sync()
    return {"id": result.lastrowid}


async def _own_carrier_or_404(db: AsyncSession, cid: int, my_cid: int) -> None:
    r = await db.execute(text(
        "SELECT 1 FROM carriers WHERE id = :id AND owner_customer_id = :cid"
    ), {"id": cid, "cid": my_cid})
    if not r.first():
        raise HTTPException(404, "Carrier no encontrado — solo podés editar/borrar los que vos creaste")


@router.get("/carriers/{cid}")
async def get_carrier(cid: int, user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    await _own_carrier_or_404(db, cid, _my_cid(user))
    r = await db.execute(text("SELECT * FROM carriers WHERE id = :id"), {"id": cid})
    return r.mappings().first()


@router.put("/carriers/{cid}")
async def update_carrier(cid: int, body: CarrierIn, user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    await _own_carrier_or_404(db, cid, my_cid)
    r_before = await db.execute(text("SELECT * FROM carriers WHERE id = :id"), {"id": cid})
    before = r_before.mappings().first()
    data = body.model_dump(); data["id"] = cid
    await db.execute(text("""
        UPDATE carriers SET name=:name, host=:host, port=:port, priority=:priority,
        outbound_prefix=:outbound_prefix, remove_prefix=:remove_prefix, status=:status,
        cps_limit=:cps_limit, notes=:notes
        WHERE id=:id
    """), data)
    if before:
        await diff_and_record(db, "carrier", cid, dict(before), body.model_dump(),
                               ["status", "host", "port", "priority"], user.get("name") or user.get("email"))
    await db.commit()
    _sync()
    return {"ok": True}


@router.delete("/carriers/{cid}", status_code=204)
async def delete_carrier(cid: int, user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    await _own_carrier_or_404(db, cid, my_cid)
    r = await db.execute(text("SELECT name FROM carriers WHERE id = :id"), {"id": cid})
    row = r.first()
    await db.execute(text("DELETE FROM carriers WHERE id = :id"), {"id": cid})
    await record_event(db, "carrier", cid, "deleted_by_reseller", user.get("name") or user.get("email"),
                        row[0] if row else "")
    await db.commit()
    _sync()


@router.get("/carriers/{cid}/rates")
async def get_carrier_buy_rates(cid: int, user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    await _own_carrier_or_404(db, cid, _my_cid(user))
    r = await db.execute(text("""
        SELECT cr.*, p.prefix, p.destination
        FROM carrier_rates cr JOIN prefixes p ON cr.prefix_id = p.id
        WHERE cr.carrier_id = :id ORDER BY p.prefix
    """), {"id": cid})
    return r.mappings().all()


@router.post("/carriers/{cid}/rates", status_code=201)
async def add_carrier_buy_rate(cid: int, body: CarrierBuyRateIn, user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    await _own_carrier_or_404(db, cid, my_cid)
    data = body.model_dump(); data["carrier_id"] = cid
    await db.execute(text("""
        INSERT INTO carrier_rates (carrier_id, prefix_id, buy_rate, connectcharge, billingblock)
        VALUES (:carrier_id, :prefix_id, :buy_rate, :connectcharge, :billingblock)
        ON DUPLICATE KEY UPDATE buy_rate=:buy_rate, connectcharge=:connectcharge, billingblock=:billingblock
    """), data)
    await record_event(db, "carrier", cid, "buy_rate_set", user.get("name") or user.get("email"),
                        f"prefix_id={body.prefix_id} → {body.buy_rate}/min")
    await db.commit()
    return {"ok": True}


@router.post("/carriers/{cid}/group-rates", status_code=201)
async def add_carrier_group_buy_rate(cid: int, body: CarrierGroupBuyRateIn, user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    await _own_carrier_or_404(db, cid, my_cid)
    r = await db.execute(text("SELECT id FROM prefixes WHERE group_name = :g"), {"g": body.group_name})
    prefix_ids = [row[0] for row in r.fetchall()]
    # Auditoría v2.55: antes un INSERT por prefijo en loop — mismo criterio que
    # carriers.py::add_group_buy_rate (executemany en un solo round-trip).
    if prefix_ids:
        await db.execute(text("""
            INSERT INTO carrier_rates (carrier_id, prefix_id, buy_rate, connectcharge, billingblock)
            VALUES (:cid, :pfx, :rate, :cc, :bb)
            ON DUPLICATE KEY UPDATE buy_rate=:rate, connectcharge=:cc, billingblock=:bb
        """), [{"cid": cid, "pfx": pfx_id, "rate": body.buy_rate, "cc": body.connectcharge, "bb": body.billingblock}
               for pfx_id in prefix_ids])
    await record_event(db, "carrier", cid, "group_buy_rate_set", user.get("name") or user.get("email"),
                        f"grupo {body.group_name} → {body.buy_rate}/min ({len(prefix_ids)} prefijos)")
    await db.commit()
    return {"ok": True, "updated": len(prefix_ids)}


@router.delete("/carriers/{cid}/rates/{rid}", status_code=204)
async def delete_carrier_buy_rate(cid: int, rid: int, user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    await _own_carrier_or_404(db, cid, my_cid)
    await db.execute(text("DELETE FROM carrier_rates WHERE id=:id AND carrier_id=:cid"), {"id": rid, "cid": cid})
    await record_event(db, "carrier", cid, "buy_rate_deleted", user.get("name") or user.get("email"), f"rate_id={rid}")
    await db.commit()


# ── Prefijos de campaña de sub-clientes ──────────────────────────────────────
# Mismo concepto que customers.py::add_prefix/delete_prefix, pero scopeado a
# los sub-clientes propios del reseller. Ruta "techprefixes" (no "prefixes")
# a propósito — /reseller/prefixes ya existe y es otra cosa (prefijos de
# tarifa/rating, tabla `prefixes`, nada que ver con techprefix de routing).

@router.get("/sub-customers/{cid}/techprefixes")
async def list_sub_customer_prefixes(cid: int, user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    owns = await db.execute(text(
        "SELECT 1 FROM customers WHERE id = :id AND parent_customer_id = :pid"
    ), {"id": cid, "pid": _my_cid(user)})
    if not owns.first():
        raise HTTPException(404, "Sub-cliente no encontrado")
    r = await db.execute(text(
        "SELECT id, techprefix, label, routing_group_id "
        "FROM customer_prefixes WHERE customer_id = :id ORDER BY techprefix"
    ), {"id": cid})
    return r.mappings().all()


@router.post("/sub-customers/{cid}/techprefixes", status_code=201)
async def add_sub_customer_prefix(cid: int, body: CustomerPrefixIn, user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    owns = await db.execute(text(
        "SELECT 1 FROM customers WHERE id = :id AND parent_customer_id = :pid"
    ), {"id": cid, "pid": _my_cid(user)})
    if not owns.first():
        raise HTTPException(404, "Sub-cliente no encontrado")
    techprefix = await next_campaign_prefix(db)
    await db.execute(text(
        "INSERT INTO customer_prefixes (customer_id, techprefix, label) VALUES (:cid, :tp, :label)"
    ), {"cid": cid, "tp": techprefix, "label": body.label})
    await db.commit()
    _sync()
    return {"ok": True, "techprefix": techprefix}


@router.delete("/sub-customers/{cid}/techprefixes/{prefix_id}", status_code=204)
async def delete_sub_customer_prefix(cid: int, prefix_id: int, user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    owns = await db.execute(text(
        "SELECT 1 FROM customers WHERE id = :id AND parent_customer_id = :pid"
    ), {"id": cid, "pid": _my_cid(user)})
    if not owns.first():
        raise HTTPException(404, "Sub-cliente no encontrado")
    await db.execute(text(
        "DELETE FROM customer_prefixes WHERE id = :id AND customer_id = :cid"
    ), {"id": prefix_id, "cid": cid})
    await db.commit()
    _sync()


# ── Carriers de sub-clientes ─────────────────────────────────────────────────
# El reseller puede asignar a CADA sub-cliente propio sus carriers propios +
# los carriers de plataforma que el ADMIN le asignó a él (ver
# list_assignable_carriers, arriba) — nunca los de otro reseller ni carriers
# de plataforma sin asignar. Igual que en customers.py, el gesto simple
# "asignale un carrier a este sub-cliente" crea/reutiliza el grupo
# Principal PROPIO del sub-cliente (customers.routing_group_id) por detrás.

async def _ensure_sub_customer_own_group(db: AsyncSession, cid: int, my_cid: int) -> int:
    """Mismo criterio que customers.py::_ensure_own_group, pero solo sobre
    sub-clientes propios de este reseller (owner_customer_id=my_cid, no
    NULL — un grupo creado automáticamente para un sub-cliente es del
    reseller, no de la plataforma)."""
    row = await db.execute(text(
        "SELECT routing_group_id, name FROM customers WHERE id = :id AND parent_customer_id = :pid"
    ), {"id": cid, "pid": my_cid})
    cust = row.mappings().first()
    if not cust:
        raise HTTPException(404, "Sub-cliente no encontrado")
    if cust["routing_group_id"]:
        return cust["routing_group_id"]

    result = await db.execute(text(
        "INSERT INTO carrier_groups (name, algorithm, owner_customer_id) "
        "VALUES (:name, 'priority', :owner)"
    ), {"name": f"{cust['name']} — Principal", "owner": my_cid})
    gid = result.lastrowid
    await db.execute(text(
        "UPDATE customers SET routing_group_id = :gid WHERE id = :cid"
    ), {"gid": gid, "cid": cid})
    await db.execute(text("""
        INSERT INTO customer_carrier_groups (customer_id, group_id, display_label)
        VALUES (:cid, :gid, 'Principal')
        ON DUPLICATE KEY UPDATE display_label = display_label
    """), {"cid": cid, "gid": gid})
    return gid


@router.get("/sub-customers/{cid}/carriers")
async def list_sub_customer_carriers(cid: int, user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    owns = await db.execute(text(
        "SELECT routing_group_id FROM customers WHERE id = :id AND parent_customer_id = :pid"
    ), {"id": cid, "pid": my_cid})
    row = owns.mappings().first()
    if not row:
        raise HTTPException(404, "Sub-cliente no encontrado")
    r = await db.execute(text("""
        SELECT m.carrier_id, m.priority, ca.name, ca.host, ca.status,
               (ca.owner_customer_id = :mycid) AS is_own
        FROM carrier_group_members m JOIN carriers ca ON m.carrier_id = ca.id
        WHERE m.group_id = :gid
        ORDER BY m.priority DESC
    """), {"gid": row["routing_group_id"], "mycid": my_cid})
    return r.mappings().all()


@router.post("/sub-customers/{cid}/carriers", status_code=201)
async def assign_carrier_to_sub_customer(cid: int, body: CustomerCarrierIn,
                                          user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    ok = await db.execute(text("""
        SELECT 1 FROM carriers c
        WHERE c.id = :id
          AND (c.owner_customer_id = :mycid
               OR (c.owner_customer_id IS NULL
                   AND EXISTS (
                       SELECT 1 FROM carrier_group_members m
                       JOIN customers rc ON rc.routing_group_id = m.group_id
                       WHERE rc.id = :mycid AND m.carrier_id = c.id
                   )))
    """), {"id": body.carrier_id, "mycid": my_cid})
    if not ok.first():
        raise HTTPException(400, "carrier_id debe ser propio de este reseller o un carrier de plataforma que el admin te haya asignado")

    # Mismo criterio que el lado admin (customers.py::assign_carrier) — un
    # carrier sin tarifas rutea igual pero factura buycost=0 en silencio.
    rated = await db.execute(text(
        "SELECT 1 FROM carrier_rates WHERE carrier_id = :cid LIMIT 1"
    ), {"cid": body.carrier_id})
    if not rated.first():
        raise HTTPException(400, "Este carrier no tiene tarifas de costo cargadas. Cárgale tarifas antes de asignarlo a un sub-cliente.")

    gid = await _ensure_sub_customer_own_group(db, cid, my_cid)
    await db.execute(text("""
        INSERT INTO carrier_group_members (group_id, carrier_id, priority)
        VALUES (:gid, :carid, :prio)
        ON DUPLICATE KEY UPDATE priority = :prio
    """), {"gid": gid, "carid": body.carrier_id, "prio": body.priority})
    await record_event(db, "customer", cid, "carrier_assigned", user.get("name") or user.get("email"),
                        f"carrier_id={body.carrier_id} priority={body.priority}")
    await db.commit()
    _sync()
    return {"ok": True}


@router.delete("/sub-customers/{cid}/carriers/{carrier_id}", status_code=204)
async def remove_carrier_from_sub_customer(cid: int, carrier_id: int,
                                            user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    owns = await db.execute(text(
        "SELECT routing_group_id FROM customers WHERE id = :id AND parent_customer_id = :pid"
    ), {"id": cid, "pid": my_cid})
    row = owns.mappings().first()
    if not row:
        raise HTTPException(404, "Sub-cliente no encontrado")
    if row["routing_group_id"]:
        await db.execute(text(
            "DELETE FROM carrier_group_members WHERE group_id = :gid AND carrier_id = :carid"
        ), {"gid": row["routing_group_id"], "carid": carrier_id})
    await record_event(db, "customer", cid, "carrier_removed", user.get("name") or user.get("email"),
                        f"carrier_id={carrier_id}")
    await db.commit()
    _sync()


# ── Grupos de ruteo propios ───────────────────────────────────────────────────
# Mismo concepto que backend/routers/carrier_groups.py (admin), pero scopeado
# a owner_customer_id = este reseller — mismo criterio "mini admin" que ya
# usan prefixes/rate_plans/carriers propios. Reemplaza el pin único
# active_carrier_id/carrier_failover_enabled y el reparto por %
# customers.carrier_split_mode de antes.

async def _own_group_or_404(db: AsyncSession, gid: int, my_cid: int) -> None:
    r = await db.execute(text(
        "SELECT 1 FROM carrier_groups WHERE id = :id AND owner_customer_id = :cid"
    ), {"id": gid, "cid": my_cid})
    if not r.first():
        raise HTTPException(404, "Grupo no encontrado — solo podés editar/borrar los que vos creaste")


@router.get("/carrier-groups")
async def list_own_groups(user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    r = await db.execute(text("""
        SELECT g.*, (SELECT COUNT(*) FROM carrier_group_members m WHERE m.group_id = g.id) AS member_count
        FROM carrier_groups g WHERE g.owner_customer_id = :cid ORDER BY g.name
    """), {"cid": _my_cid(user)})
    return r.mappings().all()


@router.get("/carrier-groups/{gid}")
async def get_own_group(gid: int, user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    await _own_group_or_404(db, gid, my_cid)
    g = await db.execute(text("SELECT * FROM carrier_groups WHERE id = :id"), {"id": gid})
    members = await db.execute(text("""
        SELECT m.carrier_id, m.priority, m.weight, ca.name, ca.host, ca.status
        FROM carrier_group_members m JOIN carriers ca ON m.carrier_id = ca.id
        WHERE m.group_id = :id ORDER BY m.priority DESC
    """), {"id": gid})
    # Solo sub-clientes PROPIOS — un grupo de un reseller solo lo puede
    # habilitar ese mismo reseller para sus sub-clientes (ver
    # assign_group_to_sub_customer, valida _own_group_or_404).
    used_by = await db.execute(text("""
        SELECT c.id AS customer_id, c.name AS customer_name, 'principal' AS ref, c.techprefix AS label
        FROM customers c WHERE c.routing_group_id = :id AND c.parent_customer_id = :mycid
        UNION ALL
        SELECT c.id AS customer_id, c.name AS customer_name, 'campaña' AS ref,
               COALESCE(cp.label, cp.techprefix) AS label
        FROM customer_prefixes cp JOIN customers c ON c.id = cp.customer_id
        WHERE cp.routing_group_id = :id AND c.parent_customer_id = :mycid
        ORDER BY customer_name
    """), {"id": gid, "mycid": my_cid})
    return {**dict(g.mappings().first()), "members": members.mappings().all(), "used_by": used_by.mappings().all()}


@router.post("/carrier-groups", status_code=201)
async def create_own_group(body: SubCustomerGroupIn, user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    result = await db.execute(text(
        "INSERT INTO carrier_groups (name, algorithm, owner_customer_id) VALUES (:name, :algorithm, :cid)"
    ), {**body.model_dump(), "cid": my_cid})
    new_id = result.lastrowid
    await record_event(db, "carrier_group", new_id, "created_by_reseller", user.get("name") or user.get("email"), body.name)
    await db.commit()
    return {"id": new_id}


@router.put("/carrier-groups/{gid}")
async def update_own_group(gid: int, body: SubCustomerGroupIn, user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    await _own_group_or_404(db, gid, my_cid)
    await db.execute(text(
        "UPDATE carrier_groups SET name=:name, algorithm=:algorithm WHERE id=:id"
    ), {**body.model_dump(), "id": gid})
    await db.commit()
    _sync()
    return {"ok": True}


@router.delete("/carrier-groups/{gid}", status_code=204)
async def delete_own_group(gid: int, user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    await _own_group_or_404(db, gid, my_cid)
    in_use = await db.execute(text("""
        SELECT customer_name, COUNT(*) AS n_prefixes FROM (
            SELECT c.id AS customer_id, c.name AS customer_name
            FROM customers c WHERE c.routing_group_id = :id
            UNION ALL
            SELECT c.id AS customer_id, c.name AS customer_name
            FROM customer_prefixes cp JOIN customers c ON c.id = cp.customer_id
            WHERE cp.routing_group_id = :id
        ) t
        GROUP BY customer_id, customer_name
        ORDER BY customer_name
    """), {"id": gid})
    users = in_use.mappings().all()
    if users:
        shown = ", ".join(f"{u['customer_name']} ({u['n_prefixes']})" for u in users[:5])
        extra = f" y {len(users) - 5} más" if len(users) > 5 else ""
        raise HTTPException(409, f"Este grupo está en uso por: {shown}{extra} — desasignalo antes de borrarlo")
    row = await db.execute(text("SELECT name FROM carrier_groups WHERE id = :id"), {"id": gid})
    g = row.mappings().first()
    await db.execute(text("DELETE FROM carrier_groups WHERE id = :id"), {"id": gid})
    await record_event(db, "carrier_group", gid, "deleted_by_reseller", user.get("name") or user.get("email"), g["name"] if g else "")
    await db.commit()


@router.post("/carrier-groups/{gid}/members", status_code=201)
async def add_own_group_member(gid: int, body: GroupMemberIn, user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    await _own_group_or_404(db, gid, my_cid)
    # Mismo criterio de visibilidad que assign_carrier_to_sub_customer —
    # propio o de plataforma ya asignado a este reseller.
    ok = await db.execute(text("""
        SELECT 1 FROM carriers c
        WHERE c.id = :id
          AND (c.owner_customer_id = :mycid
               OR (c.owner_customer_id IS NULL
                   AND EXISTS (
                       SELECT 1 FROM carrier_group_members m
                       JOIN customers rc ON rc.routing_group_id = m.group_id
                       WHERE rc.id = :mycid AND m.carrier_id = c.id
                   )))
    """), {"id": body.carrier_id, "mycid": my_cid})
    if not ok.first():
        raise HTTPException(400, "carrier_id debe ser propio de este reseller o un carrier de plataforma que el admin te haya asignado")
    await db.execute(text("""
        INSERT INTO carrier_group_members (group_id, carrier_id, priority, weight)
        VALUES (:gid, :carrier_id, :priority, :weight)
        ON DUPLICATE KEY UPDATE priority = :priority, weight = :weight
    """), {"gid": gid, **body.model_dump()})
    await db.commit()
    _sync()
    return {"ok": True}


@router.delete("/carrier-groups/{gid}/members/{carrier_id}", status_code=204)
async def remove_own_group_member(gid: int, carrier_id: int, user=Depends(require_reseller_permission("reseller_carriers")), db: AsyncSession = Depends(get_db)):
    await _own_group_or_404(db, gid, _my_cid(user))
    await db.execute(text(
        "DELETE FROM carrier_group_members WHERE group_id = :gid AND carrier_id = :cid"
    ), {"gid": gid, "cid": carrier_id})
    await db.commit()
    _sync()


# ── Grupos habilitados por sub-cliente + pin por prefijo ─────────────────────

@router.post("/sub-customers/{cid}/carrier-groups", status_code=201)
async def assign_group_to_sub_customer(cid: int, body: CustomerCarrierGroupIn,
                                        user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    """Habilita un grupo propio del reseller para que este sub-cliente pueda
    elegirlo — mismo criterio que assign_carrier_group() en customers.py."""
    my_cid = _my_cid(user)
    owns = await db.execute(text(
        "SELECT 1 FROM customers WHERE id = :id AND parent_customer_id = :pid"
    ), {"id": cid, "pid": my_cid})
    if not owns.first():
        raise HTTPException(404, "Sub-cliente no encontrado")
    await _own_group_or_404(db, body.group_id, my_cid)
    n = await db.execute(text(
        "SELECT COUNT(*) FROM customer_carrier_groups WHERE customer_id = :cid"
    ), {"cid": cid})
    display_label = f"Grupo {int(n.scalar()) + 1}"
    await db.execute(text("""
        INSERT INTO customer_carrier_groups (customer_id, group_id, display_label)
        VALUES (:cid, :gid, :label)
        ON DUPLICATE KEY UPDATE display_label = display_label
    """), {"cid": cid, "gid": body.group_id, "label": display_label})
    await db.commit()
    return {"ok": True}


@router.delete("/sub-customers/{cid}/carrier-groups/{group_id}", status_code=204)
async def unassign_group_from_sub_customer(cid: int, group_id: int,
                                            user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    my_cid = _my_cid(user)
    owns = await db.execute(text(
        "SELECT 1 FROM customers WHERE id = :id AND parent_customer_id = :pid"
    ), {"id": cid, "pid": my_cid})
    if not owns.first():
        raise HTTPException(404, "Sub-cliente no encontrado")
    await db.execute(text(
        "DELETE FROM customer_carrier_groups WHERE customer_id = :cid AND group_id = :gid"
    ), {"cid": cid, "gid": group_id})
    await db.execute(text(
        "UPDATE customers SET routing_group_id = NULL WHERE id = :cid AND routing_group_id = :gid"
    ), {"cid": cid, "gid": group_id})
    await db.execute(text(
        "UPDATE customer_prefixes SET routing_group_id = NULL WHERE customer_id = :cid AND routing_group_id = :gid"
    ), {"cid": cid, "gid": group_id})
    await db.commit()
    _sync()


async def _set_sub_customer_routing_group(db: AsyncSession, my_cid: int, cid: int,
                                           prefix_id: int | None, group_id: int | None) -> None:
    owns = await db.execute(text(
        "SELECT 1 FROM customers WHERE id = :id AND parent_customer_id = :pid"
    ), {"id": cid, "pid": my_cid})
    if not owns.first():
        raise HTTPException(404, "Sub-cliente no encontrado")
    if group_id is not None:
        ok = await db.execute(text(
            "SELECT 1 FROM customer_carrier_groups WHERE customer_id = :cid AND group_id = :gid"
        ), {"cid": cid, "gid": group_id})
        if not ok.first():
            raise HTTPException(400, "Ese grupo no está habilitado para este sub-cliente — asignalo primero")
    if prefix_id is None:
        await db.execute(text(
            "UPDATE customers SET routing_group_id = :gid WHERE id = :cid"
        ), {"gid": group_id, "cid": cid})
    else:
        r = await db.execute(text(
            "UPDATE customer_prefixes SET routing_group_id = :gid WHERE id = :pid AND customer_id = :cid"
        ), {"gid": group_id, "pid": prefix_id, "cid": cid})
        if r.rowcount == 0:
            exists = await db.execute(text(
                "SELECT 1 FROM customer_prefixes WHERE id = :pid AND customer_id = :cid"
            ), {"pid": prefix_id, "cid": cid})
            if not exists.first():
                raise HTTPException(404, "Prefijo no encontrado")
    await db.commit()
    _sync()


@router.put("/sub-customers/{cid}/routing-group")
async def set_sub_customer_routing_group(cid: int, body: RoutingGroupIn,
                                          user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    """Techprefix PRINCIPAL del sub-cliente."""
    await _set_sub_customer_routing_group(db, _my_cid(user), cid, None, body.group_id)
    return {"ok": True}


@router.put("/sub-customers/{cid}/prefixes/{prefix_id}/routing-group")
async def set_sub_customer_prefix_routing_group(cid: int, prefix_id: int, body: RoutingGroupIn,
                                                 user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    """Mismo pin, para un prefijo de campaña puntual del sub-cliente."""
    await _set_sub_customer_routing_group(db, _my_cid(user), cid, prefix_id, body.group_id)
    return {"ok": True}


# ── Dashboard de margen ──────────────────────────────────────────────────────

@router.get("/dashboard")
async def dashboard(user=Depends(require_reseller_permission("reseller_dashboard")), db: AsyncSession = Depends(get_db)):
    """
    Margen del reseller = sessionbill - reseller_cost, por sub-cliente y total
    del mes en curso. reseller_cost solo se calcula para CDRs de clientes con
    parent_customer_id — ver backend/routers/cdrs.py::ingest_cdr().

    Días completados del mes → cdr_summary_day_reseller (agregado nocturno,
    mismo filtro exacto que antes se corría en vivo — ver cron_summary.py y el
    comentario en db/schema.sql sobre por qué es tabla aparte). Hoy → cdrs en
    vivo, acotado a su propia partición diaria — mismo patrón híbrido que
    reports.py::report_month() (admin) y portal.py::my_report() (cliente).
    Antes esto escaneaba el mes completo en vivo en cada carga del dashboard,
    cada vez más pesado a medida que avanza el mes.

    Excluye CDRs con reseller_cost IS NULL (no COALESCE a 0): si tratáramos el
    NULL como costo cero, esas llamadas mostrarían el 100% del sessionbill
    como margen — un número falso, no "sin dato". Esto puede pasar con CDRs
    viejos de un cliente que se volvió sub-cliente de un reseller DESPUÉS de
    tener historial (ese historial nunca tuvo reseller_cost calculado).
    """
    import datetime as _dt
    my_cid = _my_cid(user)
    r = await db.execute(text("""
        SELECT cu.id AS customer_id, cu.name AS customer_name,
               SUM(t.nbcall)                              AS calls,
               ROUND(SUM(t.revenue), 4)                    AS revenue,
               ROUND(SUM(t.cost), 4)                        AS cost,
               ROUND(SUM(t.revenue - t.cost), 4)           AS margin
        FROM (
            /* Días completados del mes — tabla de resumen, ya acotado a mis sub-clientes */
            SELECT sd.customer_id, sd.nbcall, sd.revenue, sd.cost
            FROM cdr_summary_day_reseller sd
            JOIN customers subc ON subc.id = sd.customer_id AND subc.parent_customer_id = :pid
            WHERE LEFT(sd.summary_date, 7) = :month
              AND sd.summary_date < CURDATE()

            UNION ALL

            /* Hoy en vivo, mismo alcance */
            SELECT c.customer_id,
                   COUNT(*)              AS nbcall,
                   SUM(c.sessionbill)    AS revenue,
                   SUM(c.reseller_cost)  AS cost
            FROM cdrs c
            JOIN customers subc ON subc.id = c.customer_id AND subc.parent_customer_id = :pid
            WHERE c.disposition = 'ANSWERED'
              AND c.reseller_cost IS NOT NULL
              AND c.start_ts >= CURDATE() AND c.start_ts < CURDATE() + INTERVAL 1 DAY
            GROUP BY c.customer_id
        ) t
        JOIN customers cu ON t.customer_id = cu.id
        GROUP BY cu.id, cu.name
        ORDER BY margin DESC
    """), {"pid": my_cid, "month": _dt.date.today().strftime("%Y-%m")})
    rows = r.mappings().all()
    return {
        "month": _dt.date.today().strftime("%Y-%m"),
        "by_customer": rows,
        "total_margin": round(sum(float(row["margin"] or 0) for row in rows), 4),
    }


# ── Recálculo de tarifas propio ──────────────────────────────────────────────
# Mismo motor que /api/admin/billing-recalc (backend/routers/billing_recalc.py
# — _start_job()/_read_job() reusan la fórmula real de facturación en background,
# no la reimplementan acá). Acotado estructuralmente a los propios sub-clientes
# y carriers del reseller, igual que el resto de este archivo.

async def _my_recalc_scope(db: AsyncSession, my_cid: int):
    subc = await db.execute(text("SELECT id FROM customers WHERE parent_customer_id = :pid"), {"pid": my_cid})
    own_carriers = await db.execute(text("SELECT id FROM carriers WHERE owner_customer_id = :pid"), {"pid": my_cid})
    return (
        {row[0] for row in subc.all()},
        {row[0] for row in own_carriers.all()},
    )


@router.get("/billing-recalc/customers")
async def list_own_recalc_customers(user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    r = await db.execute(text(
        "SELECT id, name FROM customers WHERE parent_customer_id = :pid AND status != 'deleted' ORDER BY name"
    ), {"pid": _my_cid(user)})
    return r.mappings().all()


@router.get("/billing-recalc/carriers")
async def list_own_recalc_carriers(user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    r = await db.execute(text(
        "SELECT id, name FROM carriers WHERE owner_customer_id = :pid ORDER BY name"
    ), {"pid": _my_cid(user)})
    return r.mappings().all()


@router.post("/billing-recalc/preview")
async def preview_own_recalc(body: RecalcRequest, background_tasks: BackgroundTasks,
                              user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    allowed_customers, allowed_carriers = await _my_recalc_scope(db, _my_cid(user))
    return _start_job(background_tasks, "preview", body, None, allowed_customers, allowed_carriers)


@router.post("/billing-recalc/apply")
async def apply_own_recalc(body: RecalcRequest, background_tasks: BackgroundTasks,
                            user=Depends(require_reseller_permission("reseller_customers")), db: AsyncSession = Depends(get_db)):
    allowed_customers, allowed_carriers = await _my_recalc_scope(db, _my_cid(user))
    return _start_job(background_tasks, "apply", body, user.get("name") or user.get("email"), allowed_customers, allowed_carriers)


@router.get("/billing-recalc/jobs/{job_id}")
async def get_own_recalc_job(job_id: str, user=Depends(require_reseller_permission("reseller_customers"))):
    job = _read_job(job_id)
    if not job:
        raise HTTPException(404, "Job no encontrado — puede haber expirado")
    return job
