# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Re-auditoría v2.56.0 (hallazgo QA/alto): la suite de FakeSession nunca
ejercita Depends(require_admin)/Depends(require_client)/
Depends(require_permission)/Depends(require_api_key) — más de 30 routers sin
ningún test. Este archivo cubre lo priorizado por el plan de remediación:
login exitoso + JWT, require_admin rechazando a un cliente, permisos por
resource_key (default_visible), scoping de reseller, y validación de
X-API-Key.

Corre contra una MariaDB real de punta a punta (ver tests/integration/conftest.py)
— es la primera vez que estas dependencias de FastAPI se ejecutan en CI.
"""
import pytest
from sqlalchemy import text

pytestmark = pytest.mark.usefixtures("integration_db_available", "clean_rate_limits")

ADMIN_EMAIL = "integration-admin@voxikam.test"
ADMIN_PASSWORD = "Sup3rSecret!2026"
CLIENT_EMAIL = "integration-client@voxikam.test"
CLIENT_PASSWORD = "ClientPass!2026"
RESELLER_A_EMAIL = "integration-reseller-a@voxikam.test"
RESELLER_B_EMAIL = "integration-reseller-b@voxikam.test"
RESELLER_PASSWORD = "ResellerPass!2026"


@pytest.fixture
async def seeded(integration_db_available):
    """
    Siembra un set fijo de fixtures — idempotente (borra restos de una
    corrida anterior por email antes de insertar), así que corre limpio
    tanto en CI (DB efímera nueva) como localmente contra una DB de prueba
    persistente reusada entre corridas. Function-scoped (no session) a
    propósito: mezclar un fixture async session-scoped con el loop
    function-scoped que usa cada test de pytest-asyncio revienta el pool de
    conexiones de SQLAlchemy ("Future attached to a different loop") — re-
    sembrar por test es más simple que pelear con el scope del loop, y el
    costo (un puñado de DELETE+INSERT) es insignificante.
    """
    from database import AsyncSessionLocal
    from auth import hash_password

    async def _seed():
        async with AsyncSessionLocal() as db:
            for email in (ADMIN_EMAIL, CLIENT_EMAIL, RESELLER_A_EMAIL, RESELLER_B_EMAIL):
                await db.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})
            # balance_transactions no tiene ON DELETE CASCADE contra
            # customers (por diseño — es un ledger, no debería borrarse
            # nunca en producción) — un test anterior (ajuste de saldo del
            # sub-cliente) deja filas ahí que hay que limpiar antes de poder
            # borrar el customer en el siguiente re-seed.
            await db.execute(text("""
                DELETE FROM balance_transactions WHERE customer_id IN (
                    SELECT id FROM customers WHERE email IN (:c, :ra, :rb, 'sub-a@voxikam.test')
                )
            """), {"c": CLIENT_EMAIL, "ra": RESELLER_A_EMAIL, "rb": RESELLER_B_EMAIL})
            # sub-a@voxikam.test primero — es hijo (parent_customer_id) de
            # Reseller A, y esa FK no tiene ON DELETE CASCADE. api_keys sí
            # cascadea sola al borrar el customer.
            await db.execute(text("DELETE FROM customers WHERE email = 'sub-a@voxikam.test'"))
            await db.execute(text("DELETE FROM customers WHERE email IN (:c, :ra, :rb)"),
                              {"c": CLIENT_EMAIL, "ra": RESELLER_A_EMAIL, "rb": RESELLER_B_EMAIL})
            await db.commit()

            await db.execute(text(
                "INSERT INTO users (name, email, password_hash, role, is_superadmin, is_active) "
                "VALUES ('Integration Admin', :e, :h, 'admin', 1, 1)"
            ), {"e": ADMIN_EMAIL, "h": hash_password(ADMIN_PASSWORD)})

            client_cid = await _insert_customer(db, "Integration Client Co", CLIENT_EMAIL)
            await db.execute(text(
                "INSERT INTO users (name, email, password_hash, role, customer_id, is_active) "
                "VALUES ('Integration Client', :e, :h, 'client', :cid, 1)"
            ), {"e": CLIENT_EMAIL, "h": hash_password(CLIENT_PASSWORD), "cid": client_cid})

            reseller_a_cid = await _insert_customer(db, "Reseller A", RESELLER_A_EMAIL, is_reseller=True)
            await db.execute(text(
                "INSERT INTO users (name, email, password_hash, role, customer_id, is_active) "
                "VALUES ('Reseller A User', :e, :h, 'client', :cid, 1)"
            ), {"e": RESELLER_A_EMAIL, "h": hash_password(RESELLER_PASSWORD), "cid": reseller_a_cid})

            reseller_b_cid = await _insert_customer(db, "Reseller B", RESELLER_B_EMAIL, is_reseller=True)
            await db.execute(text(
                "INSERT INTO users (name, email, password_hash, role, customer_id, is_active) "
                "VALUES ('Reseller B User', :e, :h, 'client', :cid, 1)"
            ), {"e": RESELLER_B_EMAIL, "h": hash_password(RESELLER_PASSWORD), "cid": reseller_b_cid})

            # Sub-cliente de Reseller A únicamente — para el test de scoping.
            sub_a_cid = await _insert_customer(db, "Sub-cliente de A", "sub-a@voxikam.test",
                                                parent_customer_id=reseller_a_cid)

            # API key real para el sub-cliente de A, con el mismo hash que
            # auth.py::require_api_key() calcula (sha256 sobre el valor plano).
            import hashlib
            api_key_plain = "vk_live_integration_test_key_0001"
            await db.execute(text(
                "INSERT INTO api_keys (customer_id, label, key_prefix, key_hash, revoked) "
                "VALUES (:cid, 'integration test', :prefix, :h, 0)"
            ), {"cid": sub_a_cid, "prefix": api_key_plain[:12],
                "h": hashlib.sha256(api_key_plain.encode()).hexdigest()})

            await db.commit()

            return {
                "client_cid": client_cid,
                "reseller_a_cid": reseller_a_cid,
                "reseller_b_cid": reseller_b_cid,
                "sub_a_cid": sub_a_cid,
                "api_key_plain": api_key_plain,
            }

    return await _seed()


async def _insert_customer(db, name, email, is_reseller=False, parent_customer_id=None):
    await db.execute(text(
        "INSERT INTO customers (name, email, status, is_reseller, parent_customer_id) "
        "VALUES (:n, :e, 'active', :ir, :pid)"
    ), {"n": name, "e": email, "ir": 1 if is_reseller else 0, "pid": parent_customer_id})
    r = await db.execute(text("SELECT LAST_INSERT_ID()"))
    return r.scalar()


# ── Login exitoso + JWT ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_login_succeeds_and_returns_valid_jwt(client, seeded):
    resp = await client.post("/api/auth/login", data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "admin"
    assert body["access_token"]

    # el token realmente sirve para autenticarse en un endpoint protegido
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == ADMIN_EMAIL


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(client, seeded):
    resp = await client.post("/api/auth/login", data={"username": ADMIN_EMAIL, "password": "not-the-password"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_email_returns_401_not_500(client, seeded):
    resp = await client.post("/api/auth/login", data={"username": "nobody@nowhere.test", "password": "x"})
    assert resp.status_code == 401


# ── require_admin rechaza a un cliente ───────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_endpoint_without_token_returns_401(client, seeded):
    resp = await client.get("/api/admin/customers")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_endpoint_rejects_client_role(client, seeded):
    login = await client.post("/api/auth/login", data={"username": CLIENT_EMAIL, "password": CLIENT_PASSWORD})
    token = login.json()["access_token"]
    resp = await client.get("/api/admin/customers", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_endpoint_accepts_admin_role(client, seeded):
    login = await client.post("/api/auth/login", data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    token = login.json()["access_token"]
    resp = await client.get("/api/admin/customers", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


# ── require_permission por resource_key (default_visible) ───────────────────

@pytest.mark.asyncio
async def test_client_without_profile_gets_platform_defaults_from_login(client, seeded):
    """El cliente de fixture no tiene profile_id — permissions en la respuesta
    de login debe reflejar default_visible de permission_resources tal cual
    (invoices=0 por default, calls=1 por default, ver schema.sql)."""
    login = await client.post("/api/auth/login", data={"username": CLIENT_EMAIL, "password": CLIENT_PASSWORD})
    permissions = login.json()["permissions"]
    assert permissions.get("invoices") is False
    assert permissions.get("calls") is not False


@pytest.mark.asyncio
async def test_client_endpoint_gated_by_disabled_permission_returns_403(client, seeded):
    login = await client.post("/api/auth/login", data={"username": CLIENT_EMAIL, "password": CLIENT_PASSWORD})
    token = login.json()["access_token"]
    # 'invoices' tiene default_visible=0 — el cliente de fixture no tiene
    # override propio ni de perfil, así que require_permission("invoices")
    # debe rechazarlo.
    resp = await client.get("/api/my/invoices", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


# ── Scoping de reseller ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reseller_cannot_touch_another_resellers_sub_customer(client, seeded):
    """Reseller B no debería poder ajustar el balance del sub-cliente que es
    de Reseller A — el guard de scoping (parent_customer_id = mi propio id)
    debe devolver 404, no 200 ni los datos de otro."""
    login = await client.post("/api/auth/login", data={"username": RESELLER_B_EMAIL, "password": RESELLER_PASSWORD})
    token = login.json()["access_token"]
    sub_a_cid = seeded["sub_a_cid"]
    resp = await client.post(
        f"/api/reseller/sub-customers/{sub_a_cid}/balance",
        json={"amount": 10.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reseller_can_touch_their_own_sub_customer(client, seeded):
    login = await client.post("/api/auth/login", data={"username": RESELLER_A_EMAIL, "password": RESELLER_PASSWORD})
    token = login.json()["access_token"]
    sub_a_cid = seeded["sub_a_cid"]
    resp = await client.post(
        f"/api/reseller/sub-customers/{sub_a_cid}/balance",
        json={"amount": 10.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


# ── X-API-Key (api_v1.py) ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_api_v1_without_key_returns_401(client, seeded):
    resp = await client.get("/api/v1/balance")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_v1_with_malformed_key_returns_401(client, seeded):
    resp = await client.get("/api/v1/balance", headers={"X-API-Key": "not-a-real-key"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_v1_with_valid_key_returns_200(client, seeded):
    resp = await client.get("/api/v1/balance", headers={"X-API-Key": seeded["api_key_plain"]})
    assert resp.status_code == 200
