# backend/

FastAPI async — API REST del sistema. Corre como servicio `voxikam-backend` en `127.0.0.1:8000`.

## Stack

- **FastAPI 0.139** + **uvicorn** (`__WORKERS__` workers, ver `systemd/voxikam-backend.service`)
- **SQLAlchemy 2.0** async + **aiomysql** (driver MariaDB)
- **bcrypt** directo para hashes (sin passlib), **python-jose** para JWT
- **WeasyPrint** para PDF de facturas
- **Jinja2** para renderizar HTML de facturas

## Archivos raíz

| Archivo | Rol |
|---|---|
| `main.py` | Crea app FastAPI, monta `SecurityMiddleware`, llama `register_routes()`, billing worker (c/30s) |
| `routes.py` | **Único lugar para agregar rutas.** Lista `ROUTES` con tuples `(router, prefix, tags)` |
| `auth.py` | `hash_password`, `verify_password`, `create_token`, `get_current_user`, `require_admin`, `require_client`, `require_permission`, `require_reseller_permission`, `require_api_key` |
| `database.py` | `AsyncEngine`, `AsyncSessionLocal`, `get_db()` (dependencia FastAPI) |
| `rating.py` | `billable_blocks()`/`calc_bill()` — única fuente de verdad para el cálculo de facturación (usado por `main.py` y `routers/cdrs.py`) |
| `balance.py` | `apply_balance_change()` — UPDATE+SELECT+INSERT de `balance_transactions` compartido por los ajustes manuales de balance |
| `rate_limit.py` | Rate limiting compartido entre workers, respaldado en MariaDB (`rate_limit_counters`) — ver más abajo |
| `sync_runner.py` | Wrapper de `subprocess.Popen` para `gen_dispatcher.py`/`gen_nftables.py`, dispara desde los routers admin tras cambios de config y loguea WARNING si el script falla |
| `techprefix.py` | Generación/validación de techprefix (`next_sub_customer_prefix`, `next_campaign_prefix`, `techprefix_conflicts`) |

**Listado completo de los 38 routers, con su nivel de auth por defecto:** ver la tabla en `../CLAUDE.md` (sección "Permisos y autenticación por ruta") — no se duplica acá para no desincronizarse.

## Cómo agregar una ruta

1. Crear `routers/mi_modulo.py` con `router = APIRouter()`
2. En `routes.py` agregar a la lista `ROUTES`:
   ```python
   from routers import mi_modulo
   (mi_modulo.router, "/api/admin/mi_modulo", ["Admin · MiModulo"]),
   ```
3. No tocar `main.py`.

## Auth flow

```
POST /api/auth/login  ← form-data: username (email) + password
  └── verify bcrypt
  └── create_token({sub: user_id, role: ..., name: ..., customer_id: ...})
  └── return {access_token, role, name, customer_id, permissions, ...}

GET /api/admin/*  ← Header: Authorization: Bearer <token>
  └── Depends(require_admin) → get_current_user → SELECT user FROM DB (cache 20s)
```

`require_client` permite `admin` Y `client` (admin puede ver el portal). `require_admin` solo
permite `admin`. El portal cliente (`portal.py`, `reseller.py`) usa `require_permission(resource_key)`/
`require_reseller_permission(resource_key)` — resuelven contra el árbol granular
`permission_resources`/`profile_permissions` (ver `../CLAUDE.md`), no un set fijo de columnas `show_*`.

## CDR Ingest (billing)

El camino real: `templates/kamailio.cfg.j2` (`event_route[dialog:end]`) inserta el CDR directo a
MariaDB vía `sql_query()` con `buycost=0` al colgar (BYE) — Kamailio nunca llama HTTP para esto.
`main.py::_billing_worker()` (loop propio, cada 30s) procesa esos CDRs pendientes:
1. Busca el cliente por `techprefix` + `src_ip`
2. `rating.py::calc_bill()` — longest-prefix-match en `rates` (sessionbill) y `carrier_rates` (buycost)
3. `UPDATE cdrs` con `sessionbill`/`buycost` (`lucro` es columna GENERATED = sessionbill - buycost)
4. Descuenta balance del cliente + dispara `check_balance_alert()`
5. Un CDR corrupto/con tarifa faltante se salta con `try/except` por fila — no aborta el batch entero

`POST /api/admin/cdrs/ingest` (protegido por `X-Ingest-Secret`, ver `require_ingest_secret`) existe
como camino HTTP alternativo con la misma lógica de cálculo, pero no tiene un llamador real
conocido en la config de Kamailio actual — ver el docstring de `ingest_cdr()` en `routers/cdrs.py`.

## Portal cliente — límite 200 registros

```python
CLIENT_MAX_ROWS = 200
# El COUNT usa subquery para evitar full table scan:
# SELECT COUNT(*) FROM (SELECT 1 FROM cdrs WHERE ... LIMIT 200) t
```

El response incluye `"capped": true` cuando se llega al límite para que el frontend muestre aviso.

## Middleware (middleware/security.py)

- Rate limiting respaldado en MariaDB (`rate_limit.py`, tabla `rate_limit_counters`, ventana fija) —
  compartido entre workers, no en memoria por proceso (v2.57.0, cerró un hueco real: con
  `--workers>1` el límite en memoria era N veces más débil que el documentado):
  - `/api/auth/login`: 10 req/60s por IP, además de 8 intentos fallidos/5min por cuenta (`routers/auth.py`)
  - `/api/`: 300 req/60s por IP
- Bloquea UAs: `sqlmap`, `nikto`, `masscan`, `nmap`
- Security headers: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, CSP
- Fail-open ante error de DB (logueado) — un hiccup del rate limiter nunca tumba tráfico normal

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
pytest tests/integration/   # requiere DATABASE_URL apuntando a una MariaDB real (se skipea si no está)
```

Al tocar `rating.py::billable_blocks()`/`calc_bill()` o `routers/cdrs.py::ingest_cdr()` — correr
esta suite primero. `test_billable_blocks.py::test_both_callers_use_the_same_function_object`
es la red de seguridad específica: detecta si `main.py` y `routers/cdrs.py` alguna vez vuelven a
divergir en su propia copia en vez de compartir `rating.py`.

## Logs

```bash
journalctl -u voxikam-backend -n 50 -f
```

---

> © 2026 [KPBTec](https://github.com/KPBTec) · Ver [Licencia y Autoría](../AUTHORS.md)
