# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Fixtures de tests de integración — a diferencia del resto de backend/tests/
(FakeSession, sin DB), estos SÍ hablan con una MariaDB real a través de la
app FastAPI completa (httpx.AsyncClient + ASGITransport), ejercitando
Depends(require_admin)/Depends(require_client)/Depends(require_permission)/
Depends(require_api_key) de punta a punta — la re-auditoría v2.56.0 encontró
que ninguno de esos se ejecuta jamás en la suite de FakeSession.

Requieren DATABASE_URL apuntando a una MariaDB real y alcanzable (CI la
provee vía el job backend-tests, ver .github/workflows/ci.yml; local:
exportar DATABASE_URL antes de correr pytest). Si no hay una DB real
alcanzable, todos los tests de este paquete se saltan limpio — el resto de
la suite (FakeSession) nunca depende de esto.
"""
import os
from urllib.parse import urlparse

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text


def _database_url_looks_real() -> bool:
    url = os.environ.get("DATABASE_URL", "")
    # el default dummy de tests/conftest.py apunta a "localhost/voxikam_test"
    # con user "test" — cualquier otra cosa se asume real e intencional.
    return bool(url) and "test:test@localhost/voxikam_test" not in url


def _can_connect_sync() -> bool:
    """
    Chequeo de conectividad SÍNCRONO a propósito (pymysql, no aiomysql): un
    fixture scope="session" que abre una conexión async con asyncio.run()
    crea su PROPIO event loop, distinto del loop function-scoped que usa
    cada test de pytest-asyncio — cualquier conexión que quede pooleada
    contra ese loop descartado revienta el próximo test con "Future
    attached to a different loop". Evitarlo del todo usando un driver síncrono
    acá es más simple que pelear con el scope del loop.
    """
    try:
        import pymysql
        u = urlparse(os.environ["DATABASE_URL"].replace("mysql+aiomysql://", "mysql://"))
        conn = pymysql.connect(
            host=u.hostname, port=u.port or 3306,
            user=u.username, password=u.password or "",
            database=u.path.lstrip("/"), connect_timeout=3,
        )
        conn.close()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def integration_db_available():
    if not _database_url_looks_real():
        pytest.skip("DATABASE_URL sigue en el default dummy — tests de integración requieren una MariaDB real (ver conftest.py de este paquete)")
    if not _can_connect_sync():
        pytest.skip("No se pudo conectar a DATABASE_URL — tests de integración requieren una MariaDB real y alcanzable")
    return True


@pytest.fixture(scope="session", autouse=True)
def _nullpool_engine_for_tests(integration_db_available):
    """
    database.py crea su engine UNA vez a nivel de módulo, con el pool
    default de SQLAlchemy — pensado para vivir dentro de UN solo event loop
    por el tiempo de vida del proceso (así corre uvicorn en producción). Cada
    test de pytest-asyncio arranca su PROPIO event loop nuevo; una conexión
    que quedó en el pool de un test anterior (loop ya cerrado) revienta con
    "Future attached to a different loop" apenas otro test la reutiliza.
    Reemplazar el engine por uno con NullPool (nunca reusa una conexión
    entre checkouts) elimina el problema de raíz — el costo extra de abrir
    una conexión TCP por query es aceptable para una suite de ~15 tests, no
    para producción real (por eso esto vive solo acá, nunca en database.py).

    Dos módulos hacen `from database import AsyncSessionLocal` (copian la
    referencia al importar, no quedan enganchados a reasignaciones
    posteriores de database.AsyncSessionLocal) — se parchean explícitamente
    además del módulo database en sí.
    """
    import database
    import main
    import middleware.security as security_mw
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool

    test_engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    TestSessionLocal = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    originals = (database.engine, database.AsyncSessionLocal, main.AsyncSessionLocal, security_mw.AsyncSessionLocal)
    database.engine = test_engine
    database.AsyncSessionLocal = TestSessionLocal
    main.AsyncSessionLocal = TestSessionLocal
    security_mw.AsyncSessionLocal = TestSessionLocal
    yield
    database.engine, database.AsyncSessionLocal, main.AsyncSessionLocal, security_mw.AsyncSessionLocal = originals


@pytest.fixture
async def db_session(integration_db_available):
    from database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        yield db


@pytest.fixture
async def client(integration_db_available):
    import main
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def clean_rate_limits(db_session):
    """Los tests de login pegan contra el rate limiter real (rate_limit.py) —
    arrancar cada test sin contadores viejos de una corrida anterior."""
    await db_session.execute(text("DELETE FROM rate_limit_counters"))
    await db_session.commit()
    yield
