# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Logic log — comentarios internos atribuidos y con fecha sobre un cliente o
carrier. Distinto de customers.notes (un solo campo libre que se pisa en cada
edición): esto es un historial que se va acumulando, no se audita en
settings_history porque el comentario mismo YA es el registro.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from auth import require_admin
from database import get_db

router = APIRouter()

VALID_ENTITIES = {"customer", "carrier"}


class CommentIn(BaseModel):
    entity: str
    entity_id: int
    body: str


@router.get("")
async def list_comments(entity: str, entity_id: int,
                         db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    if entity not in VALID_ENTITIES:
        raise HTTPException(422, f"entity inválido — debe ser uno de: {', '.join(VALID_ENTITIES)}")
    r = await db.execute(text("""
        SELECT id, body, created_by, created_at
        FROM entity_comments
        WHERE entity = :entity AND entity_id = :entity_id
        ORDER BY created_at DESC
    """), {"entity": entity, "entity_id": entity_id})
    return r.mappings().all()


@router.post("", status_code=201)
async def create_comment(body: CommentIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    if body.entity not in VALID_ENTITIES:
        raise HTTPException(422, f"entity inválido — debe ser uno de: {', '.join(VALID_ENTITIES)}")
    if not body.body.strip():
        raise HTTPException(422, "El comentario no puede estar vacío")

    await db.execute(text("""
        INSERT INTO entity_comments (entity, entity_id, body, created_by)
        VALUES (:entity, :entity_id, :body, :created_by)
    """), {
        "entity": body.entity, "entity_id": body.entity_id, "body": body.body.strip(),
        "created_by": admin.get("name") or admin.get("email"),
    })
    await db.commit()
    r = await db.execute(text("SELECT LAST_INSERT_ID() AS id"))
    return {"id": r.scalar()}


@router.delete("/{comment_id}", status_code=204)
async def delete_comment(comment_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(text("DELETE FROM entity_comments WHERE id = :id"), {"id": comment_id})
    await db.commit()
