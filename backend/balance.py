# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
apply_balance_change() — código compartido para "sumar/restar N al balance
de un cliente + leer el balance resultante + dejar rastro en
balance_transactions". Auditoría v2.55 (workflow multi-agente): este mismo
UPDATE+SELECT+INSERT estaba duplicado a mano, con variaciones chicas, en 6
lugares del backend. Esta extracción cubre los 2 más simples y estructuralmente
casi idénticos — ambos endpoints de ajuste manual desde panel, baja frecuencia,
interactivos, fáciles de comparar 1 a 1 antes/después:
  - routers/customers.py::adjust_balance()          (admin, cualquier cliente)
  - routers/reseller.py::adjust_sub_customer_balance() (reseller, solo sus sub-clientes)

NO migra (todavía) los otros 4 call sites que tocan customers.balance:
  - routers/cdrs.py::ingest_cdr()      — camino síncrono, alto volumen (por CDR)
  - main.py::_billing_worker()         — camino de respaldo, batch de CDRs
  - routers/billing_recalc.py          — batch multi-cliente, ya dentro de su propio commit loop
  - routers/invoices.py (marcar pagada) — protegido por su propio guard atómico
    (balance_credited_at IS NULL) antes de llegar acá
Son caminos de alto volumen o con guards propios — migrarlos amerita su
propio test de caracterización antes de tocarlos, uno a la vez, no de un saque
junto con estos dos. Mismo criterio "no destruir, corregir de a poco" del
resto de esta ronda de fixes (ver CLAUDE.md).
"""
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def apply_balance_change(
    db: AsyncSession,
    customer_id: int,
    amount: float,
    *,
    type: str,
    reference: str,
    created_by: Optional[str] = None,
    extra_where: str = "",
    extra_params: Optional[dict] = None,
) -> float:
    """
    Suma `amount` (puede ser negativo) al balance de `customer_id`, lee el
    balance resultante y deja el ledger en balance_transactions. No hace
    commit — el caller decide cuándo (algunos agrupan varios cambios en una
    sola transacción). `extra_where`/`extra_params` permiten un scoping
    adicional en el UPDATE (ej: " AND parent_customer_id = :pid" para que un
    reseller no pueda tocar el balance de un cliente que no es suyo).
    """
    params = {"amount": amount, "id": customer_id, **(extra_params or {})}
    await db.execute(text(
        f"UPDATE customers SET balance = balance + :amount WHERE id = :id{extra_where}"
    ), params)

    bal_row = await db.execute(text("SELECT balance FROM customers WHERE id = :id"), {"id": customer_id})
    new_balance = bal_row.scalar()

    await db.execute(text("""
        INSERT INTO balance_transactions
            (customer_id, type, amount, balance_after, reference, created_by)
        VALUES (:cid, :type, :amount, :bal, :ref, :by)
    """), {"cid": customer_id, "type": type, "amount": amount, "bal": new_balance,
            "ref": reference, "by": created_by})

    return new_balance
