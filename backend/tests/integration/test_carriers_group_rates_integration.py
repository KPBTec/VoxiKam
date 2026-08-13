# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Regresión v2.58.8: POST /admin/carriers/{id}/group-rates devolvía 500 en
producción real ("TypeError: not all arguments converted during string
formatting") apenas el grupo tenía 2+ prefijos — aiomysql reescribe
executemany() en un solo INSERT con múltiples VALUES(...) y pega el resto de
la sentencia (el ON DUPLICATE KEY UPDATE) una sola vez al final; si esa cola
reutiliza placeholders ya usados en el VALUES, sobran al aplicar el
%-formatting. La suite de test_billing_validation.py solo valida el modelo
Pydantic (GroupBuyRateIn) — nunca llega a golpear el endpoint real con
prefijos de verdad, por eso este bug pasó desapercibido desde que se
introdujo el executemany en v2.55. Este test SÍ pega contra una MariaDB real
con 2 prefijos compartiendo group_name, exactamente el caso que rompía.
"""
import pytest
from sqlalchemy import text

pytestmark = pytest.mark.usefixtures("integration_db_available")

ADMIN_EMAIL = "integration-carriers-admin@voxikam.test"
ADMIN_PASSWORD = "Sup3rSecret!2026"
GROUP_NAME = "INTEGRATION-TEST-GROUP"


@pytest.fixture
async def seeded_carrier(integration_db_available):
    from database import AsyncSessionLocal
    from auth import hash_password

    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM users WHERE email = :e"), {"e": ADMIN_EMAIL})
        await db.execute(text("DELETE FROM carrier_rates WHERE carrier_id IN "
                               "(SELECT id FROM carriers WHERE name = 'Integration Test Carrier')"))
        await db.execute(text("DELETE FROM carriers WHERE name = 'Integration Test Carrier'"))
        await db.execute(text("DELETE FROM prefixes WHERE group_name = :g"), {"g": GROUP_NAME})
        await db.commit()

        await db.execute(text(
            "INSERT INTO users (name, email, password_hash, role, is_superadmin, is_active) "
            "VALUES ('Integration Carriers Admin', :e, :h, 'admin', 1, 1)"
        ), {"e": ADMIN_EMAIL, "h": hash_password(ADMIN_PASSWORD)})

        await db.execute(text(
            "INSERT INTO carriers (name, host, port, priority, status, outbound_prefix) "
            "VALUES ('Integration Test Carrier', '10.0.0.99', 5060, 10, 'active', '9999')"
        ))
        carrier_id = (await db.execute(text("SELECT LAST_INSERT_ID()"))).scalar()

        # DOS prefijos en el mismo grupo — el bug real solo se dispara con
        # executemany() de 2+ filas (con 0 o 1 el código no llega a ese
        # camino, o aiomysql no reescribe nada).
        for prefix, dest in [("777701", "Integration Dest 1"), ("777702", "Integration Dest 2")]:
            await db.execute(text(
                "INSERT INTO prefixes (prefix, destination, group_name) VALUES (:p, :d, :g)"
            ), {"p": prefix, "d": dest, "g": GROUP_NAME})

        await db.commit()
        return carrier_id


@pytest.mark.asyncio
async def test_add_group_buy_rate_with_multiple_prefixes_succeeds(client, seeded_carrier):
    """Antes del fix: 500 Internal Server Error apenas el grupo tenía 2+ prefijos."""
    carrier_id = seeded_carrier

    login = await client.post("/api/auth/login", data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        f"/api/admin/carriers/{carrier_id}/group-rates",
        json={"group_name": GROUP_NAME, "buy_rate": 0.0123, "connectcharge": 0.001, "billingblock": 6},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["updated"] == 2

    # Confirmar que las dos filas realmente quedaron con los valores correctos
    # (no solo que el endpoint no explotó) — el bug de aiomysql, si volviera a
    # aparecer con otra variante de la query, podría insertar filas pero con
    # el ON DUPLICATE KEY UPDATE corrompido en vez de tirar 500.
    from database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(text(
            "SELECT buy_rate, connectcharge, billingblock FROM carrier_rates WHERE carrier_id = :cid ORDER BY prefix_id"
        ), {"cid": carrier_id})).all()
    assert len(rows) == 2
    for buy_rate, connectcharge, billingblock in rows:
        assert float(buy_rate) == pytest.approx(0.0123)
        assert float(connectcharge) == pytest.approx(0.001)
        assert billingblock == 6

    # Re-aplicar (camino del ON DUPLICATE KEY UPDATE, no del INSERT inicial)
    # con valores distintos — confirma que VALUES(columna) efectivamente
    # actualiza, no solo que el primer INSERT funcionó.
    resp2 = await client.post(
        f"/api/admin/carriers/{carrier_id}/group-rates",
        json={"group_name": GROUP_NAME, "buy_rate": 0.05, "connectcharge": 0.0, "billingblock": 1},
        headers=headers,
    )
    assert resp2.status_code == 201, resp2.text
    async with AsyncSessionLocal() as db:
        rows2 = (await db.execute(text(
            "SELECT buy_rate, billingblock FROM carrier_rates WHERE carrier_id = :cid"
        ), {"cid": carrier_id})).all()
    assert len(rows2) == 2
    for buy_rate, billingblock in rows2:
        assert float(buy_rate) == pytest.approx(0.05)
        assert billingblock == 1
