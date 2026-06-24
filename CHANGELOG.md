# Changelog — KPBTec la plataforma anterior

Todas las versiones siguen el esquema `MAJOR.MINOR`:
- **MAJOR** sube cuando hay cambios de arquitectura o breaking changes en el schema/API
- **MINOR** sube cuando se añade un módulo nuevo o mejora significativa

---

## v2.2 — 2026-06-22

### Live dashboard desde Kamailio · CDRs refactorizados · Modo --update

**Live dashboard — fuente de verdad: Kamailio `dlg.briefing`:**
- `GET /admin/live/detail` ahora usa `kamcmd dlg.briefing "ftcISs"` (state=4 = CONFIRMED) como fuente autoritativa, sin zombies posibles
- Cliente identificado por techprefix en `to_uri` (lookup `customers.techprefix` — prefijo más largo primero)
- Carrier identificado cruzando `call_id` con `active_calls.carrier_id` (guardado en CDR-START)
- Si `kamcmd` no responde, fallback automático a `active_calls` DB
- 4 KPIs: Contestadas (Kamailio `ongoing`), En marcación (`connecting+starting`), Clientes activos, Mayor tiempo
- Script de validación: `scripts/test_dlg_briefing.py` — corre en el SBC para verificar parsing antes de desplegar

**CDRs — dos tablas independientes:**
- Tab "Contestadas (200 OK)": filtra `cdrs` (siempre `disposition=ANSWERED`)
- Tab "No establecidas": filtra `cdrs_failed` con SIP codes reales (487, 486, 404, 503...)
- Búsqueda por número de teléfono en ambas tabs (campo `phone` → LIKE en src/dst)
- Botones rápidos de filtro por código SIP: 487 / 486 / 404 / 503
- Badge de color por rango de código SIP (verde <300, azul <400, naranja <500, rojo ≥500)
- Columna `sip_code SMALLINT UNSIGNED DEFAULT 200` añadida a `cdrs`
- `cpslimit` cambiado de `TINYINT UNSIGNED` (max 255) a `SMALLINT UNSIGNED` — soporta valores > 255

**Timeseries — snapshot real de Kamailio (reemplaza conteo de CDRs):**
- `cron_timeseries.py` ahora usa `kamcmd dlg.briefing state=4` como snapshot por minuto
- `answered_count` = llamadas confirmadas en ese instante (concurrentes), no llamadas iniciadas
- Cliente + carrier resueltos desde Kamailio igual que en el live detail
- Fallback a `active_calls` DB si `kamcmd` no responde
- El dashboard ya lee de `calls_timeseries` — no hay cambios en el frontend

**Instalador — modo `--update`:**
- Nuevo modo: `./install.sh --update` — actualiza código, deps, DB y frontend sin tocar Kamailio
- Opción 1 en el menú interactivo (recomendada para despliegues de código en producción)
- Pasos: rsync → pip install → migraciones DB → npm build → crontab → restart sip-backend/frontend/hep → nginx reload
- Kamailio, nftables, MariaDB tuning y configuración de OS no se tocan
- `--upgrade` conserva el comportamiento anterior (completo, incluye Kamailio)

**RTPEngine — CLI socket:**
- `listen-cli = 127.0.0.1:9901` en `rtpengine.conf` — habilita `rtpengine-ctl` para estadísticas por sesión (jitter, packet loss)
- Requiere `systemctl restart rtpengine` en ventana de mantenimiento (corta llamadas activas)

**Update:**
- `./install.sh --update` aplica todas las migraciones de schema (cpslimit, sip_code)
- Kamailio NO se reinicia — las llamadas activas continúan sin interrupción

---

## v2.1 — 2026-06-22

### Fix: Llamadas zombie en active_calls + búsqueda de trazas 14s → <100ms

**Llamadas zombie (active_calls huérfanas):**
- Kamailio: `dlg_set_timeout(5400)` en `event_route[dialog:start]` — cap de 90 minutos por diálogo, evita acumulación infinita si se pierde el BYE
- Kamailio: nuevo `event_route[dialog:expired]` — DELETE automático de `active_calls` cuando el diálogo llega al timeout (limpieza sin intervención)
- Backend: `DELETE /api/admin/live/stale?max_minutes=60` — limpieza manual de registros con más de N minutos
- Frontend: botón "Limpiar colgadas" (visible solo cuando hay llamadas > 1h) con confirmación antes de ejecutar

**Búsqueda Trazas SIP — detección inteligente de tipo de consulta:**
- Call-ID largo (≥ 20 chars, sin `@`) → `call_id = :q` exact match (usa índice → **<100ms** vs 14s)
- Número de teléfono (solo dígitos/+/-) → `from_uri LIKE 'N%'` trailing wildcard (puede usar índice)
- Campo vacío → lista todas las llamadas del día sin filtro adicional
- Fallback → `LIKE '%q%'` solo si no encaja en ningún patrón anterior
- Nuevo índice compuesto `(call_id, captured_at)` en `sip_traces` + migración automática en `--upgrade`
- Límite por defecto reducido de 200 → 100 resultados

**Upgrade:**
- `./install.sh --upgrade` aplica el índice `idx_cid_captured` automáticamente
- Kamailio se reinicia (aplica `dlg_set_timeout`) — hacerlo en horario de baja carga
- Backend/Frontend: `systemctl restart sip-backend sip-frontend` (sin corte de llamadas)

---

## v2.0 — 2026-06-22

### Performance Layer — System Tuning

**sysctl `/etc/sysctl.d/99-kaplabilling.conf`:**
- `net.core.rmem_max/wmem_max = 64 MB` — previene drops de paquetes RTP en bursts
- `net.core.netdev_max_backlog = 30000` — absorbe picos de tráfico antes de que el kernel los procese
- `net.ipv4.ip_forward = 1` — preparación para módulo kernel xt_RTPENGINE (v2.1)
- `nf_conntrack_max = 131072`, `nf_conntrack_udp_timeout = 10` — evita `table full, dropping packet`

**Kamailio (`templates/kamailio.cfg.j2`):**
- `mlock_pages=yes` — RAM de Kamailio nunca se pagea a swap (elimina latency spikes)
- `open_files_limit=65536` — evita `EMFILE` en alta carga
- `tos=0x18` — DSCP CS3 en paquetes SIP para QoS en redes con marking
- `modparam("tm", "hash_size", 2048)` — menos colisiones en tabla de transacciones
- `modparam("dialog", "hash_size", 4096)` — menos colisiones en tabla de diálogos
- `modparam("dispatcher", "ds_ping_latency_stats", 1)` — auto-deprioritiza carriers lentos

**Kamailio systemd override:**
- `LimitNOFILE=65536`, `LimitMEMLOCK=infinity` (requerido por `mlock_pages`)

**RTPEngine (`rtpengine/rtpengine.conf`):**
- `num-threads = 0` — auto-detect CPU cores (antes: default 1 thread)
- `receive-buffer-size = 4194304` — socket buffer 4 MB contra drops en bursts
- `max-sessions = 500` — cap explícito contra resource exhaustion
- `timeout = 60`, `silent-timeout = 3600` — limpieza de streams huérfanos

**RTPEngine systemd override:**
- `LimitNOFILE=65536`, `LimitMEMLOCK=infinity`, `AmbientCapabilities=CAP_NET_ADMIN CAP_NET_RAW CAP_SYS_NICE`

**MariaDB (auto-sizing por RAM):**
- `innodb_buffer_pool_size` — calculado automáticamente (512 MB / 1 GB / 2 GB según RAM)
- `innodb_flush_log_at_trx_commit = 2` — CDR inserts 3-5× más rápidos (máx 1s de datos en riesgo ante crash de kernel)
- `innodb_log_buffer_size = 32M`, `innodb_flush_method = O_DIRECT`

**Sistema:**
- `nf_conntrack_sip` blacklisteado — el helper kernel interfería con RTPEngine reescribiendo SDPs
- NIC ring buffers → 4096 (via udev + aplicado al instante) — absorbe bursts de hardware
- `/etc/default/kamailio MEMORY=256` — Kamailio arranca con 256 MB de shared memory

**Pendiente v2.1:**
- `xt_RTPENGINE` kernel module (60-80% menos CPU en RTP, requiere staging)
- NOTRACK nftables para puertos SIP/RTP

**Upgrade:**
- `./install.sh --upgrade` — PASO 8b aplica todo el tuning automáticamente
- Kamailio se reinicia al final (recoge `mlock_pages`, `hash_size`, `MEMORY=256`)
- RTPEngine: reiniciar manualmente en horario de baja carga para recoger `num-threads` y `receive-buffer-size`

---

## v1.9 — 2026-06-22

### Nuevo: Dashboard timeseries + Call State en CDRs

**Dashboard llamadas por minuto:**
- Tabla `calls_timeseries`: snapshot por minuto de llamadas por cliente y carrier (retención 25h)
- Cron cada 1 minuto: `scripts/cron_timeseries.py` agrega CDRs del minuto anterior con UPSERT
- Endpoint `GET /api/timeseries/admin?range=1|3|6|12` — series para gráfico admin (por cliente y carrier)
- Endpoint `GET /api/timeseries/my?range=1|3|6|12` — serie del cliente autenticado (por carrier)
- Dashboard admin: gráfico SVG de líneas con selector 1h/3h/6h/12h + toggle "por cliente / por carrier"
- Portal cliente overview: gráfico de líneas propio con el mismo selector de rango
- Componente `CallsChart` SVG puro (sin deps nuevas), con área bajo la curva, tooltip y leyenda

**Call State en CDRs (estilo sngrep/Magnus):**
- Columna `call_state VARCHAR(20)` en `cdrs` y `cdrs_failed`
- Al ingest se deriva automáticamente: ANSWERED→COMPLETED, BUSY→BUSY, NO_ANSWER→CANCELLED, FAILED→REJECTED
- Kamailio puede enviar `call_state=DIVERTED` en el payload para llamadas transferidas
- Tabla admin CDRs: columna "Call State" con badge de color (verde/amarillo/gris/rojo/azul)
- Registros previos sin `call_state` se muestran correctamente con fallback desde `disposition`

**Upgrade:**
- `ALTER TABLE cdrs ADD COLUMN IF NOT EXISTS call_state` (safe)
- `ALTER TABLE cdrs_failed ADD COLUMN IF NOT EXISTS call_state` (safe)
- `CREATE TABLE IF NOT EXISTS calls_timeseries`

---

## v1.7 — 2026-06-21

### Nuevo: Acceso al portal por cliente + Firewall por servicio + Normalización de números

**Acceso al portal del cliente:**
- Admin puede crear usuario portal desde el detalle del cliente (antes solo existía el endpoint, sin UI)
- Sección "Acceso al portal" en `/customers/{id}`: crear usuario con nombre/email/contraseña, eliminar acceso, cambiar contraseña
- Backend: `POST /{cid}/user` valida que no exista duplicado (409), `DELETE /{cid}/user`, `PUT /{cid}/user/password`
- `GET /admin/customers/{cid}` ahora incluye `portal_user: {id, name, email}` o `null`

**Firewall por servicio/puerto:**
- Reglas globales ALLOW ahora admiten restricción de puerto: SIP (5060 UDP/TCP), RTP (20000-40000 UDP), SSH (puerto configurado TCP), Todos (comportamiento anterior)
- Schema: columna `service ENUM('all','sip','rtp','ssh')` en `firewall_rules`
- `gen_nftables.py` genera `manual_rules.nft` con reglas nft por servicio (DENY explícitos + ALLOW con puerto restringido)
- `nftables.conf` incluye `manual_rules.nft` antes de carriers para que los DENYs prevalezcan
- Upgrade: `ALTER TABLE firewall_rules ADD COLUMN IF NOT EXISTS service` se aplica automáticamente
- Setting `ssh_port` guardado en DB durante install/upgrade para que gen_nftables lo use dinámicamente

**Normalización de números destino (billing fix):**
- El CDR ingest ahora normaliza `dst_number` antes del prefix-matching de billing:
  1. Strip del `techprefix` del cliente (el cliente envía `TECHPREFIX+NUMERO`, ej: `80011234567890` → `1234567890`)
  2. Strip del `outbound_prefix` del carrier si Kamailio reescribió el R-URI antes de generar el CDR
- `dst_number_raw` conserva el número tal como llegó en el payload (para auditoría)
- `dst_number` almacena el número E.164 limpio (sin prefijos), para billing y display
- Documentación del routing Kamailio en `docs/kamailio-routing.md` (snippet de kamailio.cfg con strip de techprefix + dispatcher group por cliente)

---

## v1.6 — 2026-06-21

### Nuevo: Mini-Homer embebido (trazas SIP desde el panel admin)

El admin puede ver el flujo SIP completo de cualquier llamada directamente desde el navegador, sin acceso SSH ni herramientas externas.

**Backend:**
- Servicio `sip-hep` (`backend/hep_listener.py`): receptor UDP HEP3 en `127.0.0.1:9060`, Python asyncio
- Tabla `sip_traces` en MariaDB: retención solo del día actual (limpieza automática a las :00)
- Batch insert de 200ms + `INSERT LOW_PRIORITY` para no competir con las queries de billing
- Endpoint `/api/admin/traces`: búsqueda por número o Call-ID, stream en vivo con `since_id` incremental
- 16 campos extraídos por mensaje: call_id, ts, src/dst IP:port, method, status, from/to URI, request_uri, user_agent, via_branch, CSeq, Reason, raw_message

**Frontend:**
- Página `/traces` con dos tabs:
  - **Stream en vivo**: tabla de todo el tráfico SIP en tiempo real, auto-refresh 1s
  - **Buscar llamada**: búsqueda por fecha + número/Call-ID, ladder SIP multicolumna dinámico
- Ladder multicolumna: detecta los nodos IP:port del trace y dibuja N columnas (Carrier | SBC | Asterisk etc.)
- Link "SIP" en la tabla de CDRs abre directamente la traza de esa llamada

**Instalador:**
- `install.sh` ahora detiene/inicia/verifica `sip-hep` junto con los demás servicios
- `chk rsync` en `03_install_deps.sh`

---

## v1.5

### Nuevo: Portal cliente + Facturación + Modos de instalación

**Portal cliente** (`/my/*`):
- Resumen de saldo, llamadas del mes, últimas facturas
- Detalle de llamadas propias con filtros
- Trunk Guide: credenciales SIP, IP del SBC, ejemplos de configuración
- Facturas propias en PDF

**Facturación:**
- Admin → Invoices → seleccionar cliente y período → generar PDF
- Cálculo automático: llamadas × tarifa − margen

**Instalador:**
- Modo `upgrade`: detecta la instalación existente via `/etc/kaplabilling.conf`, detiene servicios, sincroniza código con rsync, aplica migraciones de schema
- Modo `reinstall`: elimina datos y reinstala desde cero conservando la ruta instalada
- Flags `--upgrade` / `--reinstall` para automatización
- `release.conf`: nombre, versión y defaults centralizados — editar para re-brandear

---

## v1.0

### Release inicial

- **Instalador** `install.sh`: Debian 12, single-command, ~10 min, sin dependencias previas
- **Backend** FastAPI async: auth JWT, CDRs en tiempo real, carriers, customers, rates, firewall, reports, invoices
- **Frontend** Next.js 15 standalone: panel admin completo con Tailwind v4, dark mode
- **Live dashboard**: llamadas activas en tiempo real via polling
- **Kamailio SBC** + RTPEngine configurados automáticamente
- **nftables** gestionado desde el panel (carriers + clientes en IPs)
- **MariaDB** puerto aleatorio, bind 127.0.0.1
- Usuario `kaplabilling` sin shell, permisos mínimos
