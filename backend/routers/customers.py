# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from ipaddress import ip_address
import subprocess, sys
from pathlib import Path

from auth import require_admin, hash_password, resolve_permissions
from database import get_db
from alerts import check_balance_alert
from audit import diff_and_record
from webhooks import dispatch_event
from techprefix import (
    assert_techprefix_free, next_campaign_prefix, next_customer_prefix, next_reseller_prefix,
)

router = APIRouter()
SCRIPTS = Path(__file__).parent.parent.parent / "scripts"


class CustomerIn(BaseModel):
    name: str
    company: Optional[str] = None
    email: EmailStr
    phone: Optional[str] = None
    # Obligatorio a propósito — un cliente sin plan nunca factura nada, en
    # silencio (encontrado en producción: "empresa" quedó con rate_plan_id
    # NULL desde su creación, sin ningún aviso, y jamás generó un sessionbill).
    rate_plan_id: int
    profile_id: Optional[int] = None
    calllimit: int = 10
    cpslimit: int = 2
    # Opcional — vacío/None autogenera en create_customer() (1001+ normal,
    # 2001+ si is_reseller=True, ver backend/techprefix.py). Editable a mano
    # igual que antes si se manda un valor.
    techprefix: Optional[str] = None
    # Solo tiene efecto en create_customer() — elige el rango de autogeneración
    # (1001+ vs 2001+) y setea customers.is_reseller al crear. Promover un
    # cliente a reseller DESPUÉS de creado sigue siendo make_reseller()/
    # remove_reseller() (acción separada) — este campo no los reemplaza ni
    # se usa en update_customer().
    is_reseller: bool = False
    currency: str = "PEN"
    # Overrides de permisos SOLO cuando profile_id es None — {resource_key: can_view}.
    # Ver permission_resources/profile_permissions en db/schema.sql. Si se manda
    # profile_id, este campo se ignora del todo (el perfil gobierna) y cualquier
    # override previo del cliente se borra en update_customer() — mismo criterio
    # "profile pisa completo" que ya tenía el UI viejo (checkboxes ocultos con perfil).
    permissions: Optional[dict[str, bool]] = None
    status: str = "active"
    billing_type: str = "prepago"
    notes: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _name_no_control_chars(cls, v: str) -> str:
        """
        Se embebe sin escapar en una línea de comentario '#' del
        dispatcher.list generado por Kamailio (scripts/gen_dispatcher.py,
        incluido tal cual en kamailio.cfg). Un '"' o una ',' no rompen un
        comentario, pero un salto de línea sí permite
        escaparse de él e inyectar directivas Kamailio arbitrarias en la
        config real. Se bloquea cualquier carácter de control, nunca hace
        falta ninguno en un nombre real. gen_dispatcher.py además sanea
        (_safe_comment) como segunda capa, para nombres que ya existían
        antes de este validador.
        """
        if any(ord(c) < 32 or ord(c) == 127 for c in v):
            raise ValueError(
                "El nombre no puede contener saltos de línea ni caracteres de control — "
                "se usa tal cual en un comentario de la configuración de Kamailio generada"
            )
        return v

    @field_validator("company")
    @classmethod
    def _company_no_control_chars(cls, v: Optional[str]) -> Optional[str]:
        """routers/invoices.py arma el HTML del correo de factura con
        f-strings sin escapar (mismo patrón que alert_html) — un salto de
        línea acá podría intentar header injection en ese correo. Severidad
        baja (solo afecta el propio correo del cliente), mismo criterio
        defensivo que name/label por consistencia."""
        if v and any(ord(c) < 32 or ord(c) == 127 for c in v):
            raise ValueError("company no puede contener saltos de línea ni caracteres de control")
        return v

    @field_validator("techprefix")
    @classmethod
    def _techprefix_digits_only(cls, v: Optional[str]) -> Optional[str]:
        """
        Kamailio lo usa como key_name de una fila en techprefix_map (htable
        "techmap", ver gen_dispatcher.py/templates/kamailio.cfg.j2) y como
        prefijo comparado contra el número marcado — nunca se interpola en
        sintaxis de Kamailio (eso ya no existe, el lookup es fijo). Igual se
        restringe a solo dígitos: una `,` rompería el join de
        cron_dlg_stats.py que arma la lista de prefijos conocidos para el
        AWK, y es la forma más simple de garantizar que nunca colisiona con
        nada del resto de la tooling. Vacío/None se deja pasar (autogenerado
        en create_customer() si no se manda — ver backend/techprefix.py).
        """
        if v and not v.isdigit():
            raise ValueError(
                "techprefix debe contener solo dígitos — es lo que Kamailio compara "
                "contra el número marcado, y caracteres no numéricos romperían el "
                "routing generado para todos los clientes"
            )
        return v


class CustomerIPIn(BaseModel):
    ip: str
    description: Optional[str] = None

    @field_validator("ip")
    @classmethod
    def _ip_must_be_valid(cls, v: str) -> str:
        """
        Se embebe sin escapar en una regla nftables generada por
        scripts/gen_nftables.py (`ip saddr {ip} ...`), aplicada en caliente
        vía `sudo nft -f` (root, NOPASSWD). Cualquier string que no sea una
        IP real podría romper la sintaxis nft o, con un salto de línea,
        inyectar una regla nueva — mismo patrón que ya se corrigió para
        customers.name en el .cfg de Kamailio. Validar como dirección IP
        real (no solo bloquear caracteres de control) cierra esto de raíz:
        una IP v4/v6 válida nunca puede contener nada peligroso.
        """
        try:
            ip_address(v)
        except ValueError:
            raise ValueError(
                "Debe ser una dirección IP válida (IPv4 o IPv6) — se usa tal cual "
                "en una regla nftables generada"
            )
        return v


class CustomerPrefixIn(BaseModel):
    # techprefix NO es un campo de entrada — se autogenera en add_prefix()
    # (mismo criterio que reseller.py::_next_techprefix(): un humano no
    # conoce el gotcha de colisión por substring de Kamailio, así que no se
    # le deja elegir el valor).
    label: str = ""


class CustomerCarrierIn(BaseModel):
    carrier_id: int
    priority: int = 10


class CustomerCarrierGroupIn(BaseModel):
    group_id: int


class RoutingGroupIn(BaseModel):
    # None = sin override en un prefijo de campaña puntual — hereda el
    # grupo del cliente (customers.routing_group_id). No tiene sentido para
    # el prefijo PRINCIPAL: ahí siempre hay un group_id real, ver
    # _ensure_own_group().
    group_id: Optional[int] = None


# ── CRUD Clientes ─────────────────────────────────────────────────────────────

@router.get("")
async def list_customers(include_deleted: bool = False, exclude_resellers: bool = False,
                          resellers_only: bool = False,
                          db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    """
    Por defecto devuelve TODOS los clientes (resellers incluidos) — varias
    páginas (firewall, calidad, facturas, simulador de ruteo) dependen de la
    lista completa y no deben perder a los resellers de sus selectores.
    `exclude_resellers=true` es lo que usa la página Clientes (para no
    mezclarlos con la lista plana); `resellers_only=true` es lo que usa la
    página nueva /resellers (con conteo de sub-clientes).
    """
    conditions = []
    if not include_deleted:
        conditions.append("c.status != 'deleted'")
    if resellers_only:
        conditions.append("c.is_reseller = 1")
    elif exclude_resellers:
        conditions.append("c.is_reseller = 0")
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    r = await db.execute(text(f"""
        SELECT c.*, rp.name AS rate_plan_name,
               (SELECT COUNT(*) FROM customers sc WHERE sc.parent_customer_id = c.id) AS sub_customer_count,
               COALESCE(c.techprefix, '') AS techprefix
        FROM customers c
        LEFT JOIN rate_plans rp ON c.rate_plan_id = rp.id
        {where}
        ORDER BY c.name
    """))
    return r.mappings().all()


@router.post("", status_code=201)
async def create_customer(body: CustomerIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    techprefix = body.techprefix or None
    if techprefix:
        await assert_techprefix_free(db, techprefix)
    else:
        # Autogenerado — 2001+ si se crea directamente como reseller, 1001+
        # si no (ver backend/techprefix.py). Reduce error humano de tipeo,
        # a pedido explícito del usuario.
        techprefix = await (next_reseller_prefix(db) if body.is_reseller else next_customer_prefix(db))
    data = body.model_dump()
    permissions = data.pop("permissions", None)
    data["techprefix"] = techprefix
    await db.execute(text("""
        INSERT INTO customers (name, company, email, phone, rate_plan_id, profile_id, calllimit,
                               cpslimit, techprefix, currency, is_reseller, status, billing_type, notes)
        VALUES (:name, :company, :email, :phone, :rate_plan_id, :profile_id, :calllimit,
                :cpslimit, :techprefix, :currency, :is_reseller, :status, :billing_type, :notes)
    """), data)
    r = await db.execute(text("SELECT LAST_INSERT_ID() AS id"))
    new_id = r.scalar()
    if not body.profile_id and permissions:
        for key, val in permissions.items():
            await db.execute(text("""
                INSERT INTO profile_permissions (customer_id, resource_key, can_view)
                VALUES (:cid, :key, :val)
            """), {"cid": new_id, "key": key, "val": val})
    await db.commit()
    return {"id": new_id}


@router.get("/{cid}")
async def get_customer(cid: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("""
        SELECT c.*, cp.name AS profile_name, COALESCE(c.techprefix, '') AS techprefix
        FROM customers c
        LEFT JOIN customer_profiles cp ON c.profile_id = cp.id
        WHERE c.id = :id
    """), {"id": cid})
    c = r.mappings().first()
    if not c:
        raise HTTPException(404, "Cliente no encontrado")
    ips = await db.execute(text("SELECT * FROM customer_ips WHERE customer_id = :id"), {"id": cid})
    prefixes = await db.execute(text(
        "SELECT id, techprefix, label, routing_group_id "
        "FROM customer_prefixes WHERE customer_id = :id ORDER BY techprefix"
    ), {"id": cid})
    # "Carriers de salida" ahora es la membresía del grupo Principal PROPIO
    # del cliente (customers.routing_group_id) — ver _ensure_own_group().
    # Sin grupo todavía (cliente nuevo, sin ningún carrier asignado nunca) =
    # lista vacía, mismo resultado visible que antes con customer_carriers.
    cars = await db.execute(text("""
        SELECT ca.id, ca.name, ca.host, m.priority
        FROM carrier_group_members m JOIN carriers ca ON m.carrier_id = ca.id
        WHERE m.group_id = :gid
    """), {"gid": c["routing_group_id"]})
    groups = await db.execute(text("""
        SELECT ccg.group_id, ccg.display_label, cg.name, cg.algorithm
        FROM customer_carrier_groups ccg JOIN carrier_groups cg ON ccg.group_id = cg.id
        WHERE ccg.customer_id = :id
    """), {"id": cid})
    usr = await db.execute(text(
        "SELECT id, name, email FROM users WHERE customer_id = :id AND role = 'client' LIMIT 1"
    ), {"id": cid})
    # permissions = ya resuelto (COALESCE override propio / perfil / default de
    # plataforma) — el editor de permisos del cliente en el frontend solo se
    # muestra editable cuando profile_id es None, ver customers/[id]/page.tsx.
    permissions = await resolve_permissions(db, cid)
    return {**dict(c), "ips": ips.mappings().all(), "prefixes": prefixes.mappings().all(),
            "carriers": cars.mappings().all(), "groups": groups.mappings().all(),
            "portal_user": usr.mappings().first(), "permissions": permissions}


_AUDITED_FIELDS = ["status", "billing_type", "rate_plan_id", "calllimit", "cpslimit", "techprefix"]


@router.put("/{cid}")
async def update_customer(cid: int, body: CustomerIn, background_tasks: BackgroundTasks,
                           db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    before_row = await db.execute(text(
        "SELECT name, status, billing_type, rate_plan_id, calllimit, cpslimit, techprefix FROM customers WHERE id=:id"
    ), {"id": cid})
    before = dict(before_row.mappings().first() or {})

    if body.techprefix != before.get("techprefix"):
        await assert_techprefix_free(db, body.techprefix, exclude_id=cid)

    data = body.model_dump()
    permissions = data.pop("permissions", None)
    data["id"] = cid
    data["techprefix"] = body.techprefix or None  # '' -> NULL, ver UNIQUE KEY uq_techprefix en schema.sql
    await db.execute(text("""
        UPDATE customers SET name=:name, company=:company, email=:email, phone=:phone,
        rate_plan_id=:rate_plan_id, calllimit=:calllimit, cpslimit=:cpslimit,
        techprefix=:techprefix, currency=:currency, profile_id=:profile_id,
        status=:status, billing_type=:billing_type, notes=:notes
        WHERE id=:id
    """), data)

    # Overrides de permisos propios del cliente — solo tienen efecto sin
    # perfil asignado (ver comentario de CustomerIn.permissions). Reemplazo
    # completo (DELETE + INSERT) en vez de upsert parcial: el formulario del
    # frontend siempre manda el estado completo del grid de checkboxes, no un
    # diff — mismo criterio que un PUT idempotente.
    await db.execute(text("DELETE FROM profile_permissions WHERE customer_id = :cid"), {"cid": cid})
    if not body.profile_id and permissions:
        for key, val in permissions.items():
            await db.execute(text("""
                INSERT INTO profile_permissions (customer_id, resource_key, can_view)
                VALUES (:cid, :key, :val)
            """), {"cid": cid, "key": key, "val": val})

    await diff_and_record(db, "customer", cid, before, data, _AUDITED_FIELDS, admin.get("name") or admin.get("email"))
    await db.commit()
    # techprefix y status son insumo directo de gen_dispatcher.py
    # (fetch_customers filtra status='active'; build_techprefix_rows
    # matchea por techprefix) — sin esto, un cambio acá quedaba en la DB
    # pero Kamailio seguía ruteando con la config vieja hasta que otra
    # acción no relacionada (asignar/quitar un carrier) disparara un sync.
    # Encontrado en auditoría real, no en un caso reportado.
    _sync_dispatcher()

    if before.get("status") != data["status"]:
        background_tasks.add_task(dispatch_event, "customer.status_changed", {
            "customer_id": cid, "customer_name": before.get("name") or data["name"],
            "old_status": before.get("status"), "new_status": data["status"],
        })
    return {"ok": True}


@router.delete("/{cid}", status_code=204)
async def deactivate_customer(cid: int, background_tasks: BackgroundTasks,
                               db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    """
    No borra la fila — la pasa a status='deleted'. cdrs.customer_id no puede
    tener FK (cdrs está particionada por mes), así que un DELETE físico dejaba
    CDRs/facturas viejas apuntando a un id inexistente. Un cliente 'deleted'
    desaparece de list_customers() y pierde acceso (login y API keys ya
    validan status == 'active'), pero el historial de facturación queda intacto
    y es reversible con POST /{cid}/reactivate.
    """
    before = await db.execute(text("SELECT name, status FROM customers WHERE id = :id"), {"id": cid})
    row = before.mappings().first()
    if not row:
        raise HTTPException(404, "Cliente no encontrado")
    if row["status"] == "deleted":
        raise HTTPException(409, "El cliente ya estaba desactivado")

    await db.execute(text("UPDATE customers SET status = 'deleted' WHERE id = :id"), {"id": cid})
    await db.commit()
    # Sin esto, un cliente "desactivado" seguía enrutando llamadas en
    # Kamailio con normalidad hasta que otra acción disparara un sync —
    # encontrado en auditoría real, no en un caso reportado.
    _sync_dispatcher()
    background_tasks.add_task(dispatch_event, "customer.status_changed", {
        "customer_id": cid, "customer_name": row["name"],
        "old_status": row["status"], "new_status": "deleted",
    })


@router.post("/{cid}/reactivate")
async def reactivate_customer(cid: int, background_tasks: BackgroundTasks,
                               db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    before = await db.execute(text("SELECT name, status FROM customers WHERE id = :id"), {"id": cid})
    row = before.mappings().first()
    if not row:
        raise HTTPException(404, "Cliente no encontrado")
    if row["status"] != "deleted":
        raise HTTPException(409, "El cliente no está desactivado")

    await db.execute(text("UPDATE customers SET status = 'active' WHERE id = :id"), {"id": cid})
    await db.commit()
    _sync_dispatcher()
    background_tasks.add_task(dispatch_event, "customer.status_changed", {
        "customer_id": cid, "customer_name": row["name"],
        "old_status": "deleted", "new_status": "active",
    })
    return {"ok": True}


@router.post("/{cid}/reseller")
async def make_reseller(cid: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    """
    is_reseller es un flag explícito que activa el admin — no un role nuevo en
    users.role (mismo criterio que is_superadmin). Acción separada del
    formulario general de edición a propósito, para que no se pueda prender
    sin querer al guardar otro campo — ver backend/routers/reseller.py.
    """
    r = await db.execute(text(
        "UPDATE customers SET is_reseller = 1 WHERE id = :id AND is_reseller = 0"
    ), {"id": cid})
    if r.rowcount == 0:
        exists = await db.execute(text("SELECT 1 FROM customers WHERE id = :id"), {"id": cid})
        if not exists.first():
            raise HTTPException(404, "Cliente no encontrado")
        raise HTTPException(409, "El cliente ya es reseller")
    await db.commit()
    return {"ok": True}


@router.delete("/{cid}/reseller", status_code=204)
async def remove_reseller(cid: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    # Bloquea si todavía tiene sub-clientes propios — sacar el flag sin
    # reasignarlos los deja huérfanos de panel (siguen facturando bien, pero
    # nadie los puede administrar vía /reseller hasta que se resuelva a mano).
    sub = await db.execute(text(
        "SELECT COUNT(*) FROM customers WHERE parent_customer_id = :id"
    ), {"id": cid})
    if sub.scalar() > 0:
        raise HTTPException(
            409,
            "No se puede quitar reseller — todavía tiene sub-clientes asignados. "
            "Reasigná o desactivá los sub-clientes primero.",
        )
    r = await db.execute(text(
        "UPDATE customers SET is_reseller = 0 WHERE id = :id AND is_reseller = 1"
    ), {"id": cid})
    if r.rowcount == 0:
        exists = await db.execute(text("SELECT 1 FROM customers WHERE id = :id"), {"id": cid})
        if not exists.first():
            raise HTTPException(404, "Cliente no encontrado")
        raise HTTPException(409, "El cliente no es reseller")
    await db.commit()
    return {"ok": True}


# ── IPs ───────────────────────────────────────────────────────────────────────

@router.post("/{cid}/ips", status_code=201)
async def add_ip(cid: int, body: CustomerIPIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(text(
        "INSERT INTO customer_ips (customer_id, ip, description) VALUES (:cid, :ip, :desc)"
    ), {"cid": cid, "ip": body.ip, "desc": body.description})
    await db.commit()
    _sync_nftables()
    return {"ok": True}


@router.put("/{cid}/ips/{ip_id}")
async def update_ip(cid: int, ip_id: int, body: CustomerIPIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(text(
        "UPDATE customer_ips SET ip=:ip, description=:desc WHERE id=:id AND customer_id=:cid"
    ), {"ip": body.ip, "desc": body.description, "id": ip_id, "cid": cid})
    await db.commit()
    _sync_nftables()
    return {"ok": True}


@router.delete("/{cid}/ips/{ip_id}", status_code=204)
async def delete_ip(cid: int, ip_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(text(
        "DELETE FROM customer_ips WHERE id = :id AND customer_id = :cid"
    ), {"id": ip_id, "cid": cid})
    await db.commit()
    _sync_nftables()


# ── Prefijos de campaña ───────────────────────────────────────────────────────
# Un cliente puede tener, además de su techprefix principal, N prefijos
# adicionales (uno por campaña de su Vicidial/marcador) que facturan al mismo
# balance pero permiten desglosar consumo por campaña en su panel. Alta/baja
# simple, sin edición — igual criterio que customer_ips (para cambiar el
# prefijo de una campaña, se borra y se crea de nuevo).

@router.post("/{cid}/prefixes", status_code=201)
async def add_prefix(cid: int, body: CustomerPrefixIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    techprefix = await next_campaign_prefix(db)
    await db.execute(text(
        "INSERT INTO customer_prefixes (customer_id, techprefix, label) VALUES (:cid, :tp, :label)"
    ), {"cid": cid, "tp": techprefix, "label": body.label})
    await db.commit()
    _sync_dispatcher()
    return {"ok": True, "techprefix": techprefix}


@router.delete("/{cid}/prefixes/{prefix_id}", status_code=204)
async def delete_prefix(cid: int, prefix_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(text(
        "DELETE FROM customer_prefixes WHERE id = :id AND customer_id = :cid"
    ), {"id": prefix_id, "cid": cid})
    await db.commit()
    _sync_dispatcher()


# ── Carriers asignados ────────────────────────────────────────────────────────

async def _ensure_own_group(db: AsyncSession, cid: int) -> int:
    """
    Devuelve customers.routing_group_id, creándolo si todavía es NULL — el
    grupo "Principal" que respalda el gesto simple "asignale un carrier a
    este cliente" (mismo resultado visible que antes con customer_carriers,
    ahora sobre carrier_group_members). También lo habilita en
    customer_carrier_groups (display_label "Principal") para que el propio
    cliente lo vea/pueda re-elegirlo desde el portal si alguna vez lo
    cambia por otro override y quiere volver.
    """
    row = await db.execute(text(
        "SELECT routing_group_id, name, parent_customer_id FROM customers WHERE id = :cid"
    ), {"cid": cid})
    cust = row.mappings().first()
    if not cust:
        raise HTTPException(404, "Cliente no encontrado")
    if cust["routing_group_id"]:
        return cust["routing_group_id"]

    result = await db.execute(text(
        "INSERT INTO carrier_groups (name, algorithm, owner_customer_id) "
        "VALUES (:name, 'priority', :owner)"
    ), {"name": f"{cust['name']} — Principal", "owner": cust["parent_customer_id"]})
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


@router.post("/{cid}/carriers", status_code=201)
async def assign_carrier(cid: int, body: CustomerCarrierIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    # Obligatorio a propósito — un carrier sin tarifas rutea llamadas igual
    # (gen_dispatcher.py no valida esto) pero factura buycost=0 en silencio,
    # inflando el margen reportado como si fuera 100% de ganancia.
    rated = await db.execute(text(
        "SELECT 1 FROM carrier_rates WHERE carrier_id = :cid LIMIT 1"
    ), {"cid": body.carrier_id})
    if not rated.first():
        raise HTTPException(400, "Este carrier no tiene tarifas de costo cargadas. Cárgale tarifas en Carriers antes de asignarlo a un cliente.")

    gid = await _ensure_own_group(db, cid)
    await db.execute(text("""
        INSERT INTO carrier_group_members (group_id, carrier_id, priority)
        VALUES (:gid, :carrier_id, :priority)
        ON DUPLICATE KEY UPDATE priority = :priority
    """), {"gid": gid, "carrier_id": body.carrier_id, "priority": body.priority})
    await db.commit()
    _sync_dispatcher()
    return {"ok": True}


@router.delete("/{cid}/carriers/{carrier_id}", status_code=204)
async def remove_carrier(cid: int, carrier_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    row = await db.execute(text("SELECT routing_group_id FROM customers WHERE id = :cid"), {"cid": cid})
    cust = row.mappings().first()
    if not cust:
        raise HTTPException(404, "Cliente no encontrado")
    if not cust["routing_group_id"]:
        return
    await db.execute(text(
        "DELETE FROM carrier_group_members WHERE group_id = :gid AND carrier_id = :carid"
    ), {"gid": cust["routing_group_id"], "carid": carrier_id})
    await db.commit()
    _sync_dispatcher()


# ── Grupos de ruteo (reemplaza el pin único active_carrier_id/carrier_failover_enabled) ──
# Un Grupo (ver backend/routers/carrier_groups.py) tiene nombre + algoritmo
# (priority/round_robin/percent) + carriers miembros — se define ahí. Acá
# solo se decide, POR PREFIJO (principal o campaña), a qué grupo rutea ese
# prefijo, y qué grupos puede VER el cliente en su portal.

@router.post("/{cid}/carrier-groups", status_code=201)
async def assign_carrier_group(cid: int, body: CustomerCarrierGroupIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    """
    Habilita un grupo para que este cliente pueda elegirlo — mismo criterio
    que assign_carrier() con customer_carriers: la membresía en
    customer_carrier_groups ES la lista autoritativa de qué puede usar este
    cliente (portal, o esta misma API en set_routing_group más abajo), nunca
    se infiere de otra cosa. display_label ("Grupo N") se asigna una sola
    vez, igual que display_label en customer_carriers.
    """
    g = await db.execute(text("SELECT 1 FROM carrier_groups WHERE id = :id"), {"id": body.group_id})
    if not g.first():
        raise HTTPException(404, "Grupo no encontrado")
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


@router.delete("/{cid}/carrier-groups/{group_id}", status_code=204)
async def unassign_carrier_group(cid: int, group_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(text(
        "DELETE FROM customer_carrier_groups WHERE customer_id = :cid AND group_id = :gid"
    ), {"cid": cid, "gid": group_id})
    # Mismo criterio que remove_carrier() con active_carrier_id (viejo) — si
    # el cliente/prefijo estaba ruteando a este grupo, limpiar el override
    # para no dejarlo apuntando a un grupo que el cliente ya no puede elegir.
    await db.execute(text(
        "UPDATE customers SET routing_group_id = NULL WHERE id = :cid AND routing_group_id = :gid"
    ), {"cid": cid, "gid": group_id})
    await db.execute(text(
        "UPDATE customer_prefixes SET routing_group_id = NULL WHERE customer_id = :cid AND routing_group_id = :gid"
    ), {"cid": cid, "gid": group_id})
    await db.commit()
    _sync_dispatcher()


async def _set_routing_group(db: AsyncSession, cid: int, prefix_id: int | None, group_id: int | None) -> None:
    """
    ADMIN — pinea el prefijo (principal si prefix_id=None, o una fila
    puntual de customer_prefixes) a un grupo ya habilitado para este cliente
    (ver assign_carrier_group). group_id=None limpia el override.
    Existencia chequeada con SELECT explícito en vez de rowcount de UPDATE —
    con el driver async (sin CLIENT_FOUND_ROWS) rowcount=0 también pasa
    cuando la fila existe pero el valor no cambió, lo que daría un 404 falso.
    """
    if group_id is not None:
        ok = await db.execute(text(
            "SELECT 1 FROM customer_carrier_groups WHERE customer_id = :cid AND group_id = :gid"
        ), {"cid": cid, "gid": group_id})
        if not ok.first():
            raise HTTPException(
                400,
                "Ese grupo no está habilitado para este cliente — asignalo primero "
                "con POST /{cid}/carrier-groups",
            )
    if prefix_id is None:
        exists = await db.execute(text("SELECT 1 FROM customers WHERE id = :cid"), {"cid": cid})
        if not exists.first():
            raise HTTPException(404, "Cliente no encontrado")
        await db.execute(text(
            "UPDATE customers SET routing_group_id = :gid WHERE id = :cid"
        ), {"gid": group_id, "cid": cid})
    else:
        exists = await db.execute(text(
            "SELECT 1 FROM customer_prefixes WHERE id = :pid AND customer_id = :cid"
        ), {"pid": prefix_id, "cid": cid})
        if not exists.first():
            raise HTTPException(404, "Prefijo no encontrado")
        await db.execute(text(
            "UPDATE customer_prefixes SET routing_group_id = :gid WHERE id = :pid AND customer_id = :cid"
        ), {"gid": group_id, "pid": prefix_id, "cid": cid})
    await db.commit()
    _sync_dispatcher()


@router.put("/{cid}/routing-group")
async def set_routing_group(cid: int, body: RoutingGroupIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    """Techprefix PRINCIPAL del cliente."""
    await _set_routing_group(db, cid, None, body.group_id)
    return {"ok": True}


@router.put("/{cid}/prefixes/{prefix_id}/routing-group")
async def set_prefix_routing_group(cid: int, prefix_id: int, body: RoutingGroupIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    """Mismo pin, para un prefijo de campaña puntual (customer_prefixes)."""
    await _set_routing_group(db, cid, prefix_id, body.group_id)
    return {"ok": True}


# ── Balance ───────────────────────────────────────────────────────────────────

@router.post("/{cid}/balance")
async def adjust_balance(cid: int, amount: float, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    await db.execute(text(
        "UPDATE customers SET balance = balance + :amount WHERE id = :id"
    ), {"amount": amount, "id": cid})
    bal_row = await db.execute(text("SELECT balance FROM customers WHERE id = :id"), {"id": cid})
    new_balance = bal_row.scalar()

    await db.execute(text("""
        INSERT INTO balance_transactions
            (customer_id, type, amount, balance_after, reference, created_by)
        VALUES (:cid, 'manual', :amount, :bal, :ref, :by)
    """), {"cid": cid, "amount": amount, "bal": new_balance,
            "ref": "Ajuste manual desde panel", "by": admin.get("name") or admin.get("email")})

    # Un recargo (monto positivo) es la nueva referencia del 100% para las
    # alertas de % en prepago, y limpia cualquier alerta ya notificada —
    # un ajuste negativo no toca esta referencia, solo re-evalúa alertas.
    if amount > 0:
        await db.execute(text(
            "UPDATE customers SET last_topup_amount = :bal, last_alert_rule_id = NULL WHERE id = :id"
        ), {"bal": new_balance, "id": cid})

    await db.commit()


@router.get("/{cid}/balance-transactions")
async def list_balance_transactions(
    cid: int,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """
    Ledger real del balance — cada fila es un movimiento (type='cdr' por cada
    llamada tarifada por backend/main.py::_billing_worker(), 'manual' por un
    ajuste desde este panel, 'invoice_payment'/'recalc' por los otros dos
    caminos que también escriben acá, ver billing_recalc.py/invoices.py).
    Sin esto no había forma de auditar por qué el balance de un cliente no
    "cuadraba" contra lo que uno esperaba sumando consumo — la tabla siempre
    existió (idx_customer_date en db/schema.sql) pero nunca se exponía.
    limit acotado a 200 — este ledger puede tener cientos de miles de filas
    para un cliente de alto volumen, sin tope el frontend se cuelga solo.
    """
    limit = min(max(limit, 1), 200)
    r = await db.execute(text("""
        SELECT id, type, amount, balance_after, reference, created_by, created_at
        FROM balance_transactions
        WHERE customer_id = :cid
        ORDER BY created_at DESC, id DESC
        LIMIT :limit OFFSET :offset
    """), {"cid": cid, "limit": limit, "offset": offset})
    return [dict(row) for row in r.mappings().all()]
    await check_balance_alert(db, cid)
    return {"ok": True}


# ── Acceso al portal (usuario cliente) ───────────────────────────────────────

class UserIn(BaseModel):
    name: str
    email: EmailStr
    password: str


class PasswordIn(BaseModel):
    password: str


@router.post("/{cid}/user", status_code=201)
async def create_client_user(cid: int, body: UserIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    existing = await db.execute(
        text("SELECT id FROM users WHERE customer_id = :cid AND role = 'client'"), {"cid": cid}
    )
    if existing.first():
        raise HTTPException(409, "Ya existe un usuario portal para este cliente")
    if len(body.password) < 8:
        raise HTTPException(400, "La contraseña debe tener al menos 8 caracteres")
    await db.execute(text("""
        INSERT INTO users (name, email, password_hash, role, customer_id)
        VALUES (:name, :email, :hash, 'client', :cid)
    """), {"name": body.name, "email": body.email, "hash": hash_password(body.password), "cid": cid})
    await db.commit()
    return {"ok": True}


@router.delete("/{cid}/user", status_code=204)
async def delete_client_user(cid: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(
        text("DELETE FROM users WHERE customer_id = :cid AND role = 'client'"), {"cid": cid}
    )
    await db.commit()


@router.put("/{cid}/user/password")
async def reset_client_password(cid: int, body: PasswordIn, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    if len(body.password) < 8:
        raise HTTPException(400, "La contraseña debe tener al menos 8 caracteres")
    await db.execute(
        text("UPDATE users SET password_hash = :hash WHERE customer_id = :cid AND role = 'client'"),
        {"hash": hash_password(body.password), "cid": cid}
    )
    await db.commit()
    return {"ok": True}


@router.get("/{cid}/api-keys")
async def list_customer_api_keys(cid: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    """
    Solo lectura para soporte — nunca expone el hash ni la key en texto plano.
    El admin puede revocar (vía /admin/customers, no acá) pero no ver ni crear
    una key a nombre del cliente — la key es una credencial que solo el
    cliente debe poseer.
    """
    r = await db.execute(text("""
        SELECT id, label, key_prefix, created_at, last_used_at, revoked
        FROM api_keys WHERE customer_id = :cid ORDER BY created_at DESC
    """), {"cid": cid})
    return r.mappings().all()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sync_nftables():
    subprocess.Popen([sys.executable, str(SCRIPTS / "gen_nftables.py")])


def _sync_dispatcher():
    subprocess.Popen([sys.executable, str(SCRIPTS / "gen_dispatcher.py")])
