# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Grupos de ruteo (estilo MagnusBilling) — reemplaza el pin único
active_carrier_id/carrier_failover_enabled. Un grupo tiene nombre +
algoritmo (priority/round_robin/percent) + carriers miembros; cada prefijo
de un cliente (principal o de campaña) elige a qué grupo rutea, ver
backend/routers/customers.py (routing-group) y reseller.py (espejo).

Este router es SOLO admin, y SOLO administra grupos de plataforma
(carrier_groups.owner_customer_id IS NULL) — mismo criterio "el admin ve lo
suyo y el reseller ve lo suyo" que ya usan carriers/prefixes/rate_plans. Los
grupos propios de un reseller se administran en reseller.py, con las mismas
rutas replicadas bajo /api/reseller y owner_customer_id = su propio id.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from pathlib import Path

from auth import require_admin
from database import get_db
from audit import record_event
from sync_runner import run_sync

router = APIRouter()
SCRIPTS = Path(__file__).parent.parent.parent / "scripts"

ALGORITHMS = ("priority", "round_robin", "percent")


def _sync_dispatcher():
    run_sync(SCRIPTS / "gen_dispatcher.py")


class CarrierGroupIn(BaseModel):
    name: str
    algorithm: str = "priority"

    @field_validator("algorithm")
    @classmethod
    def _algorithm_valid(cls, v: str) -> str:
        if v not in ALGORITHMS:
            raise ValueError(f"algorithm debe ser uno de: {', '.join(ALGORITHMS)}")
        return v

    @field_validator("name")
    @classmethod
    def _name_no_control_chars(cls, v: str) -> str:
        """
        Mismo criterio que customers.py::CustomerIn._name_no_control_chars —
        el nombre real del grupo nunca se embebe en un .cfg generado (el
        cliente solo ve display_label anonimizado en el portal, ver
        customer_carrier_groups), pero sí aparece tal cual en comentarios de
        dispatcher.list (gen_dispatcher.py::build_dispatcher_list, f-string
        con group_def['name']) — misma defensa en profundidad.
        """
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


# ── CRUD de grupos ────────────────────────────────────────────────────────────

@router.get("")
async def list_groups(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    """
    member_count = carriers asignados al grupo; used_by_count = clientes/
    prefijos que rutean a través de él (misma subquery que delete_group()) —
    son dos métricas independientes, no debería sorprender ver member_count=0
    con used_by_count>0: significa que hay un cliente ruteando a un grupo sin
    ningún carrier, routing roto en silencio. El frontend usa esta
    combinación para marcarlo con una alerta visible en vez de que el admin
    lo descubra recién al intentar borrar el grupo (ver 409 de delete_group).
    """
    # used_by_count: suma de 2 subqueries correlacionadas directas, no un
    # UNION ALL envuelto en derived table — MariaDB rechaza la referencia a
    # g.id (columna de la query externa) dentro de un derived table en el
    # FROM ("Unknown column 'g.id' in WHERE"), aunque MySQL sí lo acepta.
    # Suma de counts = count del UNION ALL ya que ambas tablas son disjuntas.
    r = await db.execute(text("""
        SELECT g.*,
               (SELECT COUNT(*) FROM carrier_group_members m WHERE m.group_id = g.id) AS member_count,
               (SELECT COUNT(*) FROM customers c WHERE c.routing_group_id = g.id)
             + (SELECT COUNT(*) FROM customer_prefixes cp WHERE cp.routing_group_id = g.id) AS used_by_count
        FROM carrier_groups g WHERE g.owner_customer_id IS NULL ORDER BY g.name
    """))
    return r.mappings().all()


@router.get("/{gid}")
async def get_group(gid: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text(
        "SELECT * FROM carrier_groups WHERE id = :id AND owner_customer_id IS NULL"
    ), {"id": gid})
    g = r.mappings().first()
    if not g:
        raise HTTPException(404, "Grupo no encontrado")
    members = await db.execute(text("""
        SELECT m.carrier_id, m.priority, m.weight, ca.name, ca.host, ca.status
        FROM carrier_group_members m JOIN carriers ca ON m.carrier_id = ca.id
        WHERE m.group_id = :id ORDER BY m.priority DESC
    """), {"id": gid})
    used_by = await db.execute(text("""
        SELECT c.id AS customer_id, c.name AS customer_name, 'principal' AS ref, c.techprefix AS label
        FROM customers c WHERE c.routing_group_id = :id
        UNION ALL
        SELECT c.id AS customer_id, c.name AS customer_name, 'campaña' AS ref,
               COALESCE(cp.label, cp.techprefix) AS label
        FROM customer_prefixes cp JOIN customers c ON c.id = cp.customer_id
        WHERE cp.routing_group_id = :id
        ORDER BY customer_name
    """), {"id": gid})
    # "Habilitado para" (customer_carrier_groups) vs "used_by" de arriba son
    # cosas distintas — tener el grupo habilitado no implica estar ruteando
    # con él ahora mismo (el cliente puede tenerlo disponible y no haberlo
    # elegido todavía). Sin esta lista separada, "used_by" vacío se leía como
    # "nadie tiene acceso", pero podía haber clientes habilitados sin usarlo.
    enabled_for = await db.execute(text("""
        SELECT c.id AS customer_id, c.name AS customer_name, ccg.display_label
        FROM customer_carrier_groups ccg JOIN customers c ON c.id = ccg.customer_id
        WHERE ccg.group_id = :id ORDER BY c.name
    """), {"id": gid})
    return {
        **dict(g),
        "members": members.mappings().all(),
        "used_by": used_by.mappings().all(),
        "enabled_for": enabled_for.mappings().all(),
    }


@router.post("", status_code=201)
async def create_group(body: CarrierGroupIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    result = await db.execute(text(
        "INSERT INTO carrier_groups (name, algorithm, owner_customer_id) VALUES (:name, :algorithm, NULL)"
    ), body.model_dump())
    new_id = result.lastrowid
    await record_event(db, "carrier_group", new_id, "created", admin.get("name") or admin.get("email"), body.name)
    await db.commit()
    return {"id": new_id}


@router.put("/{gid}")
async def update_group(gid: int, body: CarrierGroupIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    r = await db.execute(text(
        "UPDATE carrier_groups SET name=:name, algorithm=:algorithm WHERE id=:id AND owner_customer_id IS NULL"
    ), {**body.model_dump(), "id": gid})
    if r.rowcount == 0:
        exists = await db.execute(text("SELECT 1 FROM carrier_groups WHERE id=:id"), {"id": gid})
        raise HTTPException(404 if not exists.first() else 409,
                             "Grupo no encontrado" if not exists.first() else "El grupo ya tenía esos valores o no es de plataforma")
    await db.commit()
    _sync_dispatcher()
    return {"ok": True}


@router.delete("/{gid}", status_code=204)
async def delete_group(gid: int, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    """
    409 si algún prefijo (principal o de campaña, de cualquier cliente) sigue
    ruteando a este grupo — borrarlo en ese caso dejaría a gen_dispatcher.py
    con un routing_group_id apuntando a nada (cae al default silenciosamente,
    ver _resolve_routing, pero es mejor forzar que el admin lo desasigne
    explícitamente primero en vez de que el ruteo cambie solo).
    """
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
        # Acotado a 5 nombres — un cliente con muchos prefijos de campaña
        # no debe volver el mensaje ilegible.
        shown = ", ".join(f"{u['customer_name']} ({u['n_prefixes']})" for u in users[:5])
        extra = f" y {len(users) - 5} más" if len(users) > 5 else ""
        raise HTTPException(409, f"Este grupo está en uso por: {shown}{extra} — desasignalo antes de borrarlo")
    row = await db.execute(text("SELECT name FROM carrier_groups WHERE id=:id AND owner_customer_id IS NULL"), {"id": gid})
    g = row.mappings().first()
    if not g:
        raise HTTPException(404, "Grupo no encontrado")
    await db.execute(text("DELETE FROM carrier_groups WHERE id = :id"), {"id": gid})
    await record_event(db, "carrier_group", gid, "deleted", admin.get("name") or admin.get("email"), g["name"])
    await db.commit()


# ── Miembros ──────────────────────────────────────────────────────────────────

@router.post("/{gid}/members", status_code=201)
async def add_member(gid: int, body: GroupMemberIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    g = await db.execute(text("SELECT 1 FROM carrier_groups WHERE id=:id AND owner_customer_id IS NULL"), {"id": gid})
    if not g.first():
        raise HTTPException(404, "Grupo no encontrado")
    ca = await db.execute(text("SELECT 1 FROM carriers WHERE id=:id"), {"id": body.carrier_id})
    if not ca.first():
        raise HTTPException(404, "Carrier no encontrado")
    await db.execute(text("""
        INSERT INTO carrier_group_members (group_id, carrier_id, priority, weight)
        VALUES (:gid, :carrier_id, :priority, :weight)
        ON DUPLICATE KEY UPDATE priority = :priority, weight = :weight
    """), {"gid": gid, **body.model_dump()})
    await db.commit()
    _sync_dispatcher()
    return {"ok": True}


@router.delete("/{gid}/members/{carrier_id}", status_code=204)
async def remove_member(gid: int, carrier_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text(
        "DELETE FROM carrier_group_members WHERE group_id = :gid AND carrier_id = :cid"
    ), {"gid": gid, "cid": carrier_id})
    if r.rowcount == 0:
        raise HTTPException(404, "El carrier no es miembro de este grupo")
    await db.commit()
    _sync_dispatcher()


