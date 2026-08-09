# backend/

FastAPI async — API REST del sistema. Corre como servicio `sip-backend` en `127.0.0.1:8000`.

## Stack

- **FastAPI 0.115** + **uvicorn** (2 workers)
- **SQLAlchemy 2.0** async + **aiomysql** (driver MariaDB)
- **bcrypt** directo para hashes (sin passlib), **python-jose** para JWT
- **WeasyPrint** para PDF de facturas
- **Jinja2** para renderizar HTML de facturas

## Archivos raíz

| Archivo | Rol |
|---|---|
| `main.py` | Crea app FastAPI, monta `SecurityMiddleware`, llama `register_routes()`, expone `/api/health` |
| `routes.py` | **Único lugar para agregar rutas.** Lista `ROUTES` con tuples `(router, prefix, tags)` |
| `auth.py` | `hash_password`, `verify_password`, `create_token`, `get_current_user`, `require_admin`, `require_client` |
| `database.py` | `AsyncEngine`, `AsyncSessionLocal`, `get_db()` (dependencia FastAPI) |

## Cómo agregar una ruta

1. Crear `routers/mi_modulo.py` con `router = APIRouter()`
2. En `routes.py` agregar a la lista `ROUTES`:
   ```python
   from routers import mi_modulo
   (mi_modulo.router, "/api/admin/mi_modulo", ["Admin · MiModulo"]),
   ```
3. No tocar `main.py`.

## Routers

| Archivo | Prefix | Descripción |
|---|---|---|
| `auth.py` | `/api/auth` | `POST /login` (OAuth2 form), `GET /me` |
| `customers.py` | `/api/admin/customers` | CRUD clientes + IPs |
| `carriers.py` | `/api/admin/carriers` | CRUD carriers |
| `rates.py` | `/api/admin/rates` | Planes tarifarios + tarifas por destino |
| `cdrs.py` | `/api/admin/cdrs` | `POST /ingest` (Kamailio BYE), `GET /list` con filtros |
| `live.py` | `/api/admin/live` | Llamadas activas en tiempo real |
| `reports.py` | `/api/admin/reports` | Dashboard KPIs + resúmenes día/mes |
| `invoices.py` | `/api/admin/invoices` | Generar factura, marcar pagada, descargar PDF |
| `firewall.py` | `/api/admin/firewall` | CRUD reglas IP ALLOW/DENY/JAIL |
| `portal.py` | `/api/my` | Endpoints cliente: `/calls`, `/overview`, `/invoices`, `/trunk-guide` |

## Auth flow

```
POST /api/auth/login  ← form-data: username (email) + password
  └── verify bcrypt
  └── create_token({sub: user_id, role: ..., name: ..., customer_id: ...})
  └── return {access_token, role, name, customer_id}

GET /api/admin/*  ← Header: Authorization: Bearer <token>
  └── Depends(require_admin) → get_current_user → SELECT user FROM DB
```

`require_client` permite `admin` Y `client` (admin puede ver el portal).
`require_admin` solo permite `admin`.

## CDR Ingest (billing)

Kamailio llama `POST /api/admin/cdrs/ingest` al colgar (BYE). El endpoint:
1. Busca el cliente por `techprefix` + `src_ip`
2. Longest-prefix-match en `rates` para calcular `sessionbill`
3. Mismo match en `carrier_rates` para calcular `buycost`
4. Inserta en `cdrs` (lucro = sessionbill - buycost, columna GENERATED)
5. Descuenta balance del cliente
6. Elimina de `active_calls`

## Portal cliente — límite 200 registros

```python
CLIENT_MAX_ROWS = 200
# El COUNT usa subquery para evitar full table scan:
# SELECT COUNT(*) FROM (SELECT 1 FROM cdrs WHERE ... LIMIT 200) t
```

El response incluye `"capped": true` cuando se llega al límite para que el frontend muestre aviso.

## Middleware (middleware/security.py)

- Rate limiting in-memory con sliding window (sin Redis):
  - `/api/auth/login`: 10 req/60s por IP
  - `/api/`: 300 req/60s por IP
- Bloquea UAs: `sqlmap`, `nikto`, `masscan`, `nmap`
- Security headers: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, CSP

## Variables de entorno (.env generado por deploy.sh)

```
DATABASE_URL=mysql+aiomysql://voxikam:<pass>@127.0.0.1:<port>/sip_platform
JWT_SECRET=<hex32>
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=480
PUBLIC_IP=...
PRIVATE_IP=...
INSTALL_DIR=...
LOG_DIR=...
```

## Tests

Suite de caracterización (`tests/`) enfocada en la matemática de facturación
(`_billable_blocks`, `_calc_bill`, `ingest_cdr`) — la parte del backend donde
un bug se traduce directo en plata mal cobrada. Sin DB real: usa dobles de
prueba (`tests/fakes.py`) que matchean las queries por contenido en vez de
levantar MariaDB.

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest                      # corre todo tests/, ver pytest.ini
pytest tests/test_calc_bill.py -v
```

Al tocar `_billable_blocks()`, `_calc_bill()` o `ingest_cdr()` — o al extraer
la lógica compartida a un futuro `rating.py` (ver `CLAUDE.md`) — correr esta
suite primero. `test_billable_blocks.py::test_both_copies_agree_across_a_grid_of_inputs`
es la red de seguridad específica para esa extracción: detecta si las dos
copias (`main.py` y `routers/cdrs.py`) divergen.

## Logs

```bash
journalctl -u sip-backend -n 50 -f
```

---

> © 2026 [KPBTec](https://github.com/KPBTec) · Ver [Licencia y Autoría](../AUTHORS.md)
