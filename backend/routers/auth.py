# la plataforma anterior — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from auth import create_token, verify_password, get_current_user
from database import get_db

router = APIRouter()


@router.post("/login")
async def login(form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT id, name, email, password_hash, role, customer_id, is_active FROM users WHERE email = :email"),
        {"email": form.username}
    )
    user = result.mappings().first()
    if not user or not verify_password(form.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="Cuenta suspendida")

    modules = {
        "show_calls": True, "show_quality": True, "show_reports": True,
        "show_invoices": False, "show_trunk_guide": True,
    }
    if user["customer_id"]:
        try:
            cr = await db.execute(
                text("""
                    SELECT COALESCE(cp.show_calls,       cu.show_calls)       AS show_calls,
                           COALESCE(cp.show_quality,     cu.show_quality)     AS show_quality,
                           COALESCE(cp.show_reports,     cu.show_reports)     AS show_reports,
                           COALESCE(cp.show_invoices,    cu.show_invoices)    AS show_invoices,
                           COALESCE(cp.show_trunk_guide, cu.show_trunk_guide) AS show_trunk_guide
                    FROM customers cu
                    LEFT JOIN customer_profiles cp ON cu.profile_id = cp.id
                    WHERE cu.id = :id
                """),
                {"id": user["customer_id"]}
            )
            row = cr.mappings().first()
            if row:
                modules = {k: bool(row[k]) for k in modules}
        except Exception:
            pass  # columnas aún no migradas → usar defaults

    token = create_token({"sub": str(user["id"]), "role": user["role"]})
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user["role"],
        "name": user["name"],
        "customer_id": user["customer_id"],
        **modules,
    }


@router.get("/me")
async def me(user=Depends(get_current_user)):
    return user
