# Changelog — KPBTec VoxiKam

Todas las versiones siguen el esquema `MAJOR.MINOR.PATCH` (homogeneizado con VoxiDet — antes era `MAJOR.MINOR`, los headers `vX.Y` anteriores a v2.6.0 quedan como están, sin reescribir historial):
- **MAJOR** sube cuando hay cambios de arquitectura o breaking changes en el schema/API
- **MINOR** sube cuando se añade un módulo nuevo o mejora significativa
- **PATCH** sube en bug fixes, ajustes de UI, correcciones menores

---

## v2.52.4 — 2026-07-27

### deploy.sh: 3378 → 2417 líneas (-961, -28%) — migraciones históricas verificadas y podadas contra datos reales

Pedido explícito tras v2.52.3: optimizar el bloque de "Migraciones DB" (1194 líneas acumuladas
desde el origen del proyecto), pero sin repetir el error de la vez anterior (una comparación
"schema.sql solo vs. schema.sql + migraciones" contra una DB vacía, que dio un falso "0 diferencias"
porque el propio `mysql` nunca llegó a correr). Esta vez, con datos reales:

1. Se armó un script (`mysqldump --single-transaction`) para exportar un dump real de producción:
   esquema completo de todas las tablas + datos completos de las tablas de referencia chicas
   (customers, carriers, prefixes, rates, areas, etc.) + una muestra de 500.000 CDRs reales de
   `cdrs`, con `src_number`/`dst_number` enmascarados (se conserva el prefijo real para que el
   matching siga siendo representativo, se randomiza el resto — `prefix_matched` se copia tal cual,
   sin enmascarar, para que los reportes por área sigan siendo 100% representativos).
2. Cargado en MariaDB real (Docker), con dos vueltas de transferencia fallidas en el medio (un
   `scp` cortado a mitad de camino, y una corrida desde dentro de la sesión SSH a `vd1sbc2` en vez
   de desde la máquina local — ambas detectadas por tamaño de archivo no coincidente, no asumidas).
3. Corriendo el bloque COMPLETO de migraciones (~570 líneas por rama) contra ese snapshot real y
   comparando `mysqldump --no-data` antes/después: el único cambio estructural real fue la limpieza
   de `show_*` (ver v2.52.3). Dos falsos positivos de `AUTO_INCREMENT` (`areas`, `prefixes`)
   descartados verificando que los IDs "nuevos" no existían — `INSERT IGNORE` sobre una fila que ya
   existía consume el contador sin insertar nada, comportamiento normal de InnoDB.
4. Los 4 scripts `migrate_*.py` embebidos (`migrate_carrier_groups.py`, `migrate_lan_peers.py`,
   `migrate_dedupe_techprefix.py`, `migrate_5digit_techprefix.py`) probados en modo diagnóstico
   contra el mismo snapshot: 3 confirman "nada para migrar"; `migrate_carrier_groups.py` resultó
   **permanentemente roto** para este server — depende de `customers.active_carrier_id`, columna
   que otra migración del mismo bloque ya había borrado (la migración ya cumplió su función hace
   tiempo, según el propio log del primer `--upgrade` de esta sesión) — cada deploy lo invocaba,
   fallaba en la primera query, tragado en silencio por el mismo `2>/dev/null || true` de siempre.
5. Podado en ambas ramas (`--update`/`--upgrade`): se retiraron ~45 `ALTER`/`CREATE TABLE IF NOT
   EXISTS` y las 4 invocaciones de `migrate_*.py`. Se conservó todo lo que NO es "migración vieja":
   la limpieza de `show_*`, el catch-up de `cdr_summary_day_area` (mecanismo permanente, corre en
   cada deploy), `sync_balance_block.py --apply`, y el rename condicional de `connect_charge`.
6. **Reverificación final**: el bloque podado, corrido contra una copia fresca del mismo snapshot
   real, produce resultado idéntico al bloque original de 570 líneas — mismas 500.025 filas de
   `cdrs`, mismos conteos exactos en `areas` (3), `prefixes` (34), `profile_permissions` (82),
   `show_*` limpio en ambas ramas.

Si alguna vez hace falta reconstruir el detalle de qué hacía cada `ALTER` retirado, está en el
historial de git de `deploy.sh` (comentarios originales preservados en cada commit).

---

## v2.52.3 — 2026-07-27

### Migraciones que se pisaban entre sí — columnas show_* legacy resucitando en cada deploy

Origen: el usuario pidió evaluar si el bloque de "Migraciones DB" (1194 líneas acumuladas desde el
origen del proyecto) se podía acortar. Al comparar la estructura real de producción
(`mysqldump --no-data`) contra `db/schema.sql`, apareció algo que una comparación contra una DB
vacía nunca hubiera revelado: `customers.show_calls/show_quality/show_reports/show_invoices/
show_trunk_guide/show_api_access` seguían existiendo en producción pese a que `schema.sql` ya no
las define hace tiempo.

**Causa raíz**: la migración que reemplaza estas columnas por `profile_permissions` (INSERT IGNORE
+ DROP COLUMN IF EXISTS) SÍ se ejecuta y SÍ borra las columnas — pero más abajo, en el mismo run de
deploy, una migración más vieja (del fix de `profile_id` en la auditoría v2.38.0, escrita cuando
`show_*` todavía era el diseño vigente) las vuelve a agregar con `ADD COLUMN IF NOT EXISTS`. Se
borran y se recrean en el mismo deploy, silenciosamente — nadie lo notó porque ambos pasos van
envueltos en `2>/dev/null || true`. Mismo patrón repetido 3 veces (para `show_calls`+5 hermanas,
para `show_api_access`, y para las 4 `show_reseller_*`), duplicado en las ramas `--update` y
`--upgrade` — 30 líneas conflictivas en total, ahora eliminadas.

**Metodología, con una autocorrección en el camino**: la primera verificación (`schema.sql` solo vs.
`schema.sql` + migraciones, contra una DB vacía en Docker) dio "0 diferencias" — pero ese resultado
era inválido: el sandbox no tiene `mysql` instalado fuera del contenedor, así que todos los `$MC
"..." ` de la prueba fallaban con "command not found", tragados por el mismo `2>/dev/null || true`
que se estaba auditando. Detectado al notar que el fix "aplicado" no cambiaba nada en la DB de
prueba. Corregido ruteando las pruebas a través de `docker exec` contra un `mysql` real, y recién
ahí se reprodujo el bug y se confirmó el fix: `customers` termina con `profile_id` pero sin ninguna
columna `show_*`, en ambas tablas afectadas.

**Hallazgo secundario, no relacionado**: se encontró (por el usuario, revisando `/etc/cron.d/`) un
crontab huérfano — `/etc/cron.d/kaplabilling`, del nombre anterior del proyecto — corriendo cada
minuto en paralelo contra `/opt/kaplabilling` (que ya no existe), generando sesiones PAM y líneas de
error en `dlg_stats.log` sin ningún efecto real. `deploy.sh` nunca lo tocó porque solo escribe/
sobreescribe `/etc/cron.d/voxikam`. Removido manualmente en el servidor (`rm /etc/cron.d/
kaplabilling`) — no requirió cambio de código, cron relee `/etc/cron.d/` sin reinicio.

**Alcance del squash**: se descartó borrar el resto de las ~1194 líneas de migraciones históricas
solo por su redundancia aparente contra una DB vacía — el propio bug de `show_*` demuestra que ese
tipo de comparación no revela conflictos que solo existen cuando hay historia real de por medio. Se
encontró además una diferencia menor y no urgente (un FK duplicado en `areas`, sin efecto funcional)
que confirma lo mismo. Cualquier squash adicional futuro debe validarse contra un dump real de
producción, no contra un estado sintético vacío.

---

## v2.52.2 — 2026-07-26

### "Job no encontrado" en Recalcular tarifas y Reset facturación — carrera en el primer poll del frontend

Reportado en producción real en Facturación → Recalcular tarifas: clickear "Vista previa" devolvía
"Job no encontrado — puede haber expirado" casi de inmediato. Diagnóstico paso a paso antes de
tocar nada (per pedido explícito de verificar antes de asumir):

1. Se descartó un problema de permisos en `/var/lib/voxikam/recalc_jobs/` — `ls -la` mostró dueño y
   permisos correctos (`voxikam:voxikam`, `drwxr-xr-x`), y el archivo del job del intento fallido
   **sí existía en disco, con contenido completo** (`6ad25c13-....json`, 1674 bytes, escrito
   segundos después del click).
2. Eso descarta que el job nunca haya corrido — corrió y terminó bien. El problema es puramente del
   frontend: `pollJob()` esperaba 1.5s y hacía **un único intento** contra `GET /jobs/{job_id}`; si
   ese primer poll llegaba antes de que el `BackgroundTasks` del backend hubiera alcanzado a escribir
   su primer archivo de estado (arranca recién DESPUÉS de que la respuesta del POST ya se mandó al
   cliente — una carrera real, no hipotética, bajo los 11 workers de producción), el 404 se trataba
   como error terminal en vez de "todavía no escribió, seguir esperando".

Fix en los tres lugares que comparten este patrón (`frontend/app/(admin)/billing-recalc/page.tsx`,
`frontend/app/(client)/my/reseller/billing-recalc/page.tsx`, `frontend/app/(admin)/billing-reset/
page.tsx`, este último recién agregado en v2.52.1): un 404 aislado ya no es fatal — solo se declara
error real después de 10 intentos seguidos (~15s), tolerando la ventana de arranque del
`BackgroundTasks` sin falsos negativos.

---

## v2.52.1 — 2026-07-26

### Reset facturación se colgaba con 504 al primer uso real — pasado a background job

Probado en producción real inmediatamente después de v2.52.0: `POST /admin/invoices/reset-module`
devolvió `504` (nginx `proxy_read_timeout 60s`, ver `nginx/voxikam.conf`). Causa raíz, la misma
clase de bug que ya se había resuelto una vez este mismo día en `billing_recalc.py`:

- El `UPDATE customers ... SET balance = -(subquery correlacionada)` reescaneaba la tabla `cdrs`
  completa (4.5M+ filas) **una vez por cada cliente**, sin ningún filtro de fecha ni partición.
- El `DELETE FROM balance_transactions` sin `WHERE` puede estar borrando casi tantas filas como
  `cdrs` tiene — el worker de facturación escribe una fila ahí por cada llamada facturada.

Fix, mismo patrón que `billing_recalc.py` (que documenta exactamente este síntoma en su propio
docstring — "nginx corta a los 60s"):

1. El endpoint ahora lanza un **background job** (`BackgroundTasks` + archivo de estado en
   `/var/lib/voxikam/billing_reset_jobs/<job_id>.json`) y devuelve el `job_id` de inmediato; el
   frontend sondea `GET /reset-module/jobs/{job_id}` cada 2s hasta que termina.
2. El `UPDATE` de balance pasó de subquery correlacionada a un **solo `JOIN`** contra un agregado
   `GROUP BY customer_id` — un escaneo de `cdrs` en total, no uno por cliente. Reverificado contra
   MariaDB real: mismo resultado exacto que la versión anterior (un cliente con 3 CDRs contestados sigue
   dando -300.00).
3. El backup de seguridad dejó de volcar `balance_transactions` fila por fila a JSON (con millones
   de filas posibles, riesgo real de agotar memoria del proceso) — ahora es un `GROUP BY
   customer_id, type` agregado: cuántos movimientos y cuánto sumaban, sin cargar cada fila.

Sin este fix, no había forma de saber si el reset original quedó a medio aplicar (nginx cortó la
respuesta al navegador, pero el `UPDATE` podía seguir corriendo del lado del backend sin que nadie
lo viera) — con el job en background, el estado siempre es consultable y no depende de la ventana
de un solo request HTTP.

---

## v2.52.0 — 2026-07-26

### Facturación → Reset facturación

Al revisar por qué el balance de un cliente (-27,089.69) "no cuadraba" contra su consumo, la causa
salió a la luz en la propia pantalla de Facturas: varias facturas para el mismo cliente con rangos
de fecha solapados (ej. cuatro facturas distintas para "2026-06-01 → 2026-06-22", cada una con un
total distinto según cuántos CDRs de prueba había en ese momento) — datos de prueba generados
mientras se construía el módulo, no un error de cálculo del balance en sí. Reconciliar factura por
factura no era viable; el pedido explícito fue un reset completo del módulo.

Nuevo `POST /admin/invoices/reset-module` + página **Facturación → Reset facturación**
(`frontend/app/(admin)/billing-reset/page.tsx`), con confirmación por texto ("RESETEAR") antes de
habilitar el botón:

1. Vuelca `invoices` y `balance_transactions` completas (todas, de todos los clientes) a un JSON de
   respaldo en `logs/billing_reset_backups/` — mismo criterio que el dump de seguridad que ya hace
   `deploy.sh` antes de aplicar `schema.sql`. No hay "deshacer" desde el panel, pero el respaldo
   permite reconstruir a mano si hiciera falta.
2. Borra los PDFs físicos de cada factura (solo los que realmente viven bajo `INVOICES_DIR`, nunca
   el logo compartido de `branding/`).
3. Borra todas las filas de `invoices` y `balance_transactions`.
4. Recalcula el balance de cada cliente como **deuda pura**: `-(SUM(sessionbill)` de todos sus CDRs
   `ANSWERED`, como si nunca se hubiera acreditado un pago ni una recarga — arranca de cero desde el
   consumo real, sin arrastrar el ruido de las facturas de prueba.

Confirmado con el admin antes de tocar nada (alcance global para todos los clientes; recompute a
deuda negativa, no a cero; facturas son PDFs internos sin validez tributaria/SUNAT, así que un
DELETE liso es aceptable). Verificado contra MariaDB real (Docker) antes de dar la query por buena:
un cliente con 3 CDRs contestados (100.50 + 150.25 + 49.25, con una NO_ANSWER correctamente
excluida) quedó en exactamente -300.00 tras el reset; tablas vaciadas; un cliente sin llamadas quedó
en 0.

---

## v2.51.0 — 2026-07-26

### cdr_summary_day_area quedaba stale tras el backfill de prefix_matched + historial de balance auditable

Reportado en producción real: después del backfill/trigger de v2.48.2, el contador de "CDRs sin área"
(`GET /admin/areas/backfill-status`, lee `cdrs` en vivo) bajaba a casi cero, pero el reporte "Por
destino" filtrado por mes seguía mostrando miles de llamadas en "Sin área" para julio. Causa raíz:
ese reporte, para días ya cerrados, lee `cdr_summary_day_area` — una tabla de resumen que
`scripts/cron_summary.py` escribe una vez por noche y que `backfill_prefix_matched.py` nunca tocaba,
así que quedaba congelada con el `prefix_matched` viejo/NULL para siempre, sin importar cuántas
veces se corriera "Recalcular histórico" desde el panel.

1. `scripts/backfill_prefix_matched.py` ahora, después de corregir `cdrs.prefix_matched`, reconstruye
   `cdr_summary_day_area` día por día para todo el histórico (misma query exacta que usa
   `cron_summary.py` cada noche, en loop). Se dispara solo con clickear "Recalcular histórico" en
   Reportes → Por destino, o automáticamente la primera vez que corre un `--update`/`--upgrade` en un
   server que todavía no tenía el trigger (mismo guard `PREFIX_BACKFILL_TRIGGERED` de v2.48.2).
2. **Bug real encontrado probando el fix contra MariaDB antes de aplicarlo**: sin un `DELETE` del día
   antes de reinsertar, el bucket viejo ("Sin área") quedaba como fila fantasma junto al nuevo bucket
   correcto, duplicando nbcall/sessionbill/etc. de ese día en el reporte. Corregido agregando el
   `DELETE FROM cdr_summary_day_area WHERE summary_date = :d` antes del INSERT, y reverificado: un
   día con 2 llamadas reales seguía mostrando 2, no 4.
3. **Historial de balance**: nuevo `GET /admin/customers/{id}/balance-transactions` + panel "Historial
   de balance" en la ficha del cliente (Clientes → \[cliente\]). El ledger real (`balance_transactions`
   — una fila por llamada facturada vía `backend/main.py::_billing_worker()`, ajuste manual, pago de
   factura o recálculo de tarifas) ya existía en la base desde hace tiempo, pero no había ninguna
   pantalla para verlo — sin eso, un balance que "no cuadra" contra la suma de consumo esperada no se
   podía auditar. El endpoint de ajuste manual (`POST /{cid}/balance`) ya escribía ahí; ahora también
   se puede leer.

Sobre "¿deploy.sh debería forzar una migración completa si detecta una versión vieja?": ya lo hace —
`schema.sql` (con `CREATE TRIGGER IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`, etc.) se reaplica
completo en CADA `--update`/`--upgrade` sin importar cuántas versiones de salto haya, no hay lógica
condicional por versión que se pueda saltar. El backfill de este release sigue el mismo patrón: el
guard es "¿ya corrió alguna vez?", no "¿qué versión tenías antes?".

Verificado con Docker rootless + MariaDB real (no solo lectura de código): reproducido el bug de
filas fantasma, corregido, y reconfirmado con una segunda corrida (idempotente, mismo resultado).
`npm run build` y `py_compile` limpios.

---

## v2.50.0 — 2026-07-26

### Áreas: gestión separada del reporte + Consumos con agrupación por área/prefijo y auto-generado

Reorganización pedida tras revisar el panel en producción — Reportes → Áreas mezclaba dos
funciones distintas (crear/editar áreas y ver el reporte de rentabilidad por destino) en una
sola pantalla, y la página de Consumos exigía apretar "Generar" a mano cada vez que se abría.

1. **Separación de responsabilidades**: la gestión de áreas (crear, editar nombre/país/descripción,
   eliminar) se mudó a una página nueva, `frontend/app/(admin)/area-groups/page.tsx`, con su
   propia entrada en el sidebar bajo **Tarifas → Áreas**. Reportes → Áreas se renombra a **"Por
   destino"** y queda únicamente con la tabla de rentabilidad (país/área/prefijo), sin ningún
   formulario de edición — mismo criterio que ya separa Prefijos/Pricelists/Tarifas.
2. **Consumos auto-genera** el reporte al entrar a la página y cada vez que cambia el período o la
   vista seleccionada, en vez de requerir un clic manual en "Generar" (el botón queda como
   "Actualizar", refresco opcional).
3. **Consumos agrega "Por área" y "Por prefijo"** junto a las vistas existentes "Por cliente"/"Por
   carrier", reusando el mismo endpoint `GET /admin/areas/report?by=area|prefix` que ya alimenta
   el reporte "Por destino" — sin backend nuevo.

Verificado con `npm run build` completo tras cada cambio (ambas páginas nuevas/modificadas
compilan y quedan listadas en el build de Next.js) y `py_compile` del backend (sin tocarlo en este
cambio, se confirma que sigue intacto).

---

## v2.49.1 — 2026-07-26

### El backfill de resumen seguía corriendo siempre — bug real en la query de v2.48.1, no detectado hasta ahora

Reportado en producción real: el backfill acotado de v2.48.1 (arranca desde el último día ya
cubierto en la DB) seguía reprocesando el mismo rango completo en cada deploy, siempre. Causa
raíz, confirmada contra el `schema.sql` real (no una tabla de prueba simplificada, que es como se
había probado originalmente — ahí estaba el hueco):

1. La columna de fecha en `cdr_summary_day_reseller`/`cdr_summary_day_area` se llama
   `summary_date`, no `day` — la query original consultaba una columna inexistente, el error
   quedaba silenciado por el `2>/dev/null` del propio mecanismo de seguridad, y siempre caía al
   fallback "nunca corrió".
2. Aunque la columna hubiera estado bien, `cdr_summary_day_reseller` solo tiene filas si existen
   clientes con `reseller_cost IS NOT NULL` (subclientes reales de un reseller) — sin ningún
   reseller configurado, esa tabla queda vacía **para siempre**, y el `LEAST()` contra una tabla
   permanentemente vacía arrastraba el cálculo a 1970 en cada deploy sin importar que
   `cdr_summary_day_area` sí estuviera al día.

Fix: `MAX(summary_date)` (columna correcta) sobre `cdr_summary_day_area` únicamente — su WHERE es
igual de amplio que `cdr_summary_day` (se llena con cualquier CDR real), y `day_reseller` se saca
del cálculo por completo. Verificado reproduciendo el error exacto contra el schema real antes de
aplicar el fix, y confirmando que la query nueva resuelve bien incluso con `day_reseller` vacía.

---

## v2.49.0 — 2026-07-26

### Recalcular tarifas — de "50.000 CDRs o nada" a background job sin límite real

Hallazgo en producción real: un rango de 6 días con 1M+ CDRs ni siquiera podía previsualizarse — el
motor viejo hacía 2-3 queries SQL async POR CDR (misma lógica que `main.py::_calc_bill()`) y tenía
un tope duro de 50.000 por corrida solo para evitar que un rango grande colgara el request HTTP.

Reescrito con el mismo enfoque que `scripts/recalc_billing_blocks.py` (el precedente de este
mecanismo, ya probado en producción): tarifas/prefijos/clientes se cargan en memoria una sola vez,
el longest-prefix-match se hace en Python, y los CDRs se leen/aplican en lotes de 5.000 con
paginación por `id`. Preview y apply ahora arrancan un job en background (`BackgroundTasks` +
estado en `/var/lib/voxikam/recalc_jobs/<job_id>.json`, sondeado por el frontend cada 1.5s con
progreso en vivo) — ya no hace falta que quepa en la ventana de un solo request. Tope de 50k
eliminado por completo. Mismo cambio en `reseller.py` (recálculo propio de resellers) y en las dos
páginas de frontend (admin y reseller).

**Verificado con datos reales antes de reemplazar el motor viejo** — no solo con `py_compile`:
- **Paridad numérica**: 10 CDRs de prueba cubriendo los casos límite reales (bloque de facturación
  cruzado, dentro del bloque inicial, redondeo a minuto completo, `minimal_time_charge`, sin match
  de prefijo, cadena de reseller con `reseller_cost`, CDR sin carrier, CDR con `billsec=0`) — el
  motor nuevo (memoria) da exactamente el mismo resultado que el viejo (SQL por fila) en los 10/10,
  hasta el sexto decimal.
- **Performance real medida**: 2.000 CDRs — 0.477ms/CDR el motor viejo vs 0.0015ms/CDR el nuevo,
  **310x más rápido**. Un rango de 1M de CDRs (el caso real que motivó esto) pasa de ser imposible
  de completar en un request HTTP a procesarse en segundos de cómputo puro.

---

## v2.48.2 — 2026-07-26

### `/system/logs` daba 404 — mismo bug de rsync sin anclar, un tercer caso

`--exclude='logs/'` (sin barra inicial) también excluía `frontend/app/(admin)/system/logs/`, no
solo `$INSTALL_DIR/logs/` — esa página nunca se actualizaba en ningún `--update`/`--upgrade`.
Búsqueda exhaustiva (sin límite de profundidad esta vez) confirma que no quedan más colisiones de
este tipo. Fix: `--exclude='/logs/'`, mismo criterio que el fix de `invoices/` de v2.48.1.

### `prefix_matched` — trigger en MySQL, no cron ni cambio a Kamailio

Hallazgo real: `prefix_matched` (con qué área se clasifica una llamada) solo se calculaba durante
la facturación (`_calc_bill()`/`ingest_cdr()`), y esos dos caminos solo procesan
`disposition='ANSWERED' AND billsec>0` — toda llamada `NO_ANSWER`/`BUSY`/etc. quedaba sin área para
siempre, sin importar cuántas veces se corriera "Recalcular histórico" (esa herramienta solo cubre
el backlog anterior a esta versión, nunca las llamadas nuevas no contestadas). El área de una
llamada depende solo del `dst_number`, no de si se facturó.

Se evaluaron 3 approaches — modificar el INSERT de Kamailio (descartado: agrega latencia real al
hilo de procesamiento de llamadas y no hay forma de probarlo en vivo sin un Kamailio real), un cron
aparte (funciona pero hasta 1 min de lag), y un **trigger `BEFORE INSERT` en MySQL** — se eligió el
trigger: cero lag, no toca Kamailio en absoluto (el INSERT que ya emite queda idéntico), y usa la
misma query de longest-prefix-match que `_calc_bill()` ya corre en producción hoy. Probado con
MariaDB real (Docker), schema completo reaplicado de punta a punta, las 3 dispositions relevantes
y un destino sin prefijo configurado — los 4 casos se comportan como corresponde. `db/schema.sql`
únicamente — no hace falta ningún cambio de rsync/deploy para que el trigger en sí se instale.

Overhead medido (no supuesto): 10.000 inserts de prueba, con 200 prefijos configurados (~6x más
que un caso real) — 4.43ms/insert sin trigger vs 4.58ms/insert con trigger, +3%. Insignificante al
volumen real de la plataforma.

El trigger solo cubre inserts NUEVOS desde que existe — `deploy.sh` (ambos modos, `--update` y
`--upgrade`) lanza además `scripts/backfill_prefix_matched.py --yes` en background una única vez
(marcador `PREFIX_BACKFILL_TRIGGERED`, no se repite en deploys futuros) para completar de una todo
el histórico anterior — no bloquea el deploy, puede tardar minutos con millones de CDRs.

---

## v2.48.1 — 2026-07-25

### Causa raíz real de "el deploy no agarra los cambios del frontend" — bug de rsync, no de código

Días de builds fallando con el mismo error viejo (`show_invoices`) pese a que el código fuente
siempre estuvo corregido. Causa real, reproducida y confirmada con un rsync de prueba antes de
tocar nada: `deploy.sh` sincroniza el código con `--exclude='invoices/'` (sin barra inicial) para
proteger `$INSTALL_DIR/invoices/` (storage real de PDFs) de un `--delete`. Sin la barra inicial,
rsync excluye **cualquier carpeta llamada "invoices" en cualquier nivel del árbol** — incluidas
`frontend/app/(client)/my/invoices/` y `frontend/app/(admin)/invoices/`, que nunca se actualizaban
en ningún `--update`/`--upgrade` desde que se agregó ese exclude, sin importar qué tan al día
estuviera el código fuente. Fix: `--exclude='/invoices/'` (barra inicial, ancla al root de
`$INSTALL_DIR`) en los dos bloques de rsync (`deploy.sh`).

### Backfill de resumen de reseller/área — ya no reprocesa siempre desde el día 1

`cron_summary.py` corría desde el día 1 del mes en CADA `--update`/`--upgrade` (sobre el día 24,
23 corridas casi todas redundantes). Ahora arranca desde el día siguiente al último ya cubierto en
`cdr_summary_day_reseller`/`cdr_summary_day_area` (self-healing, sin marcador aparte) con tope de
31 días. Verificado con MariaDB real: la query y la aritmética de fechas dan el resultado esperado
en los tres casos (datos parciales, sin datos nunca, hueco viejo que dispara el tope).

---

## v2.48.0 — 2026-07-25

### Sistema → Infraestructura — TLS, backup y alertas activables desde la web

Los tres scripts nuevos de v2.47.0 (`setup_tls.sh`, `backup_db.sh`, `cron_infra_alert.py`) solo se
podían operar por SSH. Nueva página admin `Sistema → Infraestructura` (`backend/routers/
system_infra.py`, `/api/admin/system/infra`) para controlar los tres sin salir del panel:

- **HTTPS**: botón activar/desactivar — corre `setup_tls.sh` (o `--disable`, nuevo) con sudo en
  background, muestra el resultado (log de certbot) al terminar. `setup_tls.sh` ahora detecta modo
  no interactivo (sin TTY) para no colgarse esperando un prompt que nadie va a contestar.
- **Backup**: toggle activar/desactivar (`settings.backup_enabled`, respetado por `backup_db.sh`
  antes de correr), botón "Ejecutar ahora", y estado real de la última corrida (MariaDB OK/tamaño,
  ClickHouse OK/no, copia remota sí/no) + lista de los últimos backups en disco con tamaño y fecha.
- **Alertas de infraestructura**: toggle activar/desactivar el envío de correo
  (`settings.infra_alerts_enabled`) — la detección de problemas sigue corriendo igual, solo se
  suprime el correo si está desactivado. Muestra la última verificación y los problemas activos.

Todo protegido con la misma allowlist de sudo exacta que ya usaba `system_services.py` (`sudoers/
voxikam`) — nunca un comando genérico.

### Verificado en vivo antes de este release

MariaDB 11.8.8 real (Docker) + schema.sql completo (49 tablas) + backend real con los privilegios
de DB acotados de v2.47.0 + frontend real (Next.js dev) + login real + Playwright: confirmado que
`FOR UPDATE SKIP LOCKED` (fix de doble facturación) no rompe contra MariaDB real, que el logger
raíz ahora sí emite (`LOGIN_OK` visible en journalctl), que la validación Pydantic de `/ingest`
rechaza payloads inválidos (422) y deja pasar los válidos, y que `/system/infra` renderiza y
reacciona a los toggles con datos reales de principio a fin.

### Otros hallazgos, sin fix todavía

`backend/requirements.txt` tiene `psycopg2-binary` listado pero **nunca importado en ningún lado**
del código — dependencia muerta (el proyecto usa MariaDB/ClickHouse, no Postgres), agrega tiempo de
instalación y una dependencia de sistema (libpq) sin necesidad real.

---

## v2.47.0 — 2026-07-25

### Auditoría de arquitectura completa (seguridad, aplicación, despliegue, monitoreo, logging) — 17 hallazgos cerrados

Revisión de punta a punta con 5 agentes en paralelo, cada uno con evidencia archivo:línea contra
el código real. De los 36 hallazgos, se cerraron los 4 críticos y los 8 altos, más 5 medios de
alto impacto/bajo riesgo.

**Críticos:**
- `backend/main.py::_billing_worker()` podía facturar el mismo CDR dos veces con `--workers > 1`
  (uvicorn multi-proceso, configuración real de producción): sin lock de fila, dos procesos podían
  tomar el mismo CDR pendiente en la misma ventana de 30s. Fix: `FOR UPDATE SKIP LOCKED` en el
  SELECT — sets disjuntos garantizados entre workers, sin cambios de schema.
- Cero TLS en toda la plataforma — nuevo `scripts/setup_tls.sh` (certbot + nginx, deja
  `TLS_ENABLED=1` en el marcador para que `deploy.sh` deje de sobrescribir el vhost después).
- Cero backup automático de la DB — nuevo `scripts/backup_db.sh` (MariaDB + best-effort
  ClickHouse, retención local + sync remoto opcional), cron diario 02:30.
- `schema.sql` podía fallar a mitad de un `--upgrade` con los servicios ya detenidos y sin ningún
  camino de vuelta — ahora hace un dump de seguridad justo antes y, si falla, imprime el comando
  exacto de restore en vez de morir en silencio.

**Altos:**
- Logger raíz del backend nunca se configuraba — casi ningún `log.info()` llegaba a ningún lado
  (ni siquiera al del propio billing worker). `logging.basicConfig()` agregado en `main.py`.
- Usuario de MariaDB con `GRANT ALL PRIVILEGES` → acotado a lo que el backend usa de verdad
  (SELECT/INSERT/UPDATE/DELETE/CREATE/ALTER/INDEX — ALTER se mantiene por las particiones de
  `cron_partitions.py`), re-aplicado en cada deploy para que servers ya instalados converjan.
- Build de frontend sin red de seguridad: si `npm run build` falla, ahora se restaura el build
  anterior que funcionaba (backend/DB sí quedan actualizados) en vez de dejar el frontend caído.
  Health-check real (`curl /api/health`) después de cada restart de servicios.
- Nuevo `scripts/cron_infra_alert.py` — el único mecanismo que EMPUJA una alerta por correo
  cuando un cron se cuelga (incluido `dlg_stats`, invisible para `cron_health.py` por correr como
  root) o disco/memoria se agotan. Antes todo el monitoreo era pull-only.
- Hardening systemd (`ProtectSystem=full`, `ProtectHome`, `PrivateTmp`) en los 3 `.service` —
  `NoNewPrivileges` deliberadamente OMITIDO en `voxikam-backend` (invoca `sudo` real para
  nft/kamcmd/fail2ban-client; mismo bug que ya pasó en VoxiDet si se agrega ahí).
- `POST /ingest` (CDRs) validaba `payload: dict` crudo — nuevo `CdrIngestIn` (Pydantic).

**Medios:** longitud mínima de password en el portal de cliente (ya existía en admin_users, faltaba
acá), log de login exitoso (antes solo se logueaba el fallido), `/api/docs`/`/redoc`/`/openapi.json`
apagados por default (`ENABLE_API_DOCS`), logrotate para `logs/*.log` de cron + retención de
journald (1GB/30 días), `app/error.tsx` + `app/global-error.tsx` en el frontend (antes cero
captura de errores de cliente) reportando a un nuevo `POST /api/client-errors`.

**Otros, encontrados en el camino:** regla de nftables duplicada abría SSH a cualquier IP pese a
la restricción por `MGMT_IP` una línea arriba (`nftables/nftables.conf`) — eliminada.

**Diagnóstico también entregado, sin fix todavía (fuera de este alcance):** ~20 hallazgos medios/
bajos restantes — ver el mapa de arquitectura completo generado esta sesión.

---

## v2.46.0 — 2026-07-24

### Sistema de permisos granular (estilo MagnusBilling) — reemplaza los 10 flags sueltos

Los 10 `show_*` (uno por columna en `customers`/`customer_profiles`) no podían controlar nada
DENTRO de una página ni agregar un ítem nuevo sin una migración. Reemplazados por un árbol real:

- Tablas nuevas `permission_resources` (menú → submenú/sección, con `default_visible`) y
  `profile_permissions` (override por perfil o por cliente puntual). Resolución: COALESCE(override
  del cliente, override del perfil, default de la plataforma) — mismo criterio de precedencia que
  ya usaban `require_module()`/`require_reseller_module()`.
- Dos huecos reales sin ningún flag hasta ahora: el resumen de KPIs/últimas-llamadas de
  `/my/overview` y "Mis carriers" — ambos siempre visibles, sin excepción, sin forma de que el
  admin los apagara. Ahora son `overview_kpis`/`overview_last_calls`/`carriers`, controlables
  igual que el resto.
  Nuevo `backend/auth.py::require_permission()`/`require_reseller_permission()` reemplaza a
  `require_module()`/`require_reseller_module()` en los ~60 endpoints que los usaban.
- `/profiles` reescrito como editor de árbol real (antes checkboxes planos). Ficha de cliente
  (`/customers/{id}`) tiene el mismo editor para cuando no se usa un perfil.
- Migración de los 10 flags viejos a la tabla nueva antes de `DROP COLUMN` — sin perder nada ya
  configurado (`deploy.sh`, ambos bloques `--update`/`--upgrade`).

### Recalcular tarifas (admin y reseller) + reconciliación balance↔facturas

Caso real: un cliente negocia un precio nuevo a mitad de mes que debe aplicar retroactivamente
desde el inicio del ciclo, o un carrier cambia su tarifa de compra y hay que corregir el margen de
llamadas ya facturadas.

- Motor nuevo (`backend/routers/billing_recalc.py`) que reutiliza `main.py::_calc_bill()` (la
  misma fórmula del billing worker en vivo, no una reimplementación) — scope por cliente o por
  carrier, rango de fechas o mes, vista previa OBLIGATORIA antes de aplicar, bloqueo duro si el
  rango pisa una factura ya `sent`/`paid`. Espejo completo para reseller, acotado a sus propios
  sub-clientes/carriers.
- Marcar una factura como pagada ahora sí acredita el balance del cliente — antes eran dos
  sistemas totalmente desconectados, el balance solo acumulaba consumo desde el día 1 sin
  descontar nunca lo ya cobrado. Script de backfill (`scripts/backfill_invoice_balance_credit.py`,
  dry-run por default) para reconciliar retroactivamente facturas ya pagadas antes de este cambio.

### 10 puntos de revisión punto a punto del panel admin

- Dashboard: "clientes con llamadas activas" ya no repite el mismo cliente una fila por prefijo.
- Live: columna Carrier nueva (el dato ya estaba en `active_calls`, solo faltaba mostrarlo).
- Grupos de ruteo: badge de alerta cuando un grupo tiene 0 carriers pero sigue en uso por algún
  cliente (routing roto en silencio, antes solo se descubría al intentar borrar el grupo).
- Áreas: columna país real (`country_code`, FK a tabla `countries` con ~190 países, único por
  `(nombre, país)` no global) + selector país→área en cascada en Prefijos + reporte "Por destino"
  con toggle País/Área/Prefijo y el mismo selector día/mes que Reportes.
- Firewall separado en 3 páginas (reglas globales / IPs de clientes / Fail2ban, antes mezcladas en
  una sola pantalla) + soporte ICMP + panel de ver la config actual de fail2ban.
- Auditoría: filtro de 19+ pills planas reagrupado en acordeón por categoría (mismas categorías
  que el sidebar).
- "Reportes" renombrado a "Consumos".
- Nueva página Sistema → Logs — últimas N líneas de cualquier servicio (backend/frontend/
  Kamailio/fail2ban) o log de cron, sin entrar por SSH.

### Responsive / mobile

Bug sistemático real: ~40 páginas con tablas usaban `overflow-hidden` (corta el contenido) en vez
de `overflow-x-auto` (permite scroll horizontal) — corregido en toda la plataforma. El drawer
mobile del sidebar ya funcionaba bien, no era eso lo roto. Ficha de cliente (el caso puntual
reportado — "no puedo editar clientes desde el celular"): header, formularios de balance/reset de
password/crear usuario portal y tabla de prefijos ahora usables en pantallas angostas.

### Barrido de tokens de diseño (Tramo B) + `<LiveIndicator>` (Tramo C)

~500 usos de color crudo migrados a los tokens del sistema (`--color-success/warning/danger`, etc.)
en las 8 páginas con más deuda (`cdrs`, `system-health`, `traces`, `quality`, `invoices`, y sus
equivalentes de portal cliente). Componente `<LiveIndicator>` nuevo reemplaza 4 implementaciones
sueltas de "esto se actualiza solo" (dashboard, live, system/logs) por una sola, basada en tokens.

### Seguridad — auditoría real, no solo revisión de código

- SQLi verificado en vivo contra un MariaDB real (`x' OR '1'='1'` con y sin parámetros con bind) y
  contra la API real corriendo (payloads tipo `Robert'); DROP TABLE customers;--` como nombre de
  cliente — se guardan como texto literal, la tabla sigue intacta).
- XSS: 2 puntos reales sin escapar encontrados y corregidos — el nombre del cliente se embebía sin
  `html.escape()` en el HTML de la factura (`invoices.py`) y en la plantilla compartida de alertas
  (`mailer.py::alert_html()`, usada por `alerts.py`/`disconnect_policies.py` — el destino ahí es el
  correo interno del operador, no del cliente).
- CSP no llegaba a ninguna página del panel — vivía solo en el middleware de FastAPI (`/api/*`),
  pero el HTML real lo sirve Next.js vía nginx en otro puerto. Agregado a nginx (el que sí sirve el
  HTML) y sacado `unsafe-eval` en los dos lugares (confirmado sin uso real contra el bundle de
  producción).
- 3 CVEs "high" en dependencias (postcss/sharp, empaquetadas por Next.js) — `npm audit` a 0 con
  `overrides` en `package.json`, build reverificado limpio.
- Subida del logo de factura validaba solo la extensión del nombre — ahora valida la firma binaria
  real del archivo + límite de 2MB.
- IDOR verificado en vivo (reseller intentando leer un cliente que no es su sub-cliente → 404;
  cliente normal pegándole a un endpoint admin-only → 403) y bypass de auth (JWT sin firma válida,
  JWT falso con 5 secretos adivinados, sin token) — todo bloqueado como corresponde.
- `deploy.sh` ahora graba `LAST_DEPLOY_DATE` en el marcador del sistema en cada `--update`/
  `--upgrade` y lo muestra ("Última actualización: fecha y hora") la próxima vez que se corre —
  antes solo se veía la fecha de instalación original, nunca cuándo fue el último deploy real.

---

## v2.45.0 — 2026-07-23

### Menú "Reportes" consolidado

Investigación en vivo del portal de un carrier real (Digitalk/itelvox, credenciales propias del
usuario) — su sección "Reports" agrupa todo lo de consumo/calidad en un solo menú, filtrable por
zona/prefijo, con columnas Attempts/Answered/Minutes/Charges/ACD/ASR/PDD. Comparado con eso,
VoxiKam tenía Reportes bajo Facturación, Áreas bajo Tarifas y Calidad ASR bajo Tráfico —
consolidados en un grupo "Reportes" nuevo en el sidebar admin. Las páginas en sí no se movieron
de contenido, solo de grupo — ningún link se rompe.

### Consumo por área/destino — admin (global o por cliente) y cliente final

`GET /admin/areas/report` mostraba rentabilidad por área SOLO a nivel global de toda la
plataforma, sin desglose por cliente — y el cliente final no tenía ninguna vista de a qué
destinos estaba llamando ni cuánto le costaba cada uno (solo veía totales globales por día/mes).

- `cdr_summary_day_area` rediseñada con grano (día, **cliente**, prefijo) — antes solo (día,
  prefijo). La clave sigue siendo el prefijo crudo, nunca el nombre de área ya resuelto (un
  rename de área se refleja al instante sin recalcular nada, mismo criterio ya documentado).
- `area_report()` gana un filtro opcional `customer_id` — sin el parámetro, comportamiento
  idéntico al de antes (global, todos los clientes).
- Nuevo `GET /my/report/by-area` (portal cliente) — mismo motor SQL que el admin
  (`_area_report_rows()`, compartido entre `areas.py` y `portal.py`, mismo criterio que
  `_get_balance`/`_get_calls` ya compartidos entre `portal.py`/`api_v1.py`), forzado al propio
  `customer_id`. Aparece como sección "Por destino" en `/my/reports`, no como página nueva.
- **ASR/ACD/PDD nuevos**, pedidos explícitamente comparando contra el portal del carrier real.
  PDD (post-dial delay) no se trackeaba en ningún lado de la plataforma — se aproxima con
  `start_ts`→`answer_ts` (tiempo hasta 200 OK; no se trackea el 180 Ringing por separado, se
  documenta la limitación tal cual).

### Consumo por campaña propia del cliente — mismo patrón híbrido, pendiente desde antes

`GET /my/campaigns` (desglose por prefijo interno del cliente, ej. líneas de Vicidial) escaneaba
`cdrs` en vivo para todo el rango pedido — quedaba documentado explícitamente como "no se tocan
cdr_summary_day/month en esta primera vuelta" desde que se creó. Nueva tabla
`cdr_summary_day_campaign` (día, cliente, techprefix propio) + mismo patrón días-cerrados+hoy-en-
vivo que ya usa el resto de la plataforma.

---

## v2.44.0 — 2026-07-23

### Bloqueo de llamadas nuevas para clientes prepago con saldo agotado

Hasta ahora `customers.billing_type` (prepago/postpago) no cambiaba nada del comportamiento real de
las llamadas — un prepago con saldo en 0 podía seguir llamando exactamente igual que un postpago.
Pedido explícito: **no cortar una llamada ya en curso** (el saldo real recién se descuenta al colgar,
`backend/main.py::_billing_worker()`, con ~30s de lag propio — cortar en vivo exigiría re-chequear
saldo cada pocos segundos, fuera de alcance), pero sí evitar que se **originen llamadas nuevas** una
vez que el saldo ya está en 0 o negativo.

- Mismo mecanismo `htable` de Kamailio (`dbmode=1`, respaldado en MySQL, `kamcmd htable.reload` en
  caliente) ya validado esta sesión para Grupos de ruteo — acá como lista de bloqueo separada
  (`balance_block` / tabla `balance_block_map`), no un mapeo: solo contiene los techprefix (principal
  y de campaña) actualmente bloqueados, ausencia = permitido. Kamailio nunca decide "es prepago" —
  solo hace un lookup tonto y responde `402 Payment Required` si está. Toda la lógica de negocio vive
  en `scripts/sync_balance_block.py` (cron nuevo, cada 1 min).
- Validado contra Kamailio 5.6 real en Docker (build desde el repo oficial de Kamailio, no una imagen
  prearmada): confirmado auto-load del htable al arrancar, hot-reload real sin reiniciar el proceso
  (mismo defecto que ya se había encontrado y arreglado para `techmap`), y una llamada real de prueba
  a un techprefix bloqueado devolviendo `402` limpio e inmediato — mientras que un techprefix no
  bloqueado pasa de largo sin ninguna interferencia.
- Cron habilitado por defecto (cada 1 min) — un `--upgrade` normal deja esto funcionando solo, sin
  pasos manuales. `deploy.sh` corre `sync_balance_block.py --apply` una vez durante el propio deploy
  (además del cron) para que el bloqueo quede aplicado de inmediato y el detalle de a quién afectó
  quede visible en el log del deploy, no recién al primer tick del cron.
- Aviso visual nuevo en la ficha del cliente (admin y reseller) y en el resumen del portal cliente
  cuando un prepago se queda sin saldo — no queda solo un número en rojo sin contexto.
- Fuera de alcance a propósito: cortar una llamada ya en curso, y que postpago respete `credit_limit`
  (columna que ya existe en el schema pero no se usa en ningún lado hoy).

### Áreas: mismo patrón híbrido aplicado al reporte de rentabilidad

`GET /admin/areas/report` (`areas.py::area_report()`) escaneaba en vivo contra `cdrs` todo el rango
de fechas pedido — podían ser meses. Nueva tabla `cdr_summary_day_area`, agregada cada noche por
`cron_summary.py`, con una decisión de diseño distinta a `cdr_summary_day`: la clave es
`prefix_matched` (el prefijo crudo), NUNCA el nombre de área ya resuelto — el nombre se resuelve con
un JOIN a `prefixes` recién al leer, así que renombrar un área (`update_area()`, que ya cascadea a
`prefixes.group_name`) se refleja al instante en todo el histórico cacheado, sin recalcular nada.
Días completados desde la tabla de resumen, solo hoy en vivo acotado a su partición diaria — mismo
patrón que ya tenían portal/reseller/reports esta sesión.

### Selector de mes/año homogenizado entre Reportes admin y portal cliente

Reportes admin usaba un `<input type="month">` nativo del navegador (cada browser lo renderiza
distinto, sin estilo propio de la app) mientras el portal cliente ya usaba dos `<select>` con nombre
de mes + año. Unificado al estilo del portal — y de paso, mismo criterio que el fix reciente de
`/my/reports`: nuevo `GET /admin/reports/range` acota los años ofrecidos al rango real de datos de
toda la plataforma (`cdr_summary_month`), no años fijos sin verificar si hay algo ahí.

### Cron del bloqueo de saldo, habilitado por defecto

Se revirtió la decisión de dejarlo deshabilitado hasta un paso manual (ver más arriba) — un
`--upgrade` normal ahora deja el cron corriendo solo, cada 1 min, sin intervención. `deploy.sh` corre
`sync_balance_block.py --apply` una vez durante el propio deploy para que el bloqueo quede aplicado
de inmediato (no recién al primer tick del cron) y el detalle de a quién afectó quede visible en el
log del deploy.

### Fixes de UI encontrados en esta misma pasada

- **`apiGet`/`apiDelete` no leían el mensaje de error del backend** (`frontend/lib/api.ts`) — a
  diferencia de `apiPost`/`apiPut`, un 409 mostraba solo `"DELETE ... → 409"` genérico en vez del
  `detail` real. Un admin intentando borrar un Grupo de ruteo en uso solo veía "409", sin saber por
  qué ni qué cliente lo estaba usando. Corregido para los cuatro verbos, y de paso el 409 de borrar un
  grupo ahora lista explícitamente qué cliente(s) lo usan y cuántos prefijos cada uno (antes: "en uso
  por al menos un prefijo", sin decir cuál).
- **`customers.is_reseller` pintaba un "0" suelto en la ficha del cliente** — llega de MySQL como
  `0`/`1` (TINYINT), no como boolean real; `{customer.is_reseller && (<div>...)}` en JSX solo se salta
  el render con `false`/`null`/`undefined`, no con `0` — React sí pinta un `0` numérico como texto.
  Corregido convirtiéndolo a boolean apenas llega del API.
- **Live → "Activas por cliente"**: un cliente con varios prefijos de campaña activos aparecía como
  varias filas idénticas con su nombre repetido, como si fueran clientes distintos. Ahora se agrupan
  en una sola fila por cliente real, expandible para ver el desglose por prefijo/campaña — mismo
  patrón ya usado en Reportes admin. El KPI "Clientes activos" tenía el mismo conteo por-prefijo,
  corregido igual.
- **Ficha de cliente → Perfil de módulos**: mostraba qué módulos incluye el perfil asignado (pastillas
  verdes/tachadas) duplicando lo que ya gestiona la página Perfiles — reemplazado por un link directo,
  la composición del perfil se edita en un solo lugar.
- **Perfiles**: página angosta (`max-w-4xl`, único ancho límite de todo el panel) con una sola tarjeta
  amontonando hasta 10 pastillas de módulos. Ahora grilla responsive con módulos de cliente/reseller
  en filas separadas y etiquetadas.

---

## v2.43.1 — 2026-07-23

### Fix: reporte mensual del portal cliente escaneaba todo el mes en vivo

`GET /my/reports` (`backend/routers/portal.py::my_report()`) agregaba el mes completo en vivo
contra `cdrs` en cada carga de la página — hasta ~11s medidos en producción con un cliente de
alto volumen (un cliente, 2.8M llamadas/mes). El mismo problema ya se había resuelto para los reportes
admin (`backend/routers/reports.py::report_month()`) con un patrón híbrido: días completados desde
`cdr_summary_day` (agregado nocturno vía `cron_summary.py`, ya existente y corriendo), solo el día
de hoy se calcula en vivo y acotado a su propia partición diaria — nunca se había portado al
endpoint del portal cliente. Sin cambios de schema ni de cron: la tabla de resumen ya existía y ya
se actualizaba, solo faltaba que este endpoint la usara.

### Fix: estado de backfill de "Áreas" escaneaba todo el histórico de CDRs en cada carga

`GET /admin/areas/backfill-status` (banner de "N CDRs sin área asignada" en `/areas`) contaba en
vivo contra `cdrs` sin ningún filtro de fecha — a diferencia del reporte de arriba, este cálculo
necesita ver TODO el histórico (no hay "días completados" que resumir), así que sobre una tabla
particionada por mes con 4.25M+ filas era un scan completo de la tabla en cada carga de la página.
Nuevo cron horario (`scripts/cron_areas_backfill_status.py`) cachea el resultado en `settings`; el
endpoint ahora lee de ahí y expone `computed_at`/`stale` — si el cache todavía no existe (deploy
recién hecho) el panel lo dice explícito en vez de mostrar un 0/0 que podría esconder que sí hace
falta backfill.

### Fix: dashboard de margen del reseller escaneaba el mes en vivo (mismo patrón, un caso más difícil)

`GET /reseller/dashboard` (`backend/routers/reseller.py::dashboard()`) tenía el mismo problema que
el reporte del portal cliente: agregaba el mes completo en vivo contra `cdrs`, cada vez más pesado
según avanza el mes. No se pudo resolver reusando `cdr_summary_day` tal cual: `reseller_cost` (el
costo con el que se calcula el margen del reseller) solo existe para llamadas `ANSWERED` con
`billsec > 0` de un sub-cliente con reseller (`cdrs.py::ingest_cdr`) — un subconjunto más chico que
las filas que ya suma `cdr_summary_day.sessionbill` (toda llamada salvo `RESTART_ORPHANED`).
Agregar `reseller_cost` como columna extra ahí habría inflado el margen con llamadas fallidas que
tienen `sessionbill` pero nunca tuvieron `reseller_cost`. Se agregó una tabla de resumen separada,
`cdr_summary_day_reseller`, poblada por el mismo cron nocturno con el filtro exacto que usaba la
consulta en vivo — el dashboard ahora es días completados desde ahí + hoy en vivo, acotado a su
propia partición diaria.

### Fix: selector de mes/año del portal cliente ofrecía años sin ningún dato (ej. 2024)

`/my/reports` dejaba elegir cualquier mes de los últimos 3 años calendario a cualquier cliente,
sin importar cuándo se dio de alta — un cliente nuevo veía 2024 completo en el selector aunque no
tuviera un solo CDR ahí. Nuevo endpoint `GET /my/report/range` (lee `MIN(summary_month)` de
`cdr_summary_month`, tabla chica indexada por cliente, sin repetir el escaneo de `cdrs` que se
acaba de arreglar arriba) acota el selector al rango real de datos del cliente.

---

## v2.43.0 — 2026-07-23

### Grupos de ruteo (reemplaza el pin único de carrier) — arquitectura "solo grupos"

Pedido del cliente, inspirado en el modelo de MagnusBilling: un **Grupo de ruteo** tiene nombre +
algoritmo (`priority` / `round_robin` / `percent`) + carriers miembros, y cada prefijo de un
cliente (el techprefix principal, y cada prefijo de campaña por separado) elige a qué grupo
rutea — reemplaza tanto el pin único viejo (`active_carrier_id`/`carrier_failover_enabled`,
elegido por el cliente vía portal) como la tabla `customer_carriers` (lista simple de carriers
asignados). Ahora **todo cliente tiene un único mecanismo**: un grupo de ruteo, creado
automáticamente ("Principal") la primera vez que se le asigna un carrier — mismo gesto simple
de siempre, sin ceremonia nueva para el caso común.

- Tablas nuevas `carrier_groups`, `carrier_group_members`, `customer_carrier_groups` (visibilidad
  anonimizada para el portal del cliente, `display_label` tipo "Grupo 1"). `customer_carriers`
  se elimina por completo — migrada a un grupo "Principal" por cliente (`scripts/
  migrate_carrier_groups.py`, consolida el pool de carriers + el pin viejo con su lógica de
  failover en un solo backfill idempotente).
- Nuevos endpoints `/api/admin/carrier-groups` (CRUD admin) y espejo completo en
  `/api/reseller/carrier-groups` (grupos propios del reseller). `POST /{cid}/carriers` (el gesto
  de siempre) ahora crea/reutiliza el grupo del cliente por detrás — sin cambios visibles para
  quien solo asigna un carrier.
- Numeración de techprefix unificada por tipo de entidad (antes dispersa): 1001+ cliente admin,
  2001+ reseller creado como tal desde el inicio, 5000+ sub-cliente de reseller (sin cambios),
  7000+ prefijos de campaña de cualquier tipo de cliente — refactorizado a `backend/
  techprefix.py` compartido (antes duplicado entre `customers.py`/`reseller.py`).
- Simulador de ruteo (`routing_sim.py`) y el resto de los endpoints que dependían del pin viejo
  actualizados al nuevo modelo.

### Fix crítico: recarga en caliente real del ruteo por techprefix

**Encontrado en producción real (vd1sbc2)**: un cliente con un grupo `percent` (50/50 entre dos
carriers) seguía enrutando el 100% de sus llamadas al carrier de siempre. Causa raíz: el mapeo
techprefix→grupo vivía en `voxikam-routes.cfg`, incluido en `kamailio.cfg` vía `#!include_file`
— esa directiva se compila UNA sola vez al arrancar Kamailio, así que `kamcmd
dispatcher.reload` (que sí recarga los destinos) nunca aplicaba cambios de ASIGNACIÓN de grupo,
solo un restart manual del proceso lo hacía. Validado el diagnóstico y la corrección contra
Kamailio 5.6.3 real en Docker antes de tocar la config de producción.

- Reemplazado por un `htable` de Kamailio (`techmap`) respaldado en MySQL (tabla nueva
  `techprefix_map`, esquema fijo que exige el módulo `htable` para auto-cargar/recargar desde
  DB) — `kamcmd htable.reload techmap` sí aplica altas/bajas/cambios en caliente, confirmado con
  pruebas reales (no solo documentación, que en un punto anterior de esta plataforma ya había
  resultado no coincidir con el comportamiento real de Kamailio).
- `scripts/gen_dispatcher.py` reescrito: ya no genera `voxikam-routes.cfg` (archivo eliminado),
  escribe `techprefix_map` y dispara `htable.reload` además del `dispatcher.reload` de siempre.
  De paso, el número de grupo de dispatcher pasa a ser directamente `carrier_groups.id` (con
  offset fijo) en vez de aritmética por `customer_id` — un grupo compartido por varios clientes
  ahora se emite una sola vez en `dispatcher.list`, no una copia por cliente.
- **Requiere un restart de Kamailio, una única vez**, al aplicar este release — `deploy.sh` ya
  avisa esto al final de cada `--update`/`--upgrade`. Después de ese restart, altas/bajas de
  clientes/prefijos/grupos vuelven a aplicar solas.

### Página nueva: Entrante (LAN Peers)

El tráfico ENTRANTE (carrier → Asterisk/marcador, Grupo 1 del dispatcher) dependía de un campo
de texto suelto (`settings.lan_peers`) sin ningún endpoint ni pantalla — el propio código ya
daba por hecha una página "Settings > LAN Peers" que nunca se construyó. Ahora es una tabla
real (`lan_peers`) con CRUD completo en `/entrante` (alta/baja de host:puerto + descripción,
mismo patrón que "IPs autorizadas" de un cliente). Migración automática desde el campo viejo si
alguien lo había cargado a mano.

### Reorganización del panel

Auditoría completa de las 43 páginas del panel (comparado contra la organización de menús de
MagnusBilling/Yeti/ASTPP, investigada en sus repos públicos) — el sidebar admin pasa de 7 a 6
grupos, reordenados con una lógica narrativa (a quién sirvo → con qué equipo → qué política
aplico → qué pasó → cuánto cobro → cómo administro): **Clientes → Red → Ruteo → Tráfico →
Facturación → Sistema**. Tarifas/Pricelists/Áreas/Disconnect Policies se mudan a "Ruteo";
Alertas de balance a "Facturación"; Webhooks a "Sistema" — ningún backend cambia, solo dónde
vive cada página en el menú.

La ficha de un Cliente (8 bloques apilados, scroll larguísimo) y la de un Sub-cliente de
reseller (misma densidad pero sin jerarquía visual) se reorganizan en 2 tabs — **General** y
**Red y Ruteo** — reusando el mismo patrón de tabs que ya usaban `/cdrs` y `/traces`, sin tocar
lógica de negocio. La página de detalle de un Grupo de ruteo ahora muestra "Usado por" (qué
clientes/prefijos dependen de él) para no borrar/vaciar un grupo sin saber que corta a otro
cliente.

---

## v2.42.0 — 2026-07-16

### Prefijos de campaña por cliente (multi-techprefix, ej. Vicidial)

Pedido del cliente: clientes que operan un marcador (Vicidial u otro) quieren que cada
campaña salga con su propio prefijo técnico bajo la MISMA cuenta — ej. cliente "Master1":
`1001`="Campaña A", `1002`="Campaña B" — para ver en su panel consumo global y también
desglosado por campaña. Antes cada cliente tenía exactamente un `techprefix`.

- Nueva tabla `customer_prefixes` (customer_id, techprefix, label) — contiene SOLO los
  prefijos ADICIONALES de campaña; `customers.techprefix` sigue siendo el principal, sin
  cambios ni migración de datos. CRUD simple (alta/baja, sin edición, igual criterio que
  `customer_ips`) en `/admin/customers/{id}/prefixes` y
  `/reseller/sub-customers/{id}/techprefixes`. El techprefix SIEMPRE se autogenera (4
  dígitos, arranca en 2000) — nunca es texto libre, mismo criterio que ya usaba
  `reseller.py::_next_techprefix()` para evitar que un humano elija sin saberlo un valor que
  colisione por substring.
- La validación de colisión por substring (Kamailio matchea por `substr`, no por igualdad
  exacta) se extendió para chequear contra ambas tablas y también contra los OTROS
  prefijos de campaña del mismo cliente — dos prefijos propios que colisionen entre sí
  atribuirían mal la campaña aunque el billing (mismo customer_id) no se vería afectado.
- `scripts/gen_dispatcher.py` ahora itera TODOS los prefijos de cada cliente (antes tomaba
  uno solo) y graba `$dlg_var(techprefix)` en el bloque de ruteo generado;
  `templates/kamailio.cfg.j2` lo persiste en el nuevo `cdrs.techprefix` (nullable) al
  cerrar la llamada — mismo patrón `NULLIF(...)` que ya existía para `carrier_id`. Usa
  exactamente el mismo mecanismo que ya dispara la creación de un cliente normal
  (`gen_dispatcher.py` + `kamcmd dispatcher.reload`) — no se agregó nada nuevo. Punto abierto
  sin resolver del todo: por documentación de Kamailio esto requeriría restart del proceso
  para tomar efecto (el `#!include_file` se compila al arrancar, no se recarga en caliente),
  pero en la operación real el usuario confirma que un cliente nuevo ya rutea sin reiniciar
  nada a mano — no se hizo la prueba controlada para confirmar cuál es la realidad. Ver
  CLAUDE.md para el detalle completo.
- **Limitación honesta, sin backfill posible**: el techprefix de una llamada se descarta en
  Kamailio antes de esta versión — a diferencia de `prefix_matched`/Áreas (recalculable con
  la config actual), el dato de campaña de un CDR viejo nunca se guardó en ningún lado.
  Todo CDR anterior a este cambio queda como "Sin campaña" para siempre.
- Nuevo `GET /my/campaigns` (portal cliente): desglose de consumo por campaña, acotado a
  un rango de fechas (default 30 días), consultando `cdrs` en vivo — no se tocó
  `cdr_summary_day/month` en esta primera vuelta. `GET /my/trunk-guide` ahora lista TODOS
  los prefijos del cliente con su propio fragmento de dialplan — sin esto el cliente nunca
  se enteraba de que podía configurar campañas separadas.
- Bug independiente encontrado y corregido en el camino: `scripts/cron_dlg_stats.py`
  extraía el prefijo del snapshot en vivo con un largo FIJO de 4 caracteres
  (`substr(destino_completo, 1, 4)`), pero el autogenerador de sub-clientes de reseller
  arranca en `10000` (5 dígitos) — el widget "Activas por cliente" y la resolución de
  cliente en `cron_timeseries.py` ya estaban rotos en silencio para cualquier cliente de
  5+ dígitos. Corregido con un longest-prefix-match real contra la lista de prefijos
  conocidos (mismo criterio que el billing por tarifa), necesario además para que los
  nuevos prefijos de campaña (largo variable) se resuelvan bien.
- `backend/routers/routing_sim.py` (simulador de ruteo admin) probaba solo contra el
  prefijo principal — un destino marcado con un prefijo de campaña daba un resultado
  engañoso (parecía fallar cuando en realidad rutearía bien). Corregido para probar contra
  todos los prefijos del cliente.

## v2.41.1 — 2026-07-14

### Bug real de facturación: initblock/billingblock=60 cobraba el minuto completo en llamadas cortas

Reportado por el cliente vía "el precio no cuadra" en Reportes — confirmado con CDRs reales: una
llamada de 2 segundos y una de 26 segundos cobraban exactamente lo mismo (S/0.03, el minuto
completo), en vez de facturar proporcional al segundo real. La tarifa configurada (S/./min)
nunca cambió — lo que estaba mal era el **bloque de facturación** (`initblock`/`billingblock`),
en 60/60 (redondea toda llamada hacia arriba al minuto) por default de fábrica desde siempre, en
vez de 1/1 (por segundo real). Afectaba a los 3 planes de venta y a los 3 carriers de compra por
igual — no era un caso puntual de un cliente.

- Default cambiado de 60→1 en `RateIn`/`GroupRateIn` (`rates.py`, `carriers.py`, `reseller.py`,
  `pricelists.py`) y a nivel de columna en `db/schema.sql` + `ALTER TABLE ... MODIFY COLUMN`
  en `deploy.sh` (fresh, upgrade y update).
- Bug aparte encontrado de paso: ni el alta individual ni "por grupo" de tarifas podían corregir
  `initblock`/`billingblock` de una fila ya existente — el `ON DUPLICATE KEY UPDATE` no los
  tocaba (y "por grupo" ni siquiera aceptaba `initblock` en el body, lo hardcodeaba a 60 en el
  INSERT). Corregido en los 3 routers.
- `customers.rate_plan_id` pasó a obligatorio al crear cliente/sub-cliente (`CustomerIn`,
  `SubCustomerIn`) — un cliente sin plan nunca generaba `sessionbill`, en silencio, sin ningún
  aviso (encontrado un caso real así en producción). El formulario "Nuevo cliente" del admin ni
  siquiera tenía el campo — se agregó, con aviso si todavía no hay ningún plan creado.
- Nuevo `scripts/recalc_billing_blocks.py` (`--apply`, dry-run por default): recalcula
  `sessionbill`/`buycost`/`reseller_cost` de CDRs ya facturados mal contra las tarifas ya
  corregidas, ajusta el balance del cliente por la diferencia real (con su propio
  `balance_transactions`, auditable) y refresca `cdr_summary_day`/`month` del rango. Las tarifas
  en memoria (no una query por CDR) — con ~2M CDRs, la primera versión con queries individuales
  hubiera tardado horas.
- Auditoría posterior encontró el mismo default `60` sobreviviendo en un solo lugar que no pasa
  por los modelos Pydantic ya corregidos: la importación masiva de tarifas por CSV
  (`pricelists.py::import_csv`) usaba `int(row_data.get("billingblock") or 60)` — un CSV sin esa
  columna (o con la celda vacía) importaba tarifas en bloques de 60s en silencio. Corregido a 1.
- Aplicado en producción sobre el rango 2026-07-01 a 2026-07-14: un cliente y otro cliente recibieron
  crédito de balance por el cobro de más real (~S/22,865 y ~S/5,743 respectivamente).

### Calidad de llamada: se agregó jitter/pérdida promedio (antes solo mostraba el peor pico)

El badge "Calidad" del detalle de CDR mostraba `max_jitter_ms`/`max_packet_loss_pct` — el peor
valor puntual entre todos los reportes RTCP de la llamada. Comparado contra el portal del
carrier (Digitalk) para la misma llamada exacta, esa métrica de "peor caso" mostraba "Regular"
(58ms) mientras Digitalk reportaba 78µs de jitter promedio — la llamada estaba bien, el
indicador era engañoso por diseño (un solo pico aislado castiga toda la llamada).

- `call_media_stats` ganó `sum_jitter_ms`/`sum_packet_loss_pct` (acumulado por `hep_listener.py`
  en cada reporte RTCP) para poder calcular el promedio real (`sum/report_count`) sin tocar el
  peor-caso existente, que se conserva como dato secundario.
- `backend/routers/cdrs.py` expone `avg_jitter_ms`/`avg_packet_loss_pct` calculados con
  `SUM/NULLIF(report_count,0)`; el panel de CDRs ahora muestra el promedio como valor principal
  del badge de calidad y el peor pico atenuado debajo, mismo criterio que usa el portal del
  carrier.
- Limitación conocida y aceptada: las llamadas ya registradas antes de este cambio no tienen
  `sum_jitter_ms` acumulado retroactivamente — el promedio solo aplica hacia adelante.

### Carrier sin tarifas podía asignarse y rutear tráfico real — facturaba costo $0 en silencio

Mismo patrón que el bug de `rate_plan_id` de arriba, pero del lado de compra: un carrier sin
ninguna fila en `carrier_rates` se podía asignar a un cliente y `gen_dispatcher.py` lo enrutaba
igual (nunca validó tarifas, solo `status='active'`). Cuando no hay match contra `carrier_rates`,
`_calc_bill()` deja `buycost=0` sin ningún aviso — y como el reporte no oculta esas llamadas, se
veían con costo $0 y **margen del 100%**, más engañoso todavía que si no aparecieran. Encontrado
en producción: un carrier se asignó y usó para tráfico real sin que nadie notara que no tenía
tarifas cargadas, hasta revisar el reporte y ver "consumo" sin ningún costo registrado.

- Nueva validación en `assign_carrier()` (`customers.py`) y `assign_carrier_to_sub_customer()`
  (`reseller.py`): rechaza la asignación (400) si el carrier no tiene ninguna fila en
  `carrier_rates`.
- `list_carriers()` (admin y reseller) ahora expone `rate_count`; el panel de Carriers marca con
  un badge rojo "⚠ sin tarifas" a los que tienen cero, y el link "Tarifas →" cambia a
  "Ajustar tarifas →" en rojo para esos casos. Los selectores de asignar-carrier (cliente y
  sub-cliente) también marcan la opción con "⚠ sin tarifas" antes de que el admin/reseller
  llegue a intentar asignarlo.

### Dashboard en vivo: el gráfico "Por carrier" siempre mostraba "Sin nombre"

`scripts/cron_timeseries.py` grababa `carrier_id=0` hardcodeado en cada snapshot — nunca
resolvía el carrier real de cada llamada activa. Kamailio sí lo sabe (`$dlg_var(carrier_id)`),
pero el RPC liviano que usa el snapshot cada 10s (`kamcmd dlg.briefing`) solo trae campos fijos
(from/to/callid/estado/tiempos), no variables custom — y el RPC que sí las trae (`dlg.list`) ya
había reventado en producción con "reply too big" al dumpear todos los diálogos (v2.24.15). En
vez de tocar el routing SIP en vivo, se resuelve cruzando `sip_traces` (ClickHouse): cada
paquete SIP capturado por HEP ya trae el `dst_ip` real — para el INVITE saliente al carrier,
`dst_ip` es la IP pública del carrier (`carriers.host`). El script ahora cruza
call_id (de dlg.briefing) → dst_ip (ClickHouse) → carrier_id (MariaDB) con una sola query
batched, sin ninguna llamada nueva a Kamailio. Además ahora agrupa por (cliente, carrier) en
vez de solo por cliente — `calls_timeseries` ya tenía la clave única `(ts, customer_id,
carrier_id)` preparada para esto, solo nunca se había usado.

### Auditoría de valores hardcodeados que podían "mentir" — un hallazgo más real

A pedido explícito del usuario, tras encontrar dos veces el mismo patrón (arriba) se auditó
todo `backend/` y `scripts/` buscando otros valores fijos que reemplacen silenciosamente un
dato real. Un hallazgo con impacto real: `scripts/cron_external_sync.py::sync_batches()`
envolvía el INSERT por fila en un `except Exception: pass` genérico — pensado para tolerar
"fila ya existía" en un reintento tras un corte a mitad de batch, pero en la práctica tragaba
CUALQUIER error (timeout, columna incompatible, etc.) sin loggear nada, y `rows_synced` contaba
filas LEÍDAS de `cdrs`, no filas realmente insertadas en el destino — `external_sync_log`
quedaba en `status='ok'` aunque se hubieran perdido filas. Corregido: solo se tolera en
silencio un error que mencione "duplicate"/"unique"/"primary key"; cualquier otro fallo se
cuenta (`rows_failed`, columna nueva) y deja el estado en `'partial'` con el detalle del error,
en vez de reportar éxito falso.

## v2.41.0 — 2026-07-12

### sip_traces migrada de MariaDB a ClickHouse

`sip_traces` (captura HEP de cada paquete SIP, usada por el ladder diagram y el export
`.pcap` del panel `/traces`) crecía ~8.5 GB/día medido en producción — con los 90 días de
retención configurados desde Traffic Sampling (`settings.sip_traces_retention_hours`), eso
implicaba ~765 GB solo para esta tabla, muy por encima del disco disponible del server.
Bajar la retención o agrandar el disco quedaron descartados explícitamente — se optó por
mover la tabla a ClickHouse (self-hosted, open source), que resuelve el problema de raíz
(compresión columnar + TTL nativo) sin tocar la política de retención de 90 días.

- Nuevo `db/clickhouse_schema.sql`: `sip_traces` en `MergeTree`, particionada por día
  (`toDate(captured_at)`), ordenada por `(call_id, captured_at, id)` para que el lookup
  exacto por Call-ID (el path más caliente: ladder diagram y export pcap) siga siendo
  rápido, con `TTL captured_at + INTERVAL 2160 HOUR` sincronizado en vivo desde el panel.
- `backend/hep_listener.py`: el sink de trazas SIP pasa de `aiomysql` a
  `clickhouse-connect` — mismo batching de 200ms, mismo backpressure. El RTCP/calidad de
  medio (`call_media_stats`) sigue 100% en MariaDB, sin cambios. Se eliminó el DELETE
  horario de retención (código muerto ahora — el TTL de ClickHouse lo reemplaza).
- `backend/routers/traces.py`: los 4 endpoints (`/calls`, `/stream`, ladder, `/pcap`) ahora
  consultan ClickHouse — mismo JSON de respuesta, sin cambios en el frontend. El
  `GROUP_CONCAT(...ORDER BY...)` de `/calls` se resolvió con `arraySort`/`groupArray` de
  ClickHouse, ya que el orden no sobrevive un `GROUP BY` agregado en paralelo.
- `backend/routers/traffic_sampling.py`: cambiar la retención desde el panel ahora también
  empuja un `ALTER TABLE ... MODIFY TTL` a ClickHouse — la UX del panel no cambia.
- Nuevo `scripts/migrate_sip_traces_to_clickhouse.py` (`--cutover`/`--truncate`, dos fases
  separadas a propósito: la primera reversible, la segunda no) y
  `scripts/setup/05_install_clickhouse.sh` (instalador idempotente, mismo patrón que el
  stack SIP). `deploy.sh` gana una sección `[clickhouse]` en `credentials.conf` y aprovisiona
  usuario/DB/schema en fresh/upgrade — decisión explícita del usuario: del histórico ya
  acumulado en MariaDB solo se migran las últimas 48h, el resto se descarta con `TRUNCATE`.
- `scripts/cron_partitions.py` perdió `maintain_sip_traces()` (dead code — el particionado
  por `DROP PARTITION` en MySQL ya no aplica a esta tabla).

## v2.40.2 — 2026-07-11

### Fix de permisos: un reseller veía y podía asignar CUALQUIER carrier de plataforma

Reportado con captura real de `/my/reseller/customers` (dropdown "Carriers asignados"
mostrando carriers de plataforma que el admin nunca le concedió a ese reseller). El diseño
original (`GET /reseller/carriers/assignable` y `POST /reseller/sub-customers/{cid}/carriers`
en `backend/routers/reseller.py`) trataba "de plataforma" como sinónimo de "cualquier carrier
con `owner_customer_id IS NULL`" — sin filtrar por si el admin realmente se lo había asignado a
ESE reseller vía `customer_carriers` (el mismo mecanismo que `customers.py::assign_carrier()`
ya usa para clientes normales, la fila del propio reseller en `customers` cuenta igual).

- Ambos endpoints ahora exigen `EXISTS (SELECT 1 FROM customer_carriers WHERE customer_id =
  <cid del reseller> AND carrier_id = c.id)` para cualquier carrier de plataforma — un reseller
  sin ningún carrier asignado por el admin ahora no ve ni puede asignar ninguno, hasta que el
  admin se lo conceda desde `/customers/{id}` (la misma sección de carriers que ya existía ahí,
  reusada sin cambios). Los carriers PROPIOS del reseller (`owner_customer_id = su_cid`) siguen
  disponibles sin restricción, como antes.

### Prefijo técnico de sub-cliente: 100% automático, 5 dígitos

El campo era editable a mano en creación y edición — un reseller no conoce el gotcha de
colisión por substring de Kamailio (`_techprefix_conflicts`, ver v2.36.0) y podía elegir un
prefijo corto por accidente. Ahora:

- `_next_techprefix()` arranca en `10000` (antes `1000`) — mantiene a los sub-clientes de
  reseller en su propio rango de 5 dígitos, lejos de los rangos cortos que el admin asigna a
  mano en `customers.py`.
- `create_sub_customer()`/`update_sub_customer()` ignoran cualquier `techprefix` que venga en
  el body — siempre autogenerado al crear, nunca editable después. `SubCustomerIn` ya no acepta
  el campo. `_assert_techprefix_free()` quedó sin caller — eliminada (dead code).
- Frontend (`/my/reseller/customers`): el input de creación se sacó del formulario (con nota
  explicando que se asigna solo); el de edición pasó a solo-lectura.

---

## v2.40.1 — 2026-07-11

### Fix: el panel de CDRs confundía duración total con tiempo hablado

El detalle de una llamada (`/cdrs`, panel admin) mostraba una sola fila "Duración" ligada a
`billsec` (segundos facturables, desde que contesta hasta que cuelga) — pero nunca mostraba
`sessiontime` (duración real de la llamada completa, desde el INVITE inicial, incluye timbrado
antes de contestar). Son dos cosas distintas y la UI las mezclaba bajo una sola etiqueta,
reportado por el usuario a partir de una captura real del panel.

- `backend/routers/cdrs.py::list_cdrs()`: el `SELECT` de `base_ok` y `base_fail` (UNION) no
  traía `sessiontime` de la tabla `cdrs` — se agregó (`0 AS sessiontime` en `base_fail`, ya que
  `cdrs_failed` no tiene columna de duración).
- `frontend/app/(admin)/cdrs/page.tsx`: tipo `CDR` ahora incluye `sessiontime`; el panel de
  detalle (`CdrDetailPanel`) separa "Duración total" (`sessiontime`) de "Tiempo hablado"
  (`billsec`), con una nota inline si hubo timbrado antes de contestar.
- La tabla compacta de resultados (columna "Tiempo") y el portal de cliente (`/my/calls`) se
  dejaron sin cambios a propósito — siguen mostrando solo `billsec`, que es lo relevante para un
  vistazo rápido o para lo que el cliente paga; el desglose completo vive en el detalle admin.

---

## v2.40.0 — 2026-07-09

### Auditoría dedicada de CVEs y tecnología obsoleta (todo el stack)

A pedido explícito del usuario ("usá agentes de ciberseguridad" para CVEs/tecnología obsoleta
específicamente) — auditoría separada de la ronda general de v2.38.0, esta vez cubriendo TODO
el stack (Python, npm, Y las versiones de sistema que instala `deploy.sh`: Kamailio, RTPEngine,
MariaDB, Node), con verificación real vía WebSearch contra NVD/GHSA/avisos de cada vendor —no
solo conocimiento de entrenamiento (con fecha de corte enero 2026, seis meses antes de hoy). Los
hallazgos más críticos se verificaron dos veces: primero el agente, después yo mismo con
WebSearch propio, dado que recomendaban saltos de versión mayor en infraestructura que maneja
tráfico real.

**CRÍTICO — `fastapi==0.115.5` permitía Starlette vulnerable a CVE-2026-48710 "BadHost"** (CVSS
crítico, bypass de auth vía Host header — un solo carácter inyectado en el header desalinea
`request.url.path` del path real que el servidor ASGI enrutó). Corregido: `fastapi>=0.120,<0.140`
+ `starlette>=1.0.1` — probado en un venv real (resuelve a fastapi 0.139.0 + starlette 1.3.1, los
38 routers del backend importan sin error).

**CRÍTICO — `next==15.1.0` vulnerable a CVE-2025-29927** (bypass de middleware/auth vía header
`x-middleware-subrequest` spoofeado) **+ CVE-2025-49826 + CVE-2026-23870** (13 avisos parcheados
en total). Corregido: `next` → `15.5.18`, `react`/`react-dom` → `19.0.6` — mismo major/minor que
ya se usaba (15.x, 19.0.x), sin saltar a Next 16 (evita el riesgo de un upgrade mayor a ciegas).
Versiones confirmadas reales contra el registro de npm antes de fijarlas.

**CRÍTICO — RTPEngine mr10.5.x vulnerable a CVE-2025-53399** (RTP Inject/Bleed, CVSS 9.3 —
inyección o redirección de streams RTP/SRTP sin necesitar MITM). **NO corregido** — la versión
parcheada (mr13.4.1.1+) dejó de publicar paquetes para Debian 12/bookworm (confirmado contra el
repo real de Sipwise). Requiere una decisión de arquitectura (migrar el SO base a Debian 13,
aplicar mitigaciones de config sin cambiar de versión, o buscar un backport) — documentado en
CLAUDE.md → Roadmap, no es un fix de un archivo.

**ALTO — Kamailio 5.7.x vulnerable a CVE-2026-39863** (DoS/crash vía TCP/TLS, CWE-119). Corregido
en `scripts/setup/04_install_sip_stack.sh`: repo `kamailio57` → `kamailio58` (confirmado
`5.8.8+bpo12` disponible para bookworm). Solo afecta instalaciones NUEVAS — el Kamailio ya
corriendo en producción no se actualiza solo, requiere acción manual en el servidor real.

**ALTO — `jinja2==3.1.4` vulnerable a CVE-2024-56326/CVE-2024-56201** (RCE vía bypass del
sandbox). Corregido: `jinja2>=3.1.5`.

**MEDIO — `aiosmtplib==3.0.2` vulnerable a CVE-2026-53533** (inyección de comandos SMTP vía CRLF
en sender/recipient). Corregido: `aiosmtplib>=5.1.1` — verificado que `mailer.py::send_email()`
ya usa solo argumentos con nombre y no usa `source_address` (los dos breaking changes reales de
la serie 5.x), compatible sin cambios de código.

**INFO — MariaDB 10.11.x (LTS de Debian 12)**: varios CVEs 2025-2026 encontrados, todos ya
parcheados dentro de la misma rama — riesgo real solo si el paquete no se actualiza vía
`apt upgrade` regular en el servidor. No requiere cambio de repo/versión, solo mantenimiento
normal del SO.

**Confirmado limpio**: `pymysql==1.1.1` (es justo la versión que corrige un CVE anterior),
`sqlalchemy==2.0.36`, `psycopg2-binary==2.9.9`, `uvicorn==0.32.1`, `httpx==0.27.2`, `bcrypt`,
`python-dotenv`, `python-dateutil`, `psutil`, `email-validator`, `lucide-react`, `clsx`,
`jose`(npm) — sin CVEs activos encontrados para las versiones exactas fijadas.

**Sin cambios, ya señalado antes**: `python-jose==3.3.0` (sin CVE nuevo, pero confirmado sin
mantenimiento activo desde 2021 — FastAPI mismo recomienda migrar a PyJWT quedaba fuera de
alcance de esta auditoría, no urgente).

## v2.39.1 — 2026-07-09

### Segunda ronda de validación (6 agentes) sobre el trabajo de v2.39.0

A pedido explícito del usuario ("usa los agentes que ya te indiqué") — se corrió la misma
auditoría de 6 agentes sobre el trabajo nuevo de v2.39.0. Encontraron 2 bugs reales:

**ALTO — `saveAuth()` en el login nunca persistía `show_api_access` ni los 4 campos
`show_reseller_*`**

`frontend/app/(auth)/login/page.tsx`: el objeto que se guarda en `localStorage` tras loguearse
solo copiaba `show_calls/quality/reports/invoices/trunk_guide` — nunca `show_api_access` (nuevo
en v2.39.0) ni `show_reseller_customers/rates/carriers/dashboard` (de v2.37.0, varias versiones
atrás). Efecto real: el filtro del `Sidebar.tsx` (`user?.[item.module] !== false`) trataba
`undefined !== false` como `true` — el link "API Keys" se mostraba a TODO cliente sin importar
el toggle del admin, y **los 4 módulos de reseller (Sub-clientes, Tarifas propias, Carriers
propios, Resumen) tampoco respetaban su toggle desde que existen** — llevaban 2 versiones
enteras sin efecto real en el frontend, aunque el backend sí bloqueaba correctamente
(`require_module`/`require_reseller_module`), así que el síntoma era un link visible que al
hacer click daba 403, no una fuga de datos. Corregido agregando los 5 campos faltantes.

**MEDIO — el barrido de manejo de errores de v2.39.0 se saltó varias páginas reales** — el
propio agente que auditó el barrido encontró que "barrido completo" era una afirmación
exagerada: `frontend/app/(admin)/customers/[id]/page.tsx` (4 fetches sin `.catch`, la misma
página usada para probar el toggle de API keys), `customers/page.tsx`, `profiles/page.tsx`,
`firewall/page.tsx`, y `frontend/app/(client)/my/calls/page.tsx` (usaba `apiFetch` crudo sin
chequear `r.ok`) quedaron sin corregir en la primera pasada. Cerrados ahora.

**BAJO — `areas.py::runBackfill()` nunca reseteaba `backfillRunning` a `false`** (bug preexistente,
no introducido en v2.39.0, encontrado de paso) — el botón "Recalcular histórico" quedaba
deshabilitado para siempre tras el primer click. Corregido con `finally`.

**Confirmado limpio en esta ronda**: generación de API keys (`secrets.token_hex(24)`, 192 bits),
superficie de seguridad del toggle de jail (`Depends(require_admin)` intacto, `bool` validado por
FastAPI), consistencia de `show_api_access` en los 3 modelos Pydantic tocados, sin fuga de
información en los mensajes de error nuevos (`apiGet`/`apiPost` solo exponen `detail` de
`HTTPException`, nunca tracebacks).

## v2.39.0 — 2026-07-09

### Cierre de los pendientes de la auditoría global (v2.38.0)

A pedido explícito del usuario ("arregla todo") — los 4 pendientes documentados en el Roadmap
tras la auditoría de 6 agentes, resueltos:

- **Módulo de API keys de cliente — UI completa nueva**: backend ya existía (`portal.py`) pero
  no había ninguna forma de usarlo. Nueva página `/my/api-keys` (crear, ver una sola vez, listar,
  revocar), agregada a `Sidebar.tsx` gateada por `show_api_access`, y el toggle correspondiente
  agregado donde faltaba — ni `CustomerIn` (`customers.py`) ni `ProfileIn` (`profiles.py`) ni el
  login (`auth.py`) tenían el campo, así que el admin no podía habilitarlo aunque hubiera
  intentado. Los 3 se corrigieron.
- **Toggle de fail2ban "jail" — ya no a medio construir**: el backend (`POST /{rid}/jail`) existía
  desde antes, el frontend solo mostraba el badge. Agregado el botón candado/candado-abierto en
  `/firewall` para banear/liberar una regla sin editar la DB a mano.
- **Manejo de error visible en ~40 páginas del panel**: barrido completo (admin + cliente) —
  cualquier página que hacía `apiGet(...).then(setX)` sin `.catch` ahora captura el error y lo
  muestra en un banner, en vez de dejar listas vacías o KPIs en "0" indistinguibles de datos
  reales. Encontrados y corregidos 2 casos reales de loading infinito (además de Trunk Guide de
  v2.37.1): `alerts/consumption` y `external-sync` — ambos con un `async function load()` sin
  try/catch cuyo fallo dejaba la página en "Cargando…" para siempre.
- **Confirmación de `/ingest` en logs de producción — pendiente, requiere acceso al servidor**:
  no se puede confirmar sin correr el comando documentado en CLAUDE.md → Roadmap
  (`journalctl -u voxikam-backend | grep "POST /api/admin/cdrs/ingest"` en `vd1sbc2`) — el
  endpoint ya queda protegido con `X-Ingest-Secret` desde v2.38.0 de cualquier forma, así que no
  hay riesgo de seguridad mientras tanto; solo falta decidir si se borra el código o se documenta
  como intencional.

## v2.38.0 — 2026-07-09

### Auditoría global de 6 agentes (ciberseguridad, backend, frontend, QA, lógica, funcional)

A pedido explícito del usuario — primera corrida de esta práctica sobre TODO el proyecto, no
solo un diff de sesión. Hallazgos reales y sus fixes:

**CRÍTICO — `POST /api/admin/cdrs/ingest` sin ninguna autenticación**

Encontrado independientemente por el agente de ciberseguridad y el de backend: el endpoint que
descuenta saldo real de un cliente (`UPDATE customers SET balance = balance - :bill`) no tenía
`Depends(require_admin)` ni ninguna otra protección, identificaba al cliente por un campo del
propio payload (`src_ip`) — cualquiera en Internet que supiera la IP registrada de un cliente
podía vaciarle el saldo con un POST fabricado, sin login.

Investigación propia adicional: `templates/kamailio.cfg.j2::event_route[dialog:end]` inserta el
CDR directo a MySQL vía `sql_query()` — no hay ningún `http_client`/`curl` en todo el template
que llame a este endpoint. El propio docstring de `backend/main.py::_billing_worker()` ("procesa
CDRs escritos por Kamailio, buycost=0") describe exactamente el resultado de esa inserción
directa. Conclusión: `ingest_cdr()` es muy probablemente un mecanismo de una arquitectura
anterior (Kamailio llamando por HTTP) nunca removido tras migrar a inserción directa + billing
worker asíncrono — pero no se borra sin confirmarlo en logs de producción reales.

- `backend/auth.py`: nueva `require_ingest_secret()` — header `X-Ingest-Secret` contra
  `CDR_INGEST_SECRET` (`.env`, nunca hardcodeado).
- `deploy.sh`/`scripts/gen_configs.py`/`templates/backend.env.j2`: `CDR_INGEST_SECRET` se genera
  con `openssl rand -hex 32` la primera vez y se preserva entre corridas leyendo el valor ya
  desplegado (mismo criterio que `JWT_SECRET`, pero sin tocar el pipeline completo de
  `credentials.conf` — un secreto nuevo, no crítico para el arranque de nada existente).
- `backend/routers/cdrs.py::ingest_cdr()`: de paso, corregido un segundo gap real encontrado por
  el agente de backend — nunca escribía en `balance_transactions` ni evaluaba alertas de saldo
  bajo (a diferencia de `_billing_worker()`, que sí hace ambas cosas). Si el endpoint resulta
  estar vivo en algún deploy, ahora es consistente con el otro camino.

**CRÍTICO — `initblock` configurado pero nunca usado en ningún cálculo de facturación**

Encontrado por el agente de lógica de negocio: `rates.initblock` ("seg. primer bloque") se
guarda desde el admin y el reseller desde hace varias versiones, pero ni `cdrs.py::ingest_cdr()`
ni `main.py::_calc_bill()` lo leían — un esquema configurado como "60/6" (primer minuto completo,
6 segundos después) facturaba en realidad todo a 6 segundos, silenciosamente. Nueva función
`_billable_blocks(segundos, initblock, billingblock)` (duplicada en ambos archivos, mismo
criterio que otros helpers pequeños de este proyecto) — única fuente de verdad para este
cálculo, usada en los 3 lookups de tarifa (buycost, sessionbill, reseller_cost) en ambos caminos.

**CRÍTICO — `main.py::_calc_bill()` (camino de respaldo) ignoraba `billingblock` por completo**

Divergencia real entre los dos caminos de facturación: `ingest_cdr()` redondeaba al bloque de
facturación, `_calc_bill()` facturaba sobre `billsec` crudo — un CDR con la misma duración se
facturaba distinto según cuál camino lo procesara. Corregido usando el mismo `_billable_blocks()`
en ambos.

**ALTO — filtro `rates.status='active'` solo en el camino de respaldo, no en el principal**

`_calc_bill()` sí filtraba tarifas inactivas, `ingest_cdr()` (el camino que procesa la inmensa
mayoría de las llamadas reales) no — desactivar una tarifa desde el panel no la sacaba de
circulación en producción. Agregado el mismo filtro a los 2 lookups de `ingest_cdr()`.

**ALTO — `python-multipart==0.0.12`, CVE-2024-53981 (DoS)**

Actualizado a `0.0.18` en `backend/requirements.txt`.

**MEDIO — `JWT_SECRET` con fallback inseguro (`"changeme"`)**

`backend/auth.py`: si el backend arrancara alguna vez sin `.env` cargado, caía silenciosamente a
un secreto público conocido — cualquier JWT firmado con "changeme" pasaba la verificación. Ahora
`os.environ["JWT_SECRET"]` sin default — falla el arranque en vez de aceptar tokens inseguros.

**ALTO — `sudoers/voxikam` no se sincronizaba en modo `--update`**

Encontrado por el agente funcional (mismo patrón que el bug del bit +x de `autotune.sh`
corregido antes en esta sesión): el `cp sudoers/voxikam /etc/sudoers.d/voxikam` solo vivía en la
sección exclusiva de `fresh`/`upgrade`/`reinstall`. Si se agregaba un servicio nuevo a la
allowlist y el deploy diario es `--update` (el flujo documentado como el más usado), el sudoers
real del servidor quedaba desactualizado sin ningún aviso hasta el próximo `--upgrade`. Movido a
la sección compartida a todos los modos (mismo criterio que el symlink del CLI `voxikam`).

**ALTO — `customers.profile_id` faltaba en la rama de migración `--upgrade`**

Encontrado por el agente de QA: la rama `--update` sí migraba `profile_id` junto con los
`show_*`, la rama `--upgrade` (usada en instalaciones productivas ya existentes) solo tenía los
`show_*`. Una instalación que solo hubiera corrido `--upgrade` desde antes de que existiera
`customer_profiles` dejaba el sistema de perfiles de módulos silenciosamente inoperante (el
`LEFT JOIN customer_profiles` de `require_module()` fallaba, tragado por su propio `except`).
Agregado el `ADD COLUMN IF NOT EXISTS profile_id` faltante.

**MEDIO — factura sin PDF, sin ningún rastro del motivo**

`backend/routers/invoices.py::generate_invoice()`: el bloque de generación de PDF tenía un
`except Exception: pass` sin log ni rollback — un fallo real quedaba invisible para el admin, y
la sesión de DB seguía usándose después en un estado potencialmente inconsistente. Ahora loguea
con traceback completo y hace rollback explícito.

**MEDIO — página Trunk Guide se queda cargando para siempre si falla el fetch**

`frontend/app/(client)/my/trunk-guide/page.tsx` era el único caso real de "loading infinito"
encontrado por el agente de frontend (patrón más amplio de fetches sin manejo de error visible,
repetido en la mayoría de páginas del panel — no se tocó ese patrón general esta sesión, queda
como mejora de UX pendiente de alcance a definir). Agregado `.catch` con mensaje de error visible.

**Limpieza — imports muertos**: `live.py` (`defaultdict`), `admin_users.py` (`Optional`),
`quality.py`/`portal.py` (`require_client`, no usado en ninguno de los dos — ambos gatean con
`require_module`/`get_current_user`).

**Confirmado, sin cambios necesarios**: superficie de sudo acotada y sin margen de escalación
(`nft`/`kamcmd`/`fail2ban-client`/systemctl allowlist, todo validado); longest-prefix-match
consistente en los 3 lugares que tarifan; balance atómico (`UPDATE ... SET balance = balance -
:x`, sin condición de carrera); sin inyección SQL en 15+ routers revisados; sin secretos
hardcodeados; `python-jose` con mitigación parcial ya presente (algoritmo forzado, sin RSA/EC) —
librería envejecida, no urgente, a considerar para una futura migración a PyJWT.

**Pendiente de decisión del usuario, no de un bug** (ver CLAUDE.md → Roadmap/Pendientes):
confirmar en logs reales de producción si algo llama efectivamente a `POST /ingest`; módulo de
API keys de cliente completo en el backend sin ninguna UI que lo exponga; toggle de fail2ban
"jail" a medio construir en el panel de Firewall; patrón general de fetches sin manejo de error
visible en la mayoría de páginas del panel.

## v2.37.1 — 2026-07-09

### Limpieza post-validación: tipos TS + tokens de color

Dos observaciones menores del agente de frontend en la validación de 4 agentes, ambas
cosméticas (sin impacto funcional), corregidas a pedido explícito del usuario:

- `frontend/app/(client)/my/reseller/carriers/page.tsx` y `carriers/[id]/page.tsx`: la interfaz
  `Carrier` no incluía `remove_prefix` aunque el backend sí lo devuelve — no rompía nada porque
  `form` está tipado `any`, pero quedaba como trampa latente para el futuro. Agregado el campo.
- 6 páginas (`/my/reseller/*` completo + `/carriers` admin) usaban clases Tailwind fijas
  (`bg-zinc-900`, `text-zinc-400`, etc.) en vez de los tokens `var(--color-card)`/`--color-text`/etc.
  ya usados por el resto del panel — funcionaban bien hoy (paleta única, sin tema claro/oscuro
  conmutable todavía), pero un cambio de paleta futuro hubiera requerido tocar archivo por
  archivo en vez de un solo lugar (`globals.css`). Migradas a tokens, dejando SIN tocar a
  propósito los badges de estado inactivo/desactivado (`bg-zinc-700`/`bg-zinc-800`), que ya son
  el mismo patrón fijo usado en todo el panel, migrado o no — no es una inconsistencia real.

## v2.37.0 — 2026-07-09

### Fix: colisión de techprefix por prefijo, no solo por igualdad exacta

Encontrado en la validación de 4 agentes que corrió sobre todo el trabajo de esta sesión (ver
"REGLA OBLIGATORIA — 4 validaciones" en CLAUDE.md — desde ahora esta validación se corre siempre
al cerrar trabajo de código). `_assert_techprefix_free()` (agregada en este mismo release, ver más abajo)
validaba duplicado **exacto** (`WHERE techprefix = :tp`), pero Kamailio matchea el techprefix
contra el número marcado por **substr/prefijo de string**
(`scripts/gen_dispatcher.py::build_routes_cfg()`), evaluado en bloques `if` secuenciales. Dos
prefijos donde uno es prefijo del otro (ej. `"100"` y `"1005"`) son strings distintos — pasaban
la validación — pero colisionan en producción: el primero que matchea en el `.cfg` generado se
queda con las llamadas del segundo, sin ningún aviso. Corregido en `backend/routers/reseller.py`
y `backend/routers/customers.py` — la validación ahora es bidireccional
(`:tp LIKE CONCAT(techprefix,'%') OR techprefix LIKE CONCAT(:tp,'%')`), y `_next_techprefix()`
usa el mismo chequeo al generar el próximo prefijo libre.

### Perfiles granulares para el portal de reseller

A pedido del usuario, tras aclarar que "eso de profile solo no me cuadra" — hasta ahora un
reseller veía SIEMPRE las 4 páginas de su portal (Sub-clientes, Tarifas propias, Carriers
propios, Resumen/margen) sin que el admin pudiera ocultar ninguna. El sistema de Perfiles
(`customer_profiles`) solo cubría módulos de cliente normal.

- 4 columnas nuevas en `customers` y `customer_profiles`: `show_reseller_customers`,
  `show_reseller_rates`, `show_reseller_carriers`, `show_reseller_dashboard` — default `1` (no
  le saca acceso a ningún reseller existente al actualizar). Mismo patrón dual que ya usan
  `show_calls`/`show_quality`/etc: la columna vive tanto en `customers` (flags manuales por
  cliente) como en `customer_profiles` (plantilla reusable), con `COALESCE(perfil, propio)`
  resolviendo cuál manda.
- `backend/auth.py`: nueva `require_reseller_module(column)` — combina la validación de
  `is_reseller=1` con el chequeo del módulo puntual, aplicada a los ~30 endpoints de
  `reseller.py` según a qué página del portal pertenecen. `GET /reseller/carriers/assignable`
  se gatea por `show_reseller_customers` (no por `show_reseller_carriers`) a propósito — lo
  consume la página de Sub-clientes al asignar un carrier, no la de Carriers propios.
- Admin ahora puede ver y togglear estos 4 módulos por reseller puntual, desde la ficha del
  cliente (`/customers/{id}`, sección "Módulos del portal reseller" — solo visible si
  `is_reseller=1`) o desde un Perfil reusable (`/profiles`).
- Sin este cambio, un reseller con `profile_id` asignado heredaba automáticamente todos los
  módulos de reseller habilitados sin que el admin pudiera restringirlos — ahora es una
  decisión explícita, igual que ya lo es para los módulos de cliente normal.

### Margen reseller — confirmado el diseño existente

El usuario preguntó si el margen de 3 niveles (costo real del carrier → precio mayorista al
reseller → precio del reseller a su cliente) ya estaba cubierto. Confirmado: sí — `cdrs.reseller_cost`
ya lo calcula por destino/prefijo desde antes de este release (rate_plan propio del reseller
como "lo que le cobra el admin"), sin necesidad de precio por carrier. Los carriers en VoxiKam
son solo mecanismo de ruteo, nunca de precio — a propósito, para que la tarifa no cambie sola
ante un failover. Sin cambios de código en esta sección — quedó documentado para no reabrir la
pregunta más adelante.

## v2.36.0 — 2026-07-09

### Prefijo técnico automático (reseller) + validación global de choques

Bug real preexistente encontrado al revisar el feature de carriers propios: `techprefix` (el
string que Kamailio usa para identificar de qué cliente es una llamada saliente, en
`voxikam-routes.cfg`) **nunca se validaba como único** — ni al crear clientes desde el admin, ni
sub-clientes desde un reseller. Dos clientes con el mismo prefijo (o el mismo elegido por
casualidad por dos resellers distintos) hacían que las llamadas del segundo se enrutaran y
facturaran contra el primero — el primer `if` que matchea en el `.cfg` generado gana, sin ningún
aviso.

- `reseller.py`: `techprefix` pasa a ser opcional al crear un sub-cliente — si se deja vacío, se
  autogenera buscando el primer número libre (a partir de 1000) contra **toda** la tabla
  `customers`, sin filtrar por dueño — así nunca choca con un prefijo del admin ni de otro
  reseller. Si se manda a mano, se valida contra la misma tabla completa antes de guardar.
- `customers.py` (admin): mismo chequeo de unicidad agregado a crear/editar cliente — antes tampoco
  validaba nada ahí, ni siquiera para dos clientes directos del admin.
- Sin cambios de schema — `techprefix` ya tenía índice (`idx_techprefix`, no único, solo de
  performance) desde antes.

### Admin: menú "Resellers" separado de Clientes

A pedido del usuario — antes un reseller aparecía mezclado en la lista plana de "Clientes" sin
ninguna marca visual, sin conteo de sub-clientes, indistinguible de un cliente directo.

- Nueva página `/resellers` (grupo "Clientes" del sidebar) — lista solo `is_reseller=1`, con
  conteo de sub-clientes y el mismo criterio de "Mostrar desactivados" que ya usa Clientes. Un
  reseller desactivado **no desaparece** de esta lista — se queda marcado "inactivo", nunca se
  vuelve invisible como si nunca hubiera existido.
- `/customers` ahora excluye resellers por defecto (`exclude_resellers=true`), con un link a
  `/resellers` para no dejarlos "perdidos". El endpoint `GET /admin/customers` sigue devolviendo
  TODOS los clientes por defecto si no se manda ningún filtro — Firewall, Calidad, Facturas y el
  Simulador de ruteo siguen viendo resellers en sus selectores sin cambios, no rompió nada de lo
  que ya dependía de la lista completa.
- Se reutiliza la ficha de detalle existente (`/customers/{id}`, con el toggle "Convertir en
  reseller" ya construido en v2.28.0) — no se duplicó ningún formulario.

## v2.35.0 — 2026-07-09

### Reseller: carriers propios (modelo MagnusBilling)

A pedido explícito del usuario ("tal cual funciona magnus billing ps que da la oportunidad que reseller ponga sus propios carriers") — un reseller ahora puede cargar sus propias troncales SIP, con sus propios buy-rates, y asignarlas (junto o en vez de las de la plataforma) a sus sub-clientes. Mismo criterio "mini admin" ya usado con prefijos y planes de tarifas.

- **`carriers.owner_customer_id`** (nullable FK, mismo patrón que `prefixes`/`rate_plans`): `NULL` = carrier de la plataforma, no-`NULL` = propio de un reseller.
- **`gen_dispatcher.py` no necesitó ningún cambio** — ya arma el grupo de dispatcher por cliente (`100 + customer_id`) leyendo `customer_carriers`, sin importar quién es dueño del carrier asignado.
- **Backend `/api/reseller`**: CRUD completo de carriers propios (`GET/POST/PUT/DELETE /carriers`), tarifas de costo individuales y por grupo (`/carriers/{id}/rates`, `/carriers/{id}/group-rates`), y asignación/desasignación de carrier (propio o de plataforma) a un sub-cliente (`/sub-customers/{id}/carriers`) — con validación explícita de que solo puede asignar carriers propios o de la plataforma, nunca de otro reseller.
- **Backend admin (`/api/admin/carriers`)**: por defecto solo muestra carriers de la plataforma; `include_reseller=true` (con nombre del reseller dueño) para soporte.
- **Frontend admin**: checkbox "Incluir carriers de resellers" + badge de dueño en la lista de Carriers.
- **Frontend reseller**: página nueva "Carriers propios" (`/my/reseller/carriers`, CRUD + detalle de buy-rates igual que la vista admin) y sección "Carriers asignados" en la ficha de cada sub-cliente (asignar/quitar, con badge "tuyo" para diferenciar de los de plataforma).
- Auditoría completa desde el día uno: todas las mutaciones nuevas (`created_by_reseller`, `deleted_by_reseller`, `buy_rate_set`, `carrier_assigned`, `carrier_removed`, etc.) quedan registradas — más los gaps de auditoría preexistentes en `carriers.py` (buy rates admin) y `reseller.py` (prefijos/planes de tarifas) que se encontraron y corrigieron de paso.
- Sin cambios de infraestructura ni de Kamailio — solo backend/frontend, no requiere `--upgrade` (alcanza con `--update`).

## v2.34.1 — 2026-07-08

### Auditoría: barrido completo — 6 routers con acciones reales sin registrar

A pedido del usuario ("valida todo el sistema y qué opciones generan cambio") — barrido de los 33 routers backend contra `record_event()`/`diff_and_record()`. Encontrados y corregidos 6 archivos con mutaciones (INSERT/UPDATE/DELETE o acciones con efecto real) que no dejaban ningún rastro en Auditoría, a pesar de calzar con el criterio propio de la página ("impacto en servicio, dinero o seguridad"):

- **`rates.py`** (el más grave — pricing sin auditar): crear/editar/borrar plan de tarifas, cargar tarifa individual o por grupo, borrar tarifa, crear/editar/borrar prefijo — 9 endpoints.
- **`invoices.py`** (facturación): generar factura, marcar pagada, reenviar por correo, activar/desactivar auto-envío, editar plantilla, subir/borrar logo — 7 endpoints. `marked_paid` sin auditoría era el hueco más serio (sin registro de quién marcó una factura como pagada).
- **`mail_config.py`**: guardar configuración de correo (SMTP/Resend) — nunca se registran secretos (API key/contraseña) en el detalle, solo qué proveedor quedó activo.
- **`profiles.py`**: crear/editar/borrar perfil de cliente (controla qué módulos ve cada cliente).
- **`system_services.py`** (v2.33.1, el mismo día): apagar/reencender servicios del sistema desde el panel — el hueco que disparó esta revisión completa.

Confirmado qué NO se audita a propósito, no por descuido: `comments.py` (el comentario mismo ya es el registro, con su propio `created_by`/`created_at`), `live.py::/stale` (limpieza de caché de monitoreo, no datos de facturación), vistas/lecturas de cualquier tipo (eso es un log de acceso, no de auditoría — ya existe en los access logs de nginx).

Auditoría (frontend): agregados los filtros de entidad que faltaban — varios ya se registraban en el backend desde antes pero nunca tuvieron botón de filtro (`area`, `api_key`, `disconnect_policy`, `external_sync_config`, `rate_plan_draft`, `traffic_sampling`, `webhook`), más las 6 entidades nuevas de este batch.

## v2.34.0 — 2026-07-08

### Traza SIP completa — tramo de entrada de INVITE/BYE, sin duplicados

Cierre del tema de la traza que quedaba incompleta (v2.32.0-v2.33.3): el ladder solo mostraba el tramo de SALIDA de los requests relayed (INVITE, BYE) — nunca el de llegada real (origen→SBC). Dos intentos anteriores de agregar `sip_trace()` en otro punto del script no sirvieron (produjeron duplicados exactos, no el tramo faltante) — investigado a fondo con 3 pasadas de research contra el código fuente real de `siptrace.c` hasta encontrar la causa raíz: el modo anterior (`trace_flag` + `sip_trace()` llamado a mano) engancha callbacks de transacción SIP (TM) que **no tienen un callback de "request recibido"**, solo de "request enviado" — por eso las respuestas (100/180/200) sí se veían completas (esas sí tienen callback de entrada y salida) pero los requests nunca.

- Reemplazado por `trace_mode`/`trace_on` (mismo módulo `siptrace`, modo distinto) — engancha los eventos de red del núcleo (`SREV_NET_DATA_RECV`/`SENT`), un nivel más abajo que el de transacción SIP: captura cada paquete real en ambos sentidos automáticamente, sin necesitar ningún `sip_trace()` disperso por el script. Quitados los 4 `setflag(28); sip_trace();` que existían (documentado explícitamente que dejarlos junto con `trace_mode` duplica la captura).
- Agregado `event_route[siptrace:msg]` para filtrar OPTIONS (keepalive de dispatcher, cada 10s por carrier/cliente) y REGISTER (rechazados igual, pero antes invisibles a la traza) — sin esto, `trace_mode` habría empezado a inflar `sip_traces` con tráfico que antes nunca se capturaba.
- **Requiere `--upgrade`** (reinicia Kamailio). Validado con `kamailio -c -f` antes de cada intento; el cambio final es más chico que los dos intentos anteriores combinados (se sacó código, no se agregó).

## v2.33.4 — 2026-07-08

### Sistema → Salud: el uso del CLI voxikam no estaba explicado en ningún lado

El texto "reiniciar/logs en vivo: CLI voxikam por consola" mencionaba el comando pero nunca decía cómo usarlo — el usuario tenía que adivinar los flags. Ahora es un desplegable con la sintaxis completa (`-s`/`-r`/`-p`/`-l`, lista de servicios válidos, ejemplos) directamente en la tarjeta "Servicios VoxiKam".

## v2.33.3 — 2026-07-08

### Feedback de UI real (capturas): CDRs, Salud del sistema y traza SIP

- **Búsqueda de CDRs lenta (1.47s con teléfono+fecha)**: `list_cdrs()`/`list_failed_cdrs()` corrían la MISMA consulta cara dos veces — una para las filas, otra idéntica solo para `COUNT(*)` de paginación. El filtro `phone LIKE '%...%'` no es indexable, así que cada corrida escaneaba igual. Ahora el `COUNT(*)` solo se ejecuta cuando la página vino llena (podría haber más resultados); si vino incompleta, el total sale gratis de `offset + filas devueltas` — corta el costo a la mitad en búsquedas angostas (teléfono/fecha), que son las más comunes.
- **Cron jobs en rojo sin explicación**: `cron_health.py` buscaba el marcador de error (`✗`/`Error:`) en los últimos 4KB del log completo, no en la última corrida — como estos jobs corren cada 60s agregando una línea por corrida al mismo archivo, 4KB cubre 40-60 minutos de historial, así que un error viejo seguía marcando rojo aunque las corridas recientes ya estuvieran bien. Corregido para mirar solo la última línea. Además, cada fila del panel Sistema → Salud ahora muestra la palabra del estado (OK/ATRASADO/ERROR/SIN LOGS), no solo un punto de color — y si es error, el motivo aparece debajo sin tener que pasar el mouse.
- **Panel de detalle de CDR — "Estado" separado**: "Resultado" (completada/ocupada/etc.), "Código SIP" y "Colgó" (Cliente/Proveedor) ahora son tres filas independientes en vez de tres badges amontonados en una.
- **Semáforo de calidad**: nueva fila "Calidad" con badge verde/amarillo/rojo (Buena/Regular/Mala) calculado por umbrales de jitter y pérdida de paquetes — para quien no sabe qué es "jitter", el semáforo ya le dice si la llamada estuvo bien. Los números crudos siguen debajo para quien los quiera.
- **Traza SIP — tramo de entrada faltante**: el ladder solo mostraba el tramo de SALIDA de cada request relayed (INVITE, BYE) — nunca el de entrada (origen→SBC) — porque `sip_trace()` se llamaba después de que el ruteo ya resolvía el destino. Confirmado que no era un bug nuevo: el INVITE inicial tenía el mismo hueco. La atribución de quién colgó (`hangup_cause`) ya era correcta independientemente de esto — es un hueco puramente visual. Agregadas llamadas `sip_trace()` adicionales en `kamailio.cfg.j2`, ANTES de resolver el destino, tanto para el INVITE inicial como para mensajes in-dialog — puramente aditivo, no toca ruteo/dispatcher/CDR. **Requiere `--upgrade` (reinicia Kamailio) para tomar efecto** — recomendado validar con `kamailio -c -f /etc/kamailio/kamailio.cfg` antes de reiniciar.

## v2.33.2 — 2026-07-08

### Bug real: voxikam-autotune.service fallaba con "Permission denied" al arrancar

Reportado en producción con el error real de `journalctl`: `Failed to locate executable /opt/voxikam/scripts/autotune.sh: Permission denied`. Causa raíz: `scripts/autotune.sh` estaba trackeado en git como `100644` (no ejecutable) mientras sus scripts hermanos (`_colors.sh`, `fix_rtpengine.sh`) sí tenían `100755` — nadie lo había notado porque el único `chmod +x` que lo arreglaba vivía DENTRO del bloque exclusivo de `--upgrade`. Un `--update` (que vuelve a correr el mismo rsync compartido, preservando el modo de git) lo dejaba no-ejecutable de nuevo aunque un `--upgrade` previo lo hubiera arreglado — la secuencia "upgrade una vez, después update" que parecía segura no lo era para este archivo puntual.

- Arreglado el bit +x en el archivo trackeado.
- Agregado un `chmod +x scripts/*.sh` y `scripts/setup/*.sh` incondicional en deploy.sh, corriendo en TODOS los modos justo después del rsync — no depende de acordarse de marcar +x antes de cada commit para cualquier script nuevo que se agregue a futuro.

## v2.33.1 — 2026-07-08

### Grabación de llamadas confirmada sin uso — movida a la allowlist de un click

El admin confirmó que no usa grabación de llamadas — `rtpengine-recording-daemon.service`, `rtpengine-recording-nfs-mount.service` y `rpcbind.service` (que solo servía para ese mount NFS) pasan de "requiere confirmación humana" a la allowlist accionable de Sistema → Salud → "Otros servicios del sistema", con su línea exacta correspondiente en `sudoers/voxikam`. Libera los 7 procesos `rtpengine-recording` vistos en producción.

## v2.33.0 — 2026-07-08

### Plantilla de factura editable

Módulo pendiente desde antes del reordenamiento del Dashboard — panel nuevo **Reportes → Plantilla de factura** (`/invoice-template`) para personalizar la marca del PDF sin tocar la estructura (tabla de llamadas, totales, IGV siguen hardcoded).

- Cuatro secciones, cada una con su propio checkbox — el admin decide qué usar, nada es obligatorio: **Logo** (PNG/JPG, subido a `invoices/branding/` — anidado dentro de `invoices/`, que ya está excluido del `rsync --delete` de cada deploy desde v2.29.0, así que sobrevive a futuros deploys sin agregar otro exclude), **Encabezado de empresa** (razón social/RUC/dirección), **Pie de página** (texto libre), **Color de acento** (reemplaza el ámbar por defecto de VoxiKam en título/total/razón social).
- Backend: `GET/PUT /admin/invoices/template` + `POST/GET/DELETE /admin/invoices/template/logo`, mismo patrón `settings` key/value que ya usa Sistema → Correo. `_generate_pdf()` ahora recibe la plantilla como parámetro (fetcheada por el caller, la función sigue siendo síncrona) — aplica en `generate_invoice()` y `regen_pdf()` por igual.
- El logo se sirve por un endpoint autenticado (no un `<img src>` directo — el JWT no viaja en ese tipo de request), el frontend lo trae como blob y arma un object URL para la vista previa.

## v2.32.0 — 2026-07-08

### CLI `voxikam`, panel de servicios del sistema, y correo multi-proveedor

- **CLI de administración** (`scripts/voxikam-cli.sh`, symlink en `/usr/local/bin/voxikam`, instalado en TODOS los modos de deploy): `voxikam -s|-r|-p|-l [back|front|hep|kamailio|rtpengine|autotune|app|all]` — evita acordarse de los nombres reales de las unidades systemd para el día a día. `-r`/`-p` piden sudo, `-s`/`-l` no.
- **Sistema → Salud**: nueva tarjeta "Servicios VoxiKam" (estado + últimas 5 líneas de log de cada servicio propio, solo lectura — reiniciar/seguir logs en vivo sigue siendo tarea del CLI por consola, a propósito: el backend nunca tuvo ni tiene permiso de `systemctl restart/stop` sobre sí mismo). Requiere agregar el usuario `voxikam` al grupo `systemd-journal` (nuevo paso en deploy.sh) para poder leer el journal.
- **Sistema → Salud**: nueva sección colapsable "Otros servicios del sistema" — barrido completo de TODOS los servicios habilitados en el server (no solo los de VoxiKam), clasificados en necesarios / candidatos a apagar / no reconocidos. Apagar/reencender solo está habilitado para una allowlist chica y explícita (avahi-daemon, cups, cups-browsed, ModemManager, bluetooth, snapd) — cada uno con su línea exacta en `sudoers/voxikam` (`systemctl disable/enable --now <unit>` fijo, nunca `systemctl` genérico, para no abrir una superficie de ataque si un JWT de admin se compromete). Contrastado contra un barrido real de producción (vd1sbc2): confirmó que el nombre real del servicio es `rtpengine-daemon.service` (no `rtpengine.service`, corregido en el clasificador) y encontró un caso real NO incluido en la allowlist de un click: `rpcbind.service` está activo porque `rtpengine-recording-nfs-mount.service` lo necesita para el NFS donde se guardan las grabaciones de llamadas — apagarlo a ciegas rompería ese feature si está en uso, así que se deja fuera del botón de un click y documentado como "requiere confirmación humana", no automatizado.
- **Sistema → Correo**: rediseño completo — antes solo soportaba Resend sin explicar qué era ni de dónde sacar la API key. Ahora hay selector Resend/SMTP propio (host, puerto, usuario, contraseña, cifrado STARTTLS/SSL/ninguno), textos explicando qué es cada proveedor y dónde crear la cuenta/API key, y un botón "Enviar correo de prueba" para validar la config antes de confiar en alertas/facturas automáticas. Backend: `mailer.py` ahora soporta ambos proveedores (`aiosmtplib` para SMTP), la contraseña SMTP se guarda en `settings` igual que la API key de Resend (nunca se devuelve en texto plano).

## v2.31.0 — 2026-07-08

### Gestión de prefijos de destino — bug de descubrimiento + reseller "mini admin"

El admin reportó no poder entender por qué "Áreas" mostraba 2M+ de CDRs "Sin área" mientras las áreas que había creado (FIJO LIMA, FIJO PROVINCIA, MOVILES, PERU) aparecían vacías o sin poder cargarles prefijos.

- **Bug real encontrado**: en Tarifas → "Prefijos de destino", el selector de Área al crear un prefijo nuevo salía de `/admin/rates/groups` — una lista que solo incluye grupos que YA tienen al menos un prefijo asignado. Un área recién creada (0 prefijos, como "PERU" en este caso) nunca podía aparecer ahí — problema del huevo y la gallina, no había forma de asignarle el primer prefijo desde la UI. Ahora ese selector sale del registro formal (`/admin/areas`), que sí incluye áreas vacías. Se sumó edición inline de prefijos (antes solo alta/baja) usando el endpoint `PUT /admin/rates/prefixes/{id}` (nuevo).
- Página Áreas: en vez de duplicar la gestión de prefijos ahí también, se dejó un puntero claro a Tarifas → Prefijos (una sola fuente de verdad).
- **Reventa multinivel — reseller como "mini admin"** (a pedido del usuario, referenciando el modelo de MagnusBilling): el reseller ahora puede crear sus propios prefijos/destinos y grupos, igual que el admin crea los de la plataforma — antes `/reseller/prefixes` era 100% solo-lectura. Cada reseller ve y edita únicamente lo que él mismo creó ("el admin ve lo suyo y el reseller ve lo suyo"), pero al armar sus propios rate plans puede tarifar tanto sus prefijos propios como los de la plataforma (nunca los de otro reseller). El motor de tarifación (`cdrs.py::ingest_cdr`) no cambia — sigue haciendo longest-prefix-match contra toda la tabla sin filtrar por dueño, así que un prefijo privado del reseller tarifa igual de bien en cuanto tiene una tarifa cargada.
  - Nueva columna `prefixes.owner_customer_id` (NULL = plataforma).
  - Nuevos endpoints reseller: `POST/PUT/DELETE /reseller/prefixes`, `POST /reseller/rate-plans/{id}/group-rates` (tarifa por grupo en bloque, ya existía para admin).
  - Portal reseller (`/my/reseller/rates`): sección colapsable "Mis prefijos" + tabs "Individual"/"Por grupo" al agregar tarifas, mismo patrón que ya tiene el admin en Tarifas.

## v2.30.0 — 2026-07-08

### Dashboard simplificado — diagnóstico interno mudado a Sistema → Salud

A pedido del usuario: el Dashboard mezclaba KPIs de negocio (facturado, ganancia, llamadas) con diagnóstico interno (cron jobs, cola de captura HEP) que no tiene nada que ver con eso, y la tabla "Llamadas activas por cliente" duplicaba lo que ya muestra Live con más detalle.

- Nueva página **Sistema → Salud** (`/system-health`): Cron jobs + captura de trazas (mini-Homer), sacados tal cual del Dashboard.
- La tarjeta de captura HEP se reorganizó de paso — antes mezclaba SIP y RTCP en la misma fila por tipo de métrica (cola, descartados, flush todos juntos); ahora un bloque por protocolo, se lee de corrido.
- Dashboard: la tabla "Llamadas activas por cliente" se reemplazó por un resumen compacto (pastillas por cliente, solo si hay alguno activo) con link a Live para el detalle completo — el total ya está en el KPI "Activas ahora", la tabla era redundante.

## v2.29.0 — 2026-07-08

### Kamailio y RTPEngine requerían reinicio manual después de CADA reboot completo

Reportado por el usuario con logs reales de `systemctl status` en producción (vd1sbc2). **Requiere `./deploy.sh --upgrade` para aplicarse — vive en la parte del instalador que `--update` se salta (confirmado leyendo el código: la rama `update` hace `exit 0` antes de llegar a esta sección). Tocar en ventana de mantenimiento — reinicia Kamailio/RTPEngine, corta llamadas en curso.**

- **Causa raíz de Kamailio**: `Can't connect to server on '127.0.0.1' (115)` — el módulo `sqlops` no lograba conectar a MariaDB al arrancar, tumbando el proceso completo (`cannot fork timer process`). El `Requires=`/`After=mariadb.service` que ya existía (agregado en una sesión anterior, mismo servidor, mismo síntoma — comentario en el código lo confirma) solo garantiza que el *unit* de MariaDB ya inició, no que ya esté aceptando conexiones — su recuperación interna puede tardar unos segundos más. Nuevo `ExecStartPre` en el override de systemd de Kamailio: espera activa por TCP puro a `127.0.0.1:$DB_PORT` (sin depender de `mysqladmin` ni credenciales), hasta 30s, fail-open si nunca responde (no bloquea el arranque indefinidamente). Probado en este entorno contra un puerto real abierto y uno cerrado — se confirma que sale apenas responde y no cuelga el arranque si no responde nunca.
- **`scripts/autotune.sh`** (corre en cada boot, después de Kamailio): su lógica de "reiniciar Kamailio si algo cambió" solo miraba si los valores de memoria/children calculados eran distintos — nunca si Kamailio estaba directamente caído. En un host con CPU/RAM estables entre reboots, esos valores nunca cambian, así que nunca lo reiniciaba solo. Ahora también reintenta si detecta `kamailio` inactivo, sin importar si la config cambió — como corre después en el orden de arranque, para cuando le toca MariaDB ya lleva más tiempo arriba.
- **Causa raíz de RTPEngine**: `FAILED TO DELETE KERNEL TABLE 0 (Permission denied), KERNEL FORWARDING DISABLED` en cada boot en frío — el módulo kernel `xt_RTPENGINE` (compilado vía DKMS, confirmado funcional en v2.24.14) no lo cargaba nada automáticamente al arrancar. Nuevo `ExecStartPre=-/sbin/modprobe -q xt_RTPENGINE` antes del `rtpengine-iptables-setup` empaquetado — el `-` inicial evita que un fallo del modprobe rompa el arranque (RTPEngine seguiría funcionando en modo userspace-only como hasta ahora, sin peor que antes).

### Los PDF de facturas se borraban solos en cada deploy — bug de datos real, no de generación

Reportado por el usuario: facturas que mostraban el link "PDF" fallaban al descargar con "PDF no disponible o aún no generado" — pero solo después de un tiempo, nunca al generarlas. **Esto aplica con `--update` también, no solo `--upgrade`** — corre en el paso de sincronización de código, antes de que los modos diverjan.

- **Causa raíz**: `deploy.sh` sincroniza el código con `rsync -a --delete` cuando el origen es distinto al directorio instalado — borra en `$INSTALL_DIR` todo lo que no exista en el origen del deploy. `invoices/` (donde `backend/routers/invoices.py::_generate_pdf()` guarda los PDF generados) y `logs/` (logs de cron) son directorios que se generan en tiempo de ejecución, nunca vienen en el código fuente — así que **cada deploy borraba todos los PDF ya generados**, dejando la referencia `pdf_path` huérfana en la tabla `invoices` (por eso el botón seguía diciendo "PDF" y no "Generar PDF", pero fallaba al hacer clic).
- Agregado `--exclude='invoices/'` y `--exclude='logs/'` a ambos `rsync` (instalación existente y fresh install).
- **Los PDF ya perdidos no se pueden recuperar del disco** (no hay backup de esos archivos), pero sí se pueden regenerar sin perder el histórico: el endpoint `POST /admin/invoices/{id}/regen-pdf` ya existe y recalcula el PDF desde los CDR reales (que nunca se tocaron, siguen en la DB) — el botón "Generar PDF" en el panel hace exactamente eso.

## v2.28.2 — 2026-07-08

### Traza SIP: el SBC aparecía como "Destino" en su propia IP pública

Reportado por el usuario mirando una traza real: `10.10.0.5` (LAN) se etiquetaba bien "SBC", pero `203.0.113.10` (WAN, la MISMA máquina) aparecía como "Destino" — la heurística de `SipLadder.tsx` ("el nodo con más pares distintos es el hub") solo puede detectar una IP como el SBC, y con dual-NIC el SBC aparece dos veces en la traza (una IP hablando con el cliente, otra con el carrier).

- `backend/routers/traces.py::get_trace()` ahora devuelve `sbc_private_ip`/`sbc_public_ip`, leídas de `.env` (`PRIVATE_IP`/`PUBLIC_IP` — ya se escriben ahí desde el instalador, no hizo falta tocar nada del deploy ni la DB).
- `SipLadder.tsx`: `nodeRole()` matchea esas IPs directo antes de caer en la heurística posicional — ahora ambas interfaces del SBC se etiquetan "SBC (LAN)"/"SBC (WAN)" en vez de que una quede como "Destino".
- Propagado desde los dos lugares que usan `SipLadder` (`/traces` y el detalle de CDR en `/cdrs`).
- **Nota de seguridad, discutida con el usuario**: exponer `PRIVATE_IP` vía API no es un riesgo nuevo — el endpoint ya está detrás de `require_admin`, y esa misma IP ya aparecía sin etiquetar como `src_ip`/`dst_ip` crudo en la misma respuesta.

### Panel de detalle de CDR — layout en tabla, sin colores que parezcan error

Reportado por el usuario: el grid de 2-3 columnas se veía desordenado ("datos a la izquierda, otros a la derecha"), y el rojo en "Compra" parecía indicar un problema cuando es solo un dato normal (el costo del carrier).

- Todo el bloque de info (Llamada, Facturación, Estado, Calidad RTP) pasó de grids sueltos a una sola tabla de 2 columnas (etiqueta | valor) con secciones marcadas — alineación consistente en toda la tarjeta.
- "Compra" pasó de rojo a gris neutro (mismo tono que el resto de los datos) — rojo queda reservado para lo que sí es una alerta real en esta app (BYE/CANCEL, código SIP ≥400, etc.), no para "esto cuesta dinero".
- **No pude probarlo en un navegador real** — no hay `node_modules` instalado ni backend/DB corriendo en este entorno de desarrollo. Validado solo por revisión de código (balance de tags/llaves) — falta la verificación visual real.

## v2.28.1 — 2026-07-08

### Tres gaps documentados en la sesión anterior, cerrados a pedido del usuario

- **`docs/index.html` — backfill del historial v2.9.0 a v2.24.17**: quedaba un hueco desde antes de esta sesión (18 releases sin tarjeta, entre v2.8.9 y v2.25.0). Agregadas 5 tarjetas curadas por tema (mismo criterio que ya usa la página para versiones viejas — resumen agrupado, no volcado de las ~30 entradas individuales).
- **ASR contaba `RESTART_ORPHANED` como llamada fallida**: esas llamadas sí se contestaron (Kamailio perdió el diálogo por un reinicio, no es que el destino haya rechazado la llamada) pero tampoco se confirmó que se facturaran — no son ni "contestada" ni "fallida" para efectos de esta métrica. Excluidas del cálculo completo (no solo de un lado) en `backend/routers/reports.py` (`report_day()`, `report_month()`, `dashboard()`) **y** en `scripts/cron_summary.py` — este último es la fuente real para días históricos vía `cdr_summary_day`, sin tocarlo el fix de `reports.py` solo hubiera arreglado "hoy en vivo".
- **Auditoría inconsistente en `reseller.py`**: `update_sub_customer()` no dejaba ningún rastro en Auditoría (a diferencia de `create_sub_customer()`) — ahora usa `diff_and_record()` con el mismo criterio de campos auditados que `customers.py::update_customer()`. `adjust_sub_customer_balance()` se revisó aparte: ya tenía su propio rastro completo vía `balance_transactions`, mismo mecanismo que usa el equivalente admin — no le faltaba nada.
- De paso (parte del mismo pedido del usuario, no de esta lista): `list_sub_customers()` ahora oculta sub-clientes desactivados por defecto (con su propio "Mostrar desactivados"), y `adjust_sub_customer_balance()` rechaza con 409 si el sub-cliente está desactivado.
- **Gap relacionado, cerrado también a pedido explícito**: `quality.py::_quality_from_cdrs()` (ASR Dashboard admin) nunca filtró por `disposition` en absoluto — contaba CUALQUIER fila de `cdrs` como "contestada", no solo mal-clasificaba `RESTART_ORPHANED`. Agregado `AND c.disposition = 'ANSWERED'`. Al revisar a fondo para cerrarlo del todo aparecieron **3 lugares más** con el mismo patrón que no estaban en la lista original: `scripts/cron_quality.py` (la fuente real de `traffic_quality_hourly`, que alimenta tanto el fallback del ASR Dashboard admin como el ASR del portal cliente completo), y `backend/routers/portal.py::today()`/`my_report()` (el widget "hoy" y el reporte mensual del cliente) — ambos contaban `RESTART_ORPHANED` como llamada fallida en su propio ASR. Barrida final con `grep FROM cdrs` en todo `backend/` y `scripts/` confirmando que no queda un quinto lugar — `areas.py` e `invoices.py` ya filtraban `disposition = 'ANSWERED'` explícito desde antes, sin bug.

## v2.28.0 — 2026-07-08

### UI de reseller — la pieza que faltaba desde v2.24.18

El backend de reventa multinivel (`backend/routers/reseller.py`, `customers.is_reseller`, `rate_plans.owner_customer_id`) se construyó en v2.24.18 pero nunca tuvo pantalla — ni forma de marcar un cliente como reseller, ni dashboard para que el reseller vea sus sub-clientes. Esta versión cierra ese hueco:

- **Admin**: botón "Convertir en reseller" / "Quitar reseller" en el detalle de cliente (`customers/[id]`) — acción separada del formulario general de edición a propósito, mismo criterio que "Desactivar cliente" (v2.25.0), para que no se pueda activar sin querer. Nuevo `POST/DELETE /api/admin/customers/{cid}/reseller`. Quitar el flag se bloquea con 409 si el cliente todavía tiene sub-clientes asignados — evita dejarlos huérfanos de panel.
- **Portal del reseller**: nueva sección "Reseller" en el sidebar del cliente (solo visible si `is_reseller`), suma tres páginas a `/my/*` — no reemplaza el menú normal de cliente, un reseller sigue viendo su propia cuenta igual que cualquier cliente:
  - `/my/reseller` — dashboard de margen del mes por sub-cliente.
  - `/my/reseller/customers` — listar/crear/editar sub-clientes + ajustar su balance.
  - `/my/reseller/rates` — planes de tarifas propios + tarifas por prefijo dentro de cada plan.
- `is_reseller` ahora viaja en la respuesta de `/api/auth/login` (antes no existía en el payload) — mismo criterio que los flags `show_*` de módulos: snapshot al login, no live.
- Nuevo `GET /api/reseller/prefixes` — de solo lectura, un reseller necesita ver la lista de prefijos para tarifarlos, pero `list_prefixes` existente es admin-only.
- Bug de rendimiento encontrado de paso en `reseller.py::dashboard()`: `DATE_FORMAT(start_ts,'%Y-%m') = DATE_FORMAT(CURDATE(),'%Y-%m')` tenía el mismo problema no-sargable de v2.27.0 (mi barrida de esa versión no lo agarró porque el regex no calzaba con `DATE_FORMAT`) — corregido a un rango de límites de mes.
- `frontend/components/Sidebar.tsx`: el resaltado de "activo" pasó de `path.startsWith(href)` a un helper `isNavActive()` (coincidencia exacta o `href + "/"`) en TODOS los links, admin y cliente — necesario porque `/my/reseller` es prefijo literal de sus propias subpáginas (`/my/reseller/customers`, `/my/reseller/rates`) y quedaba marcado activo en las tres a la vez. Mismo resultado que antes para cualquier ruta que no colisiona.
- Dos gaps que quedaron anotados como "fuera de alcance" cuando se construyó el backend de reseller (v2.24.18) se cerraron acá, ahora que hay una UI real que los hace visibles: `list_sub_customers()` gana `?include_deleted=false` por defecto (mismo criterio que `customers.py::list_customers()`, con su propio checkbox "Mostrar desactivados" en `/my/reseller/customers`), y `adjust_sub_customer_balance()` ahora rechaza con 409 si el sub-cliente está `status='deleted'` (el reseller no tiene forma de reactivarlo él mismo, el mensaje se lo aclara).
- Revisado por un agente independiente antes de cerrar: cero bugs confirmados en todo el lote (endpoints, tipos, rutas, el refactor de Sidebar, la query de límites de mes). Encontró un import muerto preexistente en `reseller.py` (`diff_and_record` sin usar) — limpiado de paso.

## v2.27.0 — 2026-07-07

### Búsquedas de CDR lentas (6s+) — filtros de fecha no usaban índice ni partition pruning

A raíz de un reporte del usuario (buscar un teléfono con fecha de hoy tardaba 6.35s), se encontró que **todo el código que filtra `cdrs` por fecha** envolvía la columna en `DATE(start_ts) >= :x` — eso le impide a MySQL usar tanto el índice (`idx_date`/`idx_customer_date`) como el **partition pruning** de `cdrs` (particionada por mes vía `TO_DAYS(start_ts)`), forzando un escaneo del mes completo para filtrar un solo día. Se revisó y corrigió en los 7 archivos que tenían el mismo patrón, reescribiendo cada filtro a un rango sargable (`start_ts >= :x AND start_ts < DATE_ADD(:y, INTERVAL 1 DAY)`), sin cambiar el resultado de ninguna query:

- `backend/routers/cdrs.py` — `list_cdrs()` y `list_failed_cdrs()` (las dos pantallas del reporte de CDRs, admin).
- `backend/routers/areas.py` — reporte de rentabilidad por área.
- `backend/routers/portal.py` — `_get_calls()` (compartida por el portal del cliente **y** `/api/v1/cdrs`), `today()`, `my_report()`.
- `backend/routers/invoices.py` — `_fetch_daily()` y `generate_invoice()`.
- `backend/routers/quality.py` — `_quality_from_cdrs()`.
- `backend/routers/timeseries.py` — `_query_day()`.
- `backend/routers/reports.py` — `report_day()`, `report_month()`, `dashboard()`.

Se dejaron sin tocar los `GROUP BY DATE(start_ts)` / proyecciones (`invoices.py`, `portal.py::my_report()`) — para esos, la query ya llega acotada a un cliente + rango de fechas gracias al fix del WHERE, así que el costo de la función ahí es marginal.

### CDRs admin — detalle de llamada ya no es un popup

A pedido del usuario: el "Detalle de llamada" dejó de abrirse como modal flotante — ahora se muestra dentro de la misma tarjeta de resultados (reemplaza la tabla), con un "← Volver a resultados" para salir. Buscar de nuevo (o cambiar de página/pestaña) vuelve automáticamente a la tabla.

También: la pantalla de CDRs (pestañas Contestadas y No establecidas) ahora abre con **Desde/Hasta en el día de hoy por defecto**, en vez de vacío — antes, una búsqueda sin fecha explícita escaneaba todo el historial.

### Calidad ASR admin — filtrar por cliente tiraba 500

Reportado por el usuario: elegir un cliente puntual en Calidad ASR seguía mostrando todos los clientes. Confirmado con el log real del servidor (`journalctl -u voxikam-backend`) que en realidad era peor — un 500: `pymysql.err.OperationalError: (1054, "Unknown column 'c.customer_id' in 'WHERE'")`. Causa: `backend/routers/quality.py::_quality_from_cdrs()` armaba un único `cid_filter = "AND c.customer_id = :cid"` y lo reutilizaba tal cual en dos queries con alias distintos — la de `cdrs` (alias `c`, donde sí existe `c.customer_id`) y la de `cdrs_failed` (alias `f`) — reventaba en la segunda. Se separó en `cid_filter_ok`/`cid_filter_fail`, cada uno con su alias correcto. Bug preexistente, no introducido en esta sesión — sobrevivió sin tocarse durante el fix de rendimiento de más arriba porque ese cambio no tocaba el alias, solo el `DATE()`.

### Correo de llamadas huérfanas por reinicio — toggle para activar/desactivar

Complementa v2.26.0: se agregó un checkbox en **Sistema → Correo** ("Alertar llamadas interrumpidas por reinicio de Kamailio"), apagado por defecto — mismo criterio que `invoices_auto_email`. El archivo en `cdrs` (`disposition='RESTART_ORPHANED'`) sigue pasando siempre, sin importar este toggle; solo controla si además se manda el correo.

## v2.26.0 — 2026-07-07

### Llamadas huérfanas por reinicio de Kamailio — ya no se pierden en silencio

A raíz de un reporte del usuario sobre números que no cuadraban en el dashboard Live (`/live` mostraba 0 contestadas pero la tabla de detalle mostraba 4 "en curso"), se investigó a fondo con el usuario en vivo contra el servidor de producción — encontramos algo más grave que un bug de UI:

- **Causa raíz**: si Kamailio se reinicia con llamadas en curso, pierde toda la memoria de diálogos. El BYE de esas llamadas nunca le llega a un proceso que ya no las conoce → `event_route[dialog:end]` nunca corre → nunca se genera el CDR. `active_calls` (tabla MySQL, sobrevive el reinicio) queda con filas huérfanas para siempre. Confirmado en vivo: 3 llamadas de dos clientes reales con 29-43 min de antigüedad, `kamcmd dlg.stats_active` mostrando solo 1 diálogo real, y cero CDR para las 3 — llamadas que se contestaron y nunca se facturaron, sin ningún rastro de que existieron.
- **`scripts/cleanup_active_calls.py`** (el script que corre en el `ExecStartPost` de Kamailio) — en su modo "limpiar todo" (el que dispara el reinicio), ahora antes de borrar cada fila de `active_calls` la archiva en `cdrs` con `disposition='RESTART_ORPHANED'` (`billsec`/`sessionbill` en 0 a propósito — no se autofactura una duración estimada, sin la hora real de colgado sería adivinar) y manda un correo al admin (vía Resend, mismas credenciales que ya usa `backend/mailer.py`) con el detalle de cada llamada perdida para que se decida a mano si corresponde cobrar.
- `cdrs.disposition` ENUM suma `'RESTART_ORPHANED'` (`db/schema.sql` + ambos bloques de `deploy.sh`, migración `MODIFY COLUMN` idempotente). Al ser distinto de `'ANSWERED'`, `backend/main.py::_billing_worker()` (`WHERE disposition='ANSWERED' AND buycost=0`) nunca las toca — quedan fuera del billing automático hasta que un admin las reclasifique a mano.
- **`backend/routers/portal.py::_get_calls()`** (compartida por el portal del cliente y `/api/v1/cdrs`) excluye `disposition='RESTART_ORPHANED'` — el cliente no ve este estado interno de reconciliación hasta que un admin lo resuelva.
- Frontend admin (`cdrs/page.tsx`) muestra estas filas con una etiqueta clara "INTERRUMPIDA POR REINICIO" en vez de mostrar el nombre crudo del enum.
- **Nota honesta, no corregida**: el reporte de ASR (`reports.py`) cuenta `disposition != 'ANSWERED'` como llamada fallida — una `RESTART_ORPHANED` sí fue contestada de verdad, así que en un día con reinicio el ASR de ese carrier/cliente se ve levemente subestimado. Impacto mínimo (esto debería ser un evento raro) y ambiguo por diseño — no está claro que "contestada pero sin facturar" deba contar como éxito en ese reporte, así que se dejó como está en vez de decidir unilateralmente.

## v2.25.0 — 2026-07-07

### "Eliminar cliente" ahora desactiva, no borra

Cierra el hueco que quedó anotado en v2.24.19: `cdrs.customer_id` no puede tener FK (la tabla está particionada por mes), así que borrar un cliente con historial de llamadas dejaba CDRs huérfanas apuntando a un id inexistente. A pedido del usuario, un cliente "eliminado" ahora se desactiva en vez de borrarse:

- `customers.status` suma un 4to valor al ENUM: `'deleted'` (antes `active/suspended/expired`) — `db/schema.sql` y los dos bloques de migración de `deploy.sh` (`ALTER TABLE customers MODIFY COLUMN status ENUM(...)`, seguro de re-correr).
- `DELETE /api/admin/customers/{cid}` deja de hacer `DELETE FROM customers` — ahora es `UPDATE ... SET status='deleted'` (`deactivate_customer()` en `customers.py`). Ya no hace falta el catch de `IntegrityError` agregado en v2.24.19 (nada se borra, nada puede violar una FK).
- Nuevo `POST /api/admin/customers/{cid}/reactivate` — revierte a `status='active'`.
- `GET /api/admin/customers` gana `?include_deleted=true` (default `false`) para no mostrar clientes desactivados en el listado a menos que se pida explícitamente.
- Ambos endpoints disparan el webhook `customer.status_changed`, mismo patrón que `update_customer()`.
- Frontend: checkbox "Mostrar desactivados" en el listado de clientes; botón "Desactivar cliente" / "Reactivar cliente" en el detalle. El ENUM `status` sigue sin ser seleccionable como `'deleted'` desde el dropdown de edición genérico — solo se llega ahí por el botón dedicado, para que no se pueda desactivar un cliente por accidente al editar otro campo.

API keys y el simulador de ruteo ya validaban `status == 'active'` explícitamente, así que excluyen `'deleted'` sin ningún cambio de código. El login del portal **sí necesitó un fix real** — `routers/auth.py::login()` y `auth.py::get_current_user()` solo validaban `users.is_active`, nunca `customers.status`, así que un usuario del portal de un cliente recién desactivado podía seguir entrando (o seguir con su sesión activa hasta 20s de cache) sin ningún bloqueo. Encontrado por una revisión independiente de este mismo cambio — corregido antes de cerrar: `login()` ahora rechaza con 403 si el cliente asociado tiene `status='deleted'`, y `get_current_user()` hace `LEFT JOIN customers` para revalidar en cada request (mismo TTL de 20s que ya se usaba para `is_active`). Admin no se ve afectado (`customer_id` es NULL).

**Gap conocido, no corregido en este cambio** (fuera de alcance — reventa multinivel no tiene frontend ni clientes reales todavía): `reseller.py::list_sub_customers()`/`adjust_sub_customer_balance()` no excluyen ni bloquean sub-clientes con `status='deleted'`.

## v2.24.19 — 2026-07-07

### Limpieza de estructura de base de datos

A pedido del usuario, tras una revisión completa del schema (37 tablas) — tres arreglos concretos, ninguno toca facturación en vivo ni el SBC:

- **`carrier_rates.connect_charge` → `connectcharge`** — unifica el nombre con `rates.connectcharge`/`rate_plan_draft_items.connectcharge` (antes había dos convenciones distintas para el mismo concepto). Actualizado en los 3 lugares: la columna (con migración `RENAME COLUMN` idempotente — se chequea antes de correrla, ya que a diferencia de `ADD COLUMN IF NOT EXISTS`, `RENAME COLUMN` falla si se corre dos veces), el backend (`carriers.py`, `cdrs.py`, `main.py`, `routing_sim.py`) y el frontend (`carriers/[id]`, `routing-sim`).
- **`prefix_lengths` eliminada de `db/schema.sql`** — tabla declarada pero sin ningún uso en todo el repo (confirmado por búsqueda exhaustiva). Solo se sacó de instalaciones nuevas — no se agregó ningún `DROP TABLE` para instalaciones existentes, para no borrar nada de una base de datos en producción sin necesidad real.
- **`delete_customer()` ahora maneja el error de FK con un mensaje claro** — antes, borrar un cliente con facturas, movimientos de balance, o (desde v2.24.18) sub-clientes propios como reseller, tiraba un 500 crudo de MySQL. Ahora captura `IntegrityError` y devuelve 409 con un mensaje explicando por qué no se puede borrar.

## v2.24.18 — 2026-07-07

### API de clientes (v1) + reventa multinivel (backend)

Primeras dos piezas del roadmap salido de comparar VoxiKam contra Digitalk/ASTPP/MagnusBilling/YetiSwitch (ver plan en `.claude/plans/fizzy-greeting-minsky.md`). WebRTC queda deliberadamente fuera — la plataforma no tiene HTTPS ni módulos WS/ICE/DTLS hoy, es una iniciativa de varias sesiones dedicadas, no se toca acá.

**API pública de clientes (`/api/v1/*`):**
- Nueva tabla `api_keys` — credencial de entrada (solo se guarda el hash, nunca la key), autoservicio del cliente vía `/api/my/api-keys` (crear/listar/revocar), visibilidad read-only para admin (`/api/admin/customers/{cid}/api-keys`). Gateada por `show_api_access` (default apagado), mismo patrón que `show_invoices`.
- `backend/auth.py::require_api_key()` — nueva dependency, header `X-API-Key`, no reemplaza el JWT existente.
- `backend/routers/api_v1.py` (nuevo) — `GET /balance`, `GET /cdrs`. La lógica de consulta se extrajo de `portal.py` a funciones compartidas (`_get_balance`, `_get_calls`) para que el dashboard y la API nunca diverjan.
- Rate limiting dedicado para `/api/v1/*` (120/60s por API key, no por IP) en `backend/middleware/security.py` y `nginx/voxikam.conf` — no compite con el balde del navegador.

**Reventa multinivel:**
- `customers.parent_customer_id` (jerarquía) + `customers.is_reseller` (flag explícito que activa el admin — mismo criterio que `is_superadmin`, no un rol nuevo en el ENUM) + `rate_plans.owner_customer_id` (tarifas propias del reseller, reusando la tabla `rates` tal cual).
- `cdrs.reseller_cost` (nuevo) — permite separar el margen del reseller (`sessionbill - reseller_cost`) del margen de la plataforma (`reseller_cost - buycost`), calculado en `cdrs.py::ingest_cdr()` y `main.py::_calc_bill()` (el fallback asíncrono) solo cuando el cliente tiene `parent_customer_id`. Para clientes sin reseller, cero cambio de comportamiento.
- **Bug preexistente encontrado y corregido de paso**: el lookup de `buycost` en `cdrs.py::ingest_cdr()` no filtraba por `carrier_id` — hacía longest-prefix-match contra `carrier_rates` de TODOS los carriers a la vez, pudiendo tomar la tarifa de un carrier distinto al que realmente cursó la llamada si dos carriers tenían cargado el mismo prefijo. `main.py::_calc_bill()` (el fallback) ya lo hacía bien — se alinearon ambos.
- `backend/routers/reseller.py` (nuevo, `/api/reseller/*`) — CRUD de sub-clientes y rate plans propios, con scope `parent_customer_id`/`owner_customer_id` incondicional en cada query (no reusa `customers.py`/`rates.py` admin, que no tienen scope). Dashboard de margen por sub-cliente.
- `rate_plans.name` pasa de `UNIQUE` global a `UNIQUE(owner_customer_id, name)` — permite que dos resellers distintos llamen "Standard" a un plan. Nota: MariaDB trata cada NULL como distinto en índices únicos, así que "sin nombres repetidos entre planes de la plataforma" se valida a mano en `rates.py::create_plan()`, el índice solo no alcanza.

Frontend (páginas de reseller, autoservicio de API keys en el portal) queda para la sesión de build — este cambio es backend únicamente.

## v2.24.17 — 2026-07-07

### Detalle de CDR con traza SIP embebida + reorganización de menú + retención hasta 6 meses

- **Traza SIP embebida en el detalle de CDR**: `SipLadder` (el ladder diagram multi-columna que ya vivía en `/traces`) se extrajo a `frontend/components/SipLadder.tsx` — mismo componente, reusado tal cual, sin duplicar lógica. El modal de detalle de un CDR ahora carga y muestra la traza completa de esa llamada (`GET /admin/traces?call_id=`) más un botón "Descargar PCAP" (`GET /admin/traces/pcap?call_id=`, mismo endpoint que ya usaba `/traces`).
- **Menú reorganizado**: "Trazas SIP" salió del menú lateral — solo se llega ahí desde el botón de descarga/traza dentro del detalle de un CDR (la ruta `/traces` sigue funcionando igual, por si se necesita el modo live/búsqueda standalone). "Traffic Sampling" se renombró a **"Retención de datos"** y se movió del grupo Tráfico a Sistema.
- **CDRs: búsqueda explícita, como Digitalk**: la tabla ya no carga nada al abrir la página — hace falta ingresar un teléfono (o usar los filtros) y hacer clic en "Buscar". Antes hacía un `SELECT ... ORDER BY start_ts DESC LIMIT` sin filtro en cada carga de página; ahora no dispara ninguna query hasta que el usuario la pide.
- **Retención de Trazas SIP: tope subido de 30 días a 180 días (6 meses)** — `backend/routers/traffic_sampling.py` y presets del frontend. **CDRs siguen sin borrarse nunca** (decisión de negocio confirmada con el usuario — son registros de facturación, no diagnóstico; a diferencia de Trazas SIP que sí se purgan por ser solo diagnóstico).

## v2.24.16 — 2026-07-07

### CDRs: tabla principal simplificada + detalle completo al hacer clic

A pedido del usuario, comparando contra cómo Digitalk (uno de los carriers) muestra el detalle de cada llamada — la tabla de CDRs tenía 13 columnas apretadas y la columna "Calidad" no se entendía sin contexto.

- Tabla "Contestadas" reducida a 5 columnas: Fecha, Origen, Destino, Cliente, Tiempo. El resto (Carrier, Compra, Venta, Ganancia, Cortó, Cód SIP, Calidad, Traza) pasa a un panel de detalle que se abre al hacer clic en la fila — sin pedir nada nuevo al backend, ya viene en la misma respuesta de `/admin/cdrs`.
- Calidad ahora muestra 4 datos reales en vez del badge compacto `Xms·Y%`: jitter (peor), % pérdida (peor), **paquetes perdidos** (nuevo) y cantidad de reportes RTCP recibidos.
- **`packets_lost` (nuevo, dato real de RTCP, no derivado)**: `call_media_stats` tiene una columna más — `hep_listener.py` ahora también extrae `packets_lost` (acumulado) de cada `report_blocks` de RTPEngine, agregado con `GREATEST()` igual que jitter/pérdida (correcto porque es un contador monótono creciente, el valor más alto visto ya es el más reciente).
- Tab "No establecidas" sin cambios — ya era compacta y no tiene datos de calidad (nunca hubo RTP).

## v2.24.15 — 2026-07-07

### Fix: gráfico "Llamadas por minuto" se aplanaba en cero con tráfico alto

Reportado por el usuario en producción: el Dashboard mostraba huecos en cero en el gráfico "Llamadas por minuto", de forma intermitente. Investigación en vivo (comandos corridos por el usuario en producción):

- **Causa raíz**: con suficientes diálogos activos a la vez (~300+), `kamcmd dlg.briefing` responde `ERROR: reply too big` — Kamailio tiene un límite de tamaño de respuesta para el módulo `ctl` (default 32KB/8KB) que el dump completo de diálogos supera con ese volumen. Confirmado corriendo el pipeline exacto de `cron_dlg_stats.py` a mano en la consola.
- Ese texto de error nunca lanzaba una excepción en Python: se pasaba derecho al parser `awk`, que no matchea ninguno de sus patrones contra una línea de error y termina "exitosamente" con un JSON de 0 llamadas — indistinguible de que no hay tráfico real. `live_snapshot.json` quedaba en cero, y de ahí lo heredaba tanto el panel Live como `cron_timeseries.py` (que sí detecta bien el snapshot vacío y correctamente NO escribe una fila falsa — por eso el gráfico mostraba "sin datos" en vez de un cero engañoso, pero igual quedaba el hueco).
- **Fix en dos partes:**
  - `scripts/cron_dlg_stats.py`: `capture()` ahora lee la salida de `kamcmd` por separado antes de pasarla a `awk`, y trata cualquier respuesta que empiece con `ERROR` como una falla real (no pisa el snapshot anterior) — mismo criterio que ya existía para timeouts/excepciones.
  - `templates/kamailio.cfg.j2`: `modparam("ctl", "binrpc_max_body_size", 16384)` + `binrpc_struct_max_body_size` + `binrpc_buffer_size` (de 32KB/8KB/1KB default a 16MB/16MB/16KB) — para que kamcmd directamente deje de rechazar el dump. El costo en RAM (~32MB) es insignificante frente a la memoria real de Kamailio; se dejó con margen amplio a propósito para no tener que volver a tocar esto pronto.
- **Importante — este cambio de `kamailio.cfg.j2` solo se aplica con `./deploy.sh --upgrade`** (la opción completa del menú), no con `--update` (la rápida, que nunca regenera `kamailio.cfg`). Además, al ser un `modparam`, requiere reiniciar Kamailio para tomar efecto — no se aplica en caliente.

## v2.24.14 — 2026-07-06

### RTPEngine: logs de verdad a syslog + kernel forwarding validado en producción

Validando el cambio de v2.24.13 en producción con el usuario, `/var/log/rtpengine.log` quedó vacío pese a que `rtpengine.conf` y `rsyslog` estaban bien configurados. Investigación en vivo (comandos que corrió el usuario, no simulados):

- **Causa raíz**: `rtpengine-daemon.service` (el `.service` que instala el paquete) trae `-E`/`--log-stderr` fijo en su `ExecStart` — ese flag hace que RTPEngine mande todo a stderr **en vez de** syslog, sin importar `log-facility` en `rtpengine.conf`. Confirmado con `rtpengine --help | grep -A2 log-stderr`.
- **Bug relacionado encontrado de paso**: el override de systemd para límites de RTPEngine (`LimitNOFILE`, `LimitMEMLOCK`, `AmbientCapabilities` — de v2.0) apuntaba a `/etc/systemd/system/rtpengine.service.d/`, pero la unidad real es `rtpengine-daemon.service` — ese directorio nunca coincidió con la unidad real, así que **ese override nunca se aplicó desde que se agregó**, sin que nadie lo notara.
- Fix en `deploy.sh` (ambos flujos): override reescrito a `rtpengine-daemon.service.d/`, con los mismos límites de siempre + `ExecStart=` vaciado y redefinido sin `-E` (mismos argumentos que trae el paquete). Aviso explícito de que hace falta `systemctl restart rtpengine` a mano para que tome efecto — mismo criterio de siempre con RTPEngine.
- **De paso, validado en producción que el módulo kernel `xt_RTPENGINE` sí funciona**: `dkms status` mostraba el módulo ya compilado para el kernel corriendo (`6.1.0-49-amd64: installed`) — la nota vieja en `CLAUDE.md` ("no disponible para este kernel") estaba desactualizada, nunca se había cargado con `modprobe`. Tras cargarlo y reiniciar RTPEngine, `rtpengine-ctl list totals` mostró paquetes relayados en modo kernel (no solo userspace) — funcionando. La mayoría de los streams siguen en modo userspace por la duración corta de las llamadas de este SBC (~26s promedio): RTPEngine necesita un breve período para "aprender" el endpoint real (NAT) antes de migrar un stream al kernel, y muchas llamadas terminan antes de eso — es comportamiento esperado, no un problema. `ExecStartPre=rtpengine-iptables-setup` ya configura las reglas de firewall necesarias automáticamente — no hizo falta tocar `nftables.conf`.

## v2.24.13 — 2026-07-06

### Logs de RTPEngine separados de Kamailio + rotación diaria

El usuario pidió que los logs de RTPEngine se guarden y roten como los de Kamailio (solo ver el día actual). Al revisar, `rtpengine.conf` ya tenía `log-facility = local1`... en realidad tenía `local0` — **la misma facility que usa Kamailio** (`kamailio.cfg.j2: log_facility=LOG_LOCAL0`), así que ambos ya se estaban mezclando en el mismo `/var/log/kamailio.log` sin que nadie lo hubiera notado.

- `rtpengine.conf`: `log-facility` cambiado de `local0` → `local1` para dejar de colisionar con Kamailio. **No se reinicia solo** (mismo criterio que el resto de este archivo — cortaría audio de llamadas en curso): hace falta `systemctl restart rtpengine` a mano, en ventana de mantenimiento.
- `deploy.sh` (ambos flujos, update y fresh/upgrade): nuevo `/etc/rsyslog.d/41-rtpengine.conf` (facility LOCAL1 → `/var/log/rtpengine.log`) + `/etc/logrotate.d/rtpengine` (`daily`, `rotate 1`, igual que Kamailio) — mismo esquema exacto que ya existía para Kamailio, sin inventar uno nuevo.
- Aviso explícito al terminar el deploy recordando que hace falta el restart manual de RTPEngine para que el cambio de facility tome efecto.

## v2.24.12 — 2026-07-06

### Super admin — el admin primario no puede ser eliminado/desactivado por otros

Surge directo de la revisión de permisos de la sesión: el módulo de usuarios admin era un modelo plano (cualquier admin podía desactivar o resetear la contraseña de cualquier otro, incluido el admin original). El usuario pidió que el admin primario (el creado en la instalación) quede protegido del resto.

- `users.is_superadmin` (nueva columna, `TINYINT(1) DEFAULT 0`) — solo la marca el admin creado en la instalación (`db/seed.sql`, fresh install) o, en instalaciones existentes, una migración idempotente en `deploy.sh` que marca al admin de menor `id` **solo si todavía no hay ningún superadmin** (no se re-ejecuta en cada deploy).
- `backend/routers/admin_users.py`: `PUT /{uid}/active` rechaza desactivar a un superadmin (sin importar quién lo pida — se suma a la regla ya existente de que nadie puede desactivarse a sí mismo). `PUT /{uid}/password` rechaza resetear la contraseña de un superadmin salvo que sea el propio superadmin cambiando la suya — dejar esa puerta abierta hubiera anulado la protección (cualquier admin podría haber tomado la cuenta reseteando su clave).
- UI (`/users`): badge "Super admin" junto al nombre; botones "Desactivar" y "Contraseña" deshabilitados en esa fila para cualquiera que no sea el propio superadmin.
- **Cuidado al escribir la migración SQL**: la primera versión usaba una subquery en el `WHERE` del `UPDATE` que apuntaba a la misma tabla `users` que se está actualizando — MySQL/MariaDB puede rechazar eso (error 1093, "can't specify target table for update in FROM clause"). Reescrita para que ambas subqueries (buscar el admin más antiguo y contar superadmins existentes) vivan dentro de una única tabla derivada materializada antes del `UPDATE`, que es el patrón que sí está soportado.

## v2.24.11 — 2026-07-06

### Optimización del mini-Homer tras revisión a pedido del usuario

Repaso puntual de `hep_listener.py` buscando margen de mejora real, no reescritura — el diseño de fondo (batch insert, aislamiento SIP/RTCP, tope de cola) ya estaba bien para el volumen actual. Tres hallazgos concretos, ninguno toca Kamailio/RTPEngine/nftables:

- **Buffer de recepción UDP sin ajustar**: `create_datagram_endpoint` usaba el buffer default del SO. En una ráfaga (varias llamadas colgando/iniciando a la vez) el kernel puede descartar paquetes **antes** de que Python los vea — invisible para las colas internas porque el paquete ya se perdió antes de llegar ahí. Ahora el socket se crea a mano con `SO_RCVBUF` pedido a 8 MiB (el kernel lo recorta solo si `net.core.rmem_max` del host es menor — no falla, solo pide de menos; el valor real negociado queda logueado al arrancar el servicio).
- **Punto ciego de descartes de kernel**: no había ninguna forma de saber si esto ya estaba pasando en producción. Nuevo `_read_kernel_udp_drops()` lee la columna `drops` de `/proc/net/udp` para nuestro puerto y lo suma a `hep_stats.json` / card del Dashboard como "Descartes de kernel" — ahora si el buffer se queda corto en un pico real, se ve.
- **Race condition latente en `_get_pool()`**: sin lock, dos tareas llamando a `_get_pool()` al mismo tiempo antes de que existiera el pool podían crear dos pools y perder uno (conexiones huérfanas). Casi nunca se daba en la práctica (solo `_cleanup_loop` llega ahí de inmediato al arrancar, las otras dos tareas esperan 200ms), pero se blindó con `asyncio.Lock` + doble chequeo — patrón estándar, sin costo.
- Nota aparte (no se tocó): `INSERT LOW_PRIORITY` en el insert de `sip_traces` no hace nada porque la tabla es InnoDB — ese hint solo aplica a MyISAM. No hace daño, pero tampoco cumple lo que sugiere el nombre.

## v2.24.10 — 2026-07-06

### Visibilidad de capacidad del mini-Homer (colas SIP/RTCP)

Sigue directo del punto 1 de la conversación sobre si `hep_listener.py` aguanta el volumen real de llamadas (el cliente reportó ~115K llamadas/día). En vez de reescribirlo a ciegas, primero visibilidad real:

- `hep_listener.py`: nuevo `_stats_loop()` que escribe `/var/lib/voxikam/hep_stats.json` cada 5s con longitud de cola SIP/RTCP, total descartados por el tope `_MAX_QUEUE` (agregado en v2.24.9), y duración/tamaño del último flush a la BD de cada una.
- **Bug encontrado antes de que llegara a producción**: `/var/lib/voxikam` lo crea `cron_dlg_stats.py` corriendo como root (cron), quedando `root:root`. `voxikam-hep.service` corre como usuario `voxikam` sin permiso de escritura ahí — el nuevo `hep_stats.json` nunca se hubiera creado, fallando en silencio (capturado por el `except Exception` genérico y solo logueado). Fix en `deploy.sh`: `chown voxikam:voxikam /var/lib/voxikam` agregado en los dos flujos (`--update` rápido y fresh/upgrade), así root sigue pudiendo escribir `live_snapshot.json` ahí (root escribe en cualquier directorio sin importar el dueño) y voxikam gana permiso para `hep_stats.json`.
- Nuevo endpoint `GET /api/admin/hep-stats` (`backend/routers/hep_stats.py`) — mismo patrón que `live.py`: lee el JSON, marca `available=false` si el archivo tiene más de 30s (el proceso no está actualizando).
- Dashboard: nueva card "Cola HEP (mini-Homer)" con cola SIP/RTCP (coloreada si se acerca al tope), descartados totales, y tiempo del último flush — mismo lugar de donde salió la pregunta de capacidad, para no tener que adivinar la próxima vez.

## v2.24.9 — 2026-07-06

### Nuevo: Calidad de medio (RTP) por CDR — sin tocar Kamailio

- Retoma el ítem #34 del roadmap (diferido originalmente porque requería modificar el manejo de BYE en `kamailio.cfg.j2`) con una vía más segura: RTPEngine tiene soporte nativo para mandar sus estadísticas RTCP (jitter, % de pérdida) vía HEP/homer, correlacionadas por Call-ID — sin tocar Kamailio para nada.
- `rtpengine.conf`: `homer = 127.0.0.1:9060` apuntando al mismo puerto que ya usa `voxikam-hep.service` para SIP. **No se reinicia RTPEngine automáticamente** — deploy.sh nunca lo hace por su cuenta (cortaría audio de llamadas activas) — hace falta `systemctl restart rtpengine` a mano para que tome efecto.
- `backend/hep_listener.py` ahora entiende `proto_type=5` (RTCP-JSON) además de SIP — con su propio try/except aislado, a propósito, para que un bug en el parseo nuevo nunca pueda afectar la captura de Trazas SIP que ya está probada en producción. Se decidió un solo proceso (no un segundo mini-Homer) para no sumar carga.
- Nueva tabla `call_media_stats` (peor jitter/% pérdida por llamada, no promedio) y columna "Calidad" en CDRs (badge verde/amarillo/rojo). No hay MOS — a propósito no se inventa una aproximación, solo se muestran los números reales que manda RTPEngine.
- **A pedido del usuario** ("¿aguanta grandes cantidades?"): ninguna de las dos colas de `hep_listener.py` (ni la de SIP que ya existía, ni la nueva de RTCP) tenía un tope — si la DB se atrasara por cualquier motivo, crecían sin límite hasta poder reventar la memoria del proceso. Agregado un tope (`_MAX_QUEUE=20000`) — al llegar ahí, se descartan paquetes nuevos con un log de advertencia en vez de crecer sin control. El proceso se recupera solo apenas la DB vuelve a responder.

## v2.24.8 — 2026-07-06

### Fix crítico: snapshot de Kamailio roto borraba `active_calls` entera

Reportado por el usuario en producción: el panel Live mostraba 0 llamadas contestadas/timbrando arriba, pero la tabla de abajo mostraba 20+ llamadas reales — y el gráfico "Llamadas por minuto" del Dashboard se aplanaba en cero después de cierto punto, sin relación con tener o no la pestaña abierta (coincidencia de horario, no causa).

**Causa raíz:** `cron_dlg_stats.py` (snapshot de Kamailio cada 10s en `/var/lib/voxikam/live_snapshot.json`) escribía un snapshot con todo en cero cuando `kamcmd dlg.briefing` fallaba por cualquier motivo, indistinguible de "no hay llamadas activas de verdad". Eso rompía dos cosas río abajo:
- `cron_timeseries.py` lee ese mismo archivo — con `resumen_por_prefijo` vacío, dejaba de guardar filas para el gráfico por minuto (de ahí el aplanado).
- **Un bug más serio, encontrado en el camino**: `GET /admin/live` hacía una limpieza de "llamadas zombie" en `active_calls` confiando en el número `ongoing` del snapshot. Con `ongoing=0` (por el snapshot roto) y llamadas reales en la tabla, el `LIMIT 0` de la query de limpieza hacía que **se borrara `active_calls` completa**, no solo zombies — cada vez que se abría el panel Live o el Dashboard mientras el snapshot estaba roto.

**Fix:**
- `cron_dlg_stats.py`: si falla la captura, ya NO pisa el snapshot bueno anterior con ceros — lo deja intacto y solo loguea el error.
- `live.py`: nueva función `_snapshot_is_fresh()` que compara la antigüedad real del snapshot (>90s = no confiable) en vez de `bool(snap)` (que era `True` con solo que el archivo existiera, sin importar qué tan viejo). La limpieza de zombies ahora **solo corre si el snapshot es reciente** — nunca más basada en un número que podría estar roto.
- Panel Live y Dashboard: banner de advertencia visible cuando el snapshot no es confiable, en vez de mostrar números en cero sin ninguna señal de que algo está mal.

**Encontrado en la revisión posterior (pedida explícitamente antes de desplegar):**
- `cron_dlg_stats.py` nunca mataba `kamcmd`/`awk` si se colgaban (`communicate(timeout=10)` lanza excepción pero deja los procesos vivos) — si los cuelgues de `kamcmd` fueran la causa real de la falla, esto habría ido acumulando procesos zombie cada 10s, empeorando el problema con el tiempo. Agregado cleanup explícito (`kill()` + `wait()`) en un `finally`, corre pase lo que pase.
- El banner de aviso en Live tenía una sugerencia de diagnóstico incorrecta (`journalctl` de un servicio que no existe — `cron_dlg_stats.py` es un cron plano, no un unit de systemd). Corregido para apuntar al log real y al comando `kamcmd` exacto que se puede probar a mano.

## v2.24.7 — 2026-07-06

### Fix: botones sin cursor pointer en toda la app (no solo la sidebar)

- Reportado por el usuario: en la sidebar, Dashboard/Live mostraban la "manito" al pasar el mouse pero los headers de grupo (Reportes, Sistema, etc.) no. Causa raíz: el preflight de Tailwind deja `cursor: default` en `<button>` a propósito — el botón de logout de la sidebar ya necesitaba `cursor-pointer` a mano desde antes, y cada botón nuevo de las ~15 páginas de esta sesión (toggles de Webhooks/Disconnect Policies/Traffic Sampling, botones de Áreas/Pricelists, etc.) heredaba el mismo problema salvo que alguien lo pusiera explícito.
- Agregada una regla global en `globals.css` (`button:not(:disabled), [role="button"]:not(:disabled) { cursor: pointer }`) en vez de parchar botón por botón — corrige la sidebar Y cualquier otro botón de la app de una sola vez.

## v2.24.6 — 2026-07-05

### Fix: Dashboard — gauges apretados/pisados y cron jobs poco claros

- Reportado por el usuario con captura: el sub-label de RAM ("2.14 / 7.8 GB") se pisaba visualmente con el tick de "100%" del gauge — el componente `Gauge` tenía la fila del sub-label y la fila de ticks a solo 4px de distancia. Rehecho el cálculo vertical del SVG: cada fila (valor, ticks, sub-label, nombre) tiene su propio espacio reservado, y el alto total del gauge se ajusta según si hay sub-label o no (antes CPU sin sub-label quedaba con un hueco vacío raro, y RAM con sub-label quedaba apretada — mismo alto fijo para contenido distinto).
- Agregado un tercer gauge de **Disco** (`GET /admin/system` ahora también devuelve `disk_percent`/`disk_used_gb`/`disk_total_gb` vía `psutil.disk_usage("/")`, y `load_avg` vía `os.getloadavg()`), a pedido del usuario tomando como referencia el panel de MagnusBilling.
- Red pasó de columnas apiladas a una tabla compacta de 3 columnas (interfaz / bajada / subida), una sola leyenda "acumulado desde boot" en vez de repetida.
- Cron jobs: agregado un resumen de conteo por estado arriba ("6 al día · 1 sin logs"), lista de una sola columna en vez de grid de 2-3 (evita truncar labels largos), y la antigüedad de cada job ahora usa el color de su estado en vez de gris parejo — antes era una pared de puntos+texto sin jerarquía.

## v2.24.5 — 2026-07-05

### Rediseño: Sidebar — responsive real + transición entre grupos pulida (vía /frontend-design)

- La sidebar no tenía NINGÚN soporte responsive — `ml-56` fijo en los layouts admin/cliente sin importar el viewport, así que en pantallas angostas tapaba casi todo el contenido (reportado con captura real de un viewport angosto). Ahora: sidebar de escritorio (`md+`) sin cambios de comportamiento; debajo de `md` se vuelve un drawer off-canvas con barra superior + hamburguesa, backdrop, y se cierra solo al navegar.
- "Se ve raro cambiando de submenú": el show/hide de cada grupo era instantáneo y un grupo colapsado con la página activa adentro no se distinguía de uno vacío. Nuevo tratamiento **"signal path"**: borde+tinte ámbar continuo de la cabecera del grupo a sus items cuando está abierto, punto (LED) en la cabecera que se prende si el grupo tiene la ruta activa aunque esté colapsado, y la altura anima (`grid-template-rows`) en vez de saltar de golpe. Reutiliza la metáfora "ámbar = aguja de VU-meter" del design system en vez de inventar un patrón nuevo.

## v2.24.4 — 2026-07-05

### Fix: `MEMORY=256` fantasma en deploy.sh (dato muerto, generaba falsa alarma)

- Reportado por el usuario tras un deploy en producción: el log mostraba `/etc/default/kamailio → MEMORY=256`, dando la impresión de que la memoria compartida de Kamailio seguía limitada a 256MB pese al autotune. Investigado con `systemctl cat kamailio`: el `ExecStart` real usa `-m $SHM_MEMORY -M $PKG_MEMORY`, variables que `autotune.sh` ya calculaba y aplicaba correctamente (`/etc/default/kamailio.d/voxikam-memory.conf`) — Kamailio nunca estuvo limitado a 256MB.
- `deploy.sh` escribía además un `MEMORY=256` fijo en `/etc/default/kamailio` en cada deploy — variable que el `ExecStart` real nunca lee, dato muerto sin ningún efecto, pero que confundía la lectura del log en cada actualización. Eliminado.
- Documentado en CLAUDE.md para que quede claro de una vez cuál variable manda.

## v2.24.3 — 2026-07-05

### Fix: config de correo movida a Sistema → Correo

- La API key de Resend y el remitente vivían embebidos en el panel de Alertas de balance, pero no son específicos de ese módulo — los usan también Disconnect Policies y el envío automático de facturas. Reportado por el usuario ("debería estar en otro menú"). Movidos a un panel propio, **Sistema → Correo** (`/api/admin/mail-config`).
- Alertas de balance conserva su config específica (email que recibe las alertas, reglas de umbral) y ahora solo enlaza al panel de correo en vez de duplicar el formulario.

### Nuevo: backfill de `prefix_matched` para el reporte de Áreas

- Detectado por el usuario en producción: el reporte de rentabilidad por área mostraba TODO el histórico agrupado en "Sin área", incluso teniendo áreas bien configuradas. Causa: `prefix_matched` solo se llena correctamente desde v2.13.0 — todo lo anterior quedó con el valor viejo (no confiable) o NULL.
- Botón "Recalcular histórico" en el panel Áreas (o `scripts/backfill_prefix_matched.py --yes` manual) recalcula `prefix_matched` para todo el histórico de CDRs contestados, usando la definición de prefijos actual. Solo toca esa columna — nunca `buycost`/`sessionbill`/`lucro`, no afecta nada ya facturado. Corre en background vía `subprocess.Popen`, igual que el resto de acciones "pesadas" disparadas desde el panel.
- El panel Áreas ahora avisa cuántos CDRs siguen sin `prefix_matched` (`GET /admin/areas/backfill-status`) para que sea obvio cuándo vale la pena correrlo.

## v2.24.2 — 2026-07-05

### Fix: Dashboard — cron jobs apretujado contra CPU/RAM

- La fila de cron jobs vivía pegada al fondo de la misma tarjeta de CPU/RAM/Red, con `flex-wrap` — con 7 jobs y etiquetas largas ("Sync externa de CDRs (00:15)") se veía amontonado y rompía feo en pantallas angostas (reportado por el usuario con captura real).
- Ahora es su propia tarjeta, en grid (1/2/3 columnas según ancho), cada job en su propia fila con label truncado y la antigüedad alineada a la derecha — sin wrapping impredecible. La tarjeta de CPU/RAM/Red vuelve a su layout original, sin la sección pegada abajo.

## v2.24.1 — 2026-07-05

### Fix: sidebar — acordeón real, no grupos independientes

- La v2.24.0 persistía cada grupo abierto/cerrado por separado en `localStorage` — se iban acumulando grupos abiertos al navegar entre secciones distintas y dejaba de ser claro en qué sección estabas parado (reportado por el usuario con capturas reales).
- Ahora es un acordeón: un solo grupo abierto a la vez, sincronizado con la ruta activa en cada navegación (`useEffect` sobre `path`). Ya no depende de `localStorage`.

## v2.24.0 — 2026-07-05

### Reorganización: sidebar en grupos colapsables

- La sidebar admin creció de 4 a 22 items en el curso de esta sesión — dejó de ser navegable como lista plana. Dashboard/Live quedan siempre arriba; el resto se agrupó en Clientes/Red/Tarifas/Tráfico/Reportes/Alertas/Sistema, colapsables, con el estado guardado en localStorage.
- El grupo con la ruta activa siempre se abre solo, aunque el usuario lo hubiera colapsado antes.
- Cierra la tanda de items "sin riesgo" del roadmap de esta sesión (v2.9.0 → v2.24.0). Quedan pendientes de confirmación explícita los que tocan Kamailio/nftables en vivo: Auth Logs (#10), Static routes (#21), Calidad de medio real/RTP (#34), y todo lo previamente clasificado en rojo (calllimit/cpslimit enforcement, Gateway Throttling, Numberlists en tiempo real, Routeset Discriminators, separar cdrs/sip_traces en DB propia, API REST pública, Codec Groups, LNP, STIR/SHAKEN, pasarela de pago, reventa multinivel, antifraude).

## v2.23.0 — 2026-07-05

### Nuevo: Logic log (comentarios internos)

- Sección "Notas internas" embebida en el detalle de Cliente y de Carrier — comentarios de texto libre, con quién y cuándo, que se van acumulando (no un campo que se pisa en cada edición como el `notes` que ya existía en Clientes).
- Componente compartido (`EntityComments.tsx`) reutilizado en ambas páginas de detalle.

## v2.22.0 — 2026-07-05

### Nuevo: Envío automático de factura por email

- Toggle en **Facturas** ("Enviar por correo automáticamente al generar", OFF por defecto): al generar una factura, si está activo, se envía por correo con el PDF adjunto usando la misma configuración de Resend de Alertas.
- Botón manual "Enviar"/"Reenviar" en cada factura, funciona sin importar el estado del toggle — para reenvíos o para mandar facturas viejas que nunca se enviaron.
- Un fallo de envío (sin API key, Resend caído, cliente sin email) nunca revierte ni bloquea la generación de la factura — solo se loguea. `invoices.emailed_at` (columna nueva) registra el último envío exitoso.
- `mailer.py::send_email()` ahora soporta adjuntos (base64) — es la primera vez que se usa esa capacidad, hasta ahora todos los correos (alertas de balance, disconnect policies) eran solo HTML.

## v2.21.0 — 2026-07-05

### Nuevo: Import/export CSV de tarifas

- Panel **Pricelists**: importar un CSV (`prefix, rateinitial, connectcharge, billingblock, minimal_time_charge`) carga las filas dentro de un draft — nunca directo a `rates` — así que el mismo review de diff/publicar de v2.20.0 aplica también a cambios masivos por CSV. Reporta línea por línea qué prefijos no existían (no crea prefijos nuevos automáticamente).
- Exportar tarifas en vivo de un plan a CSV (de solo lectura) como punto de partida para editar y reimportar como draft nuevo. Exportar el contenido de un draft en cualquier momento.

## v2.20.0 — 2026-07-05

### Nuevo: Pricelists (borrador/aprobación de tarifas)

- Panel **Pricelists**: crea un draft de tarifas, cargale prefijos con su nuevo precio, revisá el % de cambio vs la tarifa actual (rojo si sube, verde si baja, "nuevo" si el prefijo no tenía tarifa todavía) y recién ahí publicá — o descartá el draft sin tocar nada.
- El billing worker y el ingest de CDR nunca leen un draft, solo `rates` — un draft en progreso es 100% invisible para la facturación en curso. Publicar es una sola transacción con `ON DUPLICATE KEY UPDATE`.
- No reemplaza la edición directa en Tarifas — es una vía adicional para cambios grandes donde vale la pena revisar antes de aplicar.

## v2.19.0 — 2026-07-05

### Nuevo: Traffic Sampling (retención configurable de trazas SIP)

- Panel **Traffic Sampling**: la ventana de retención de `sip_traces` (antes fija en "solo hoy") ahora se configura desde el panel, en horas, con presets (1h/6h/1d/3d/7d) o un valor exacto.
- De paso se corrigió un bug real: `SIP_TRACE_DAYS` en `.env` nunca estuvo conectado a la limpieza — solo aparecía en un mensaje de log. La retención real siempre fue "hoy" sin importar ese valor. Ahora `backend/hep_listener.py` lee la config desde la DB (con ese mismo env var como fallback), en caliente, sin reiniciar el servicio.
- `scripts/cron_partitions.py` usa el mismo setting para decidir cuántas particiones de día completo conservar antes de hacer `DROP PARTITION`.
- Alcance: es una ventana de retención sobre lo ya capturado, no reduce qué fracción de tráfico traza Kamailio en la captura misma (eso tocaría el `.cfg` del SBC — mismo criterio de riesgo que otros cambios de esta tanda que se dejaron fuera).

## v2.18.0 — 2026-07-05

### Nuevo: Routing Simulation

- Panel **Routing Sim**: dado un cliente y un destino, muestra qué tarifa se le cobraría y por qué carrier saldría la llamada (con el orden de failover completo, no solo el primero) — sin originar ninguna llamada real.
- Replica exactamente el longest-prefix-match que ya usa el ingest de CDRs y el orden de prioridad que ya usa `gen_dispatcher.py`, así que el resultado coincide con lo que pasaría en producción. Muestra carriers inactivos también, para explicar por qué no se usarían, y avisa si no hay ningún carrier activo asignado.

## v2.17.0 — 2026-07-05

### Nuevo: Disconnect Policies

- Panel **Disconnect Policies**: alerta cuando un cliente cruza un % de un tipo de corte (503 sin carriers, 486 ocupado, 404 no encontrado, etc.) dentro de una hora — reutiliza los datos que ya agrega `cron_quality.py` en `traffic_quality_hourly`, no una taxonomía nueva.
- Mismo criterio que las alertas de balance: **solo informa por correo/webhook, nunca suspende ni bloquea nada**. Umbral mínimo de llamadas configurable por política para evitar falsos positivos con poco volumen.
- Corre dentro del proceso del backend (loop propio cada 5 min, no un cron aparte) para reusar el envío de correo/webhooks sin duplicar lógica. Dedup por hora vía `UNIQUE KEY` en vez de estado en memoria.
- Nuevo evento de webhook: `customer.disconnect_policy_breach`.

## v2.16.0 — 2026-07-05

### Nuevo: Webhooks

- Panel **Webhooks**: suscribe una URL a `cdr.created`, `customer.balance_alert` o `customer.status_changed`. Firma HMAC-SHA256 en `X-VoxiKam-Signature`, secret visible una sola vez (al crear o al rotarlo), historial de entregas por webhook (status HTTP, intento, éxito/error).
- Un solo reintento inmediato si falla — a propósito no es un bus de eventos con colas ni backoff exponencial, es una notificación best-effort.
- El envío nunca bloquea el request que lo dispara: el ingest de CDR (que llama Kamailio en cada llamada colgada) lo dispara vía `BackgroundTasks`, y la evaluación de alertas de balance (dentro del loop del billing worker) vía `asyncio.create_task()` — un webhook lento o caído no puede frenar ninguno de los dos.

## v2.15.0 — 2026-07-05

### Nuevo: Sincronización externa de CDRs

- Panel **Sync externa**: copia `cdrs` de forma incremental hacia una base de datos externa (MySQL/MariaDB, PostgreSQL o SQL Server) — pensado para darle a BI/reportería acceso a los datos sin tocar la DB de producción. Deshabilitada por defecto, un solo destino a la vez.
- Muestra los permisos que necesita el usuario de destino según el engine elegido antes de guardar nada, con botón de "Probar conexión" separado de "Sincronizar ahora".
- Corre de noche (00:15) vía `scripts/cron_external_sync.py` o a pedido desde el panel — solo lee `cdrs` local con un cursor por `id` en batches de 500, nunca escribe/borra nada acá. Historial de corridas visible en el mismo panel.
- SQL Server queda soportado en el código pero su dependencia (`pyodbc`) es opcional a propósito — requiere unixODBC + driver de Microsoft a nivel de sistema operativo, y agregarlo como dependencia dura habría roto `pip install` en cualquier servidor sin esos paquetes.
- De paso: se descartó **Auth Logs** (intentos SIP rechazados) de la tanda "sin riesgo" — investigar cómo se maneja la autorización reveló que las IPs no autorizadas se descartan en `nftables` (`policy drop`, sin logging) antes de llegar a Kamailio, así que verlo requiere tocar el firewall del SBC en vivo, no solo el panel. Queda pendiente de confirmación explícita, igual que los demás cambios que tocan la infraestructura del SBC.

## v2.14.0 — 2026-07-05

### Nuevo: Salud de cron jobs en el Dashboard

- Fila de estado (ok/atrasado/error/log ausente) para cada cron job (resumen nocturno, particiones, timeseries, calidad ASR, sync firewall, sync dispatcher), debajo de CPU/RAM/Red en el Dashboard.
- No ejecuta nada — lee `mtime` + las últimas líneas de los logs que los scripts ya escriben en `logs/*.log`. `cron_dlg_stats.py` queda fuera del panel porque corre como root y escribe en un directorio que el backend no puede leer.

## v2.13.0 — 2026-07-05

### Nuevo: Áreas + rentabilidad por área

- Panel **Áreas**: formaliza `prefixes.group_name` (hasta ahora un texto suelto usado en Tarifas/Carriers) en una tabla propia — crear, describir y **renombrar sin romper nada** (el rename cascadea a `prefixes.group_name` en la misma transacción). Bloquea el borrado si el área todavía tiene prefijos asignados.
- Nuevo reporte de rentabilidad por área (llamadas, minutos, compra, venta, margen) para un rango de fechas — agrupa por el prefijo real que ganó la tarifa en cada CDR, no por un `LIKE` recalculado.
- Fix de paso: `cdrs.prefix_matched` se llenaba con un campo del payload de Kamailio que no necesariamente correspondía a la tarifa aplicada. Ahora se llena con el prefijo que realmente ganó el longest-prefix-match en `ingest_cdr()` — la misma fuente que ya calculaba `sessionbill`. El reporte de Áreas depende de que este campo sea confiable.

## v2.12.0 — 2026-07-04

### Nuevo: `cdrs`/`sip_traces` particionadas por fecha

- `cdrs` particionada por mes, `sip_traces` por día — RANGE sobre `TO_DAYS(fecha)`. `scripts/cron_partitions.py` (cron diario) crea las próximas particiones y, en `sip_traces`, elimina con `DROP PARTITION` las de días pasados en vez del `DELETE` fila por fila que usaba hasta ahora — mismo criterio de retención ("solo hoy"), mucho más barato en una tabla de alto volumen.
- Instalaciones existentes (de antes de esta versión) no se migran solas: un `ALTER TABLE ... PARTITION BY` reconstruye la tabla completa y puede bloquear escrituras minutos u horas en una tabla con tráfico real. Queda como paso manual — `scripts/migrate_partitioning.py` (modo diagnóstico por defecto, `--yes` para aplicar) — a correr en ventana de mantenimiento.
- `cdrs`/`sip_traces` pasan de `PRIMARY KEY (id)` a `PRIMARY KEY (id, fecha)` — requisito de MySQL para particionar por esa columna. El billing worker (`backend/main.py`) ahora incluye `start_ts` en el UPDATE de cada CDR tarifado para aprovechar partition pruning.

## v2.11.0 — 2026-07-04

### Nuevo: Auditoría de config (`settings_history`)

- Selectiva a propósito, no un log de todo (ver `backend/audit.py`): cubre lo que afecta dinero, servicio o seguridad — estado/plan/límites de cliente, altas/bajas/cambios de carrier, reglas de firewall, reglas de alerta de balance, y todo lo que pasa con usuarios admin (creación, activar/desactivar, reset de contraseña).
- Panel nuevo: **Auditoría** — filtro por entidad, quién hizo el cambio, campo, antes/después. `changed_by` ahora es el nombre de una persona real gracias a v2.10.0 (usuarios admin), no una credencial compartida.
- No se auditan campos de bajo impacto (`notes`, nombres, etc.) — el criterio es "esto podría explicar una pérdida de plata o un corte de servicio si sale mal", no "todo lo que cambió".

## v2.10.0 — 2026-07-04

### Nuevo: Usuarios admin multi-persona

- La tabla `users` ya soportaba varios admins (`role` incluye `'admin'` desde siempre) — lo que faltaba era la pantalla. Antes, el único admin se creaba una vez en `deploy.sh` y no había forma de agregar, desactivar o ver quién más tiene acceso; todo el equipo compartía una sola cuenta.
- Panel nuevo: **Usuarios** — crear admins, resetear contraseña, activar/desactivar. Protegido contra desactivar la propia cuenta o al último admin activo que quede (server-side, no solo deshabilitado en el botón).
- Base necesaria para que la próxima entrada (auditoría de config) tenga sentido real: "quién cambió esto" ahora puede responder con una persona de verdad, no una credencial compartida.

## v2.9.0 — 2026-07-04

### Nuevo: Alertas de balance (prepago/postpago) + ledger de transacciones

- Primer módulo de la ronda de mejoras inspirada en Yeti Switch/ASTPP/MagnusBilling (ver roadmap de la sesión). Arranca por lo más fundacional: trazabilidad de balance y avisos tempranos, sin tocar Kamailio.
- **Ledger de transacciones** (`balance_transactions`): cada débito por CDR facturado y cada ajuste manual de balance queda registrado con el balance resultante — hoy no había forma de reconstruir "por qué" el saldo de un cliente es el que es, fuera de los CDRs sueltos.
- **`customers.billing_type`** (prepago/postpago, editable desde el detalle del cliente) — define cómo se evalúan las alertas de saldo:
  - Prepago: % de saldo restante respecto al último recargo (`last_topup_amount`, se actualiza solo con cualquier ajuste manual positivo).
  - Postpago: balance absoluto negativo.
- **`balance_alert_rules`**: reglas de alerta como tabla propia, no un valor fijo — cada una con su label, umbral y activo/inactivo independiente. Sembradas por defecto: prepago 30%/20%, postpago -1000/-3000 — todas editables y desactivables desde el panel, nada hardcodeado.
- **Sin auto-suspensión todavía, a propósito**: se detectó que clientes activos en producción ya operan con balance negativo (`credit_limit` nunca se enforzó, sigue en 0 por defecto) — activar una suspensión automática con la regla obvia habría cortado tráfico real sin aviso. Por ahora el sistema solo alerta; la suspensión automática queda pendiente hasta confirmar los `credit_limit` reales de cada cliente activo.
- **Panel nuevo:** *Alertas → Alerta consumo* — reglas con su toggle arriba, clientes cruzándolas ahora mismo abajo (calculado en vivo, no depende de si ya se mandó el correo).
- **`backend/mailer.py`**: envío de correo vía Resend, mismo proveedor y mecanismo que `otro proyecto interno`. **Configuración de correo (API key + remitente) desde el propio panel** — *Alertas → Configuración de correo* — no por `.env`; sin una API key cargada ahí, `send_email()` no intenta nada, solo loguea (nunca rompe el billing ni ninguna otra lógica). `.env` (`RESEND_API_KEY`/`ALERT_FROM_EMAIL`) queda como fallback opcional para quien prefiera configurarlo por archivo en vez del panel. El remitente por defecto sugerido es `no-reply@kpbtec.com` (ya verificado en Resend) — uno propio de VoxiKam requiere verificar ese dominio en la misma cuenta primero.
- Email de notificación (a quién le llega la alerta) configurable por separado en el mismo panel (`settings.alert_notify_email`), con fallback a `ADMIN_EMAIL`.

## v2.8.9 — 2026-07-03

### Fix: `deploy.sh` — el modo "Actualizar" nunca actualizaba el marcador de versión

- Tras correr `./deploy.sh` → "Actualizar" (la opción rápida/recomendada, sin tocar Kamailio), la próxima corrida seguía mostrando la versión vieja en "Versión instalada" y ofrecía "actualizar" de nuevo — a pesar de que código, deps, DB y frontend sí se habían actualizado correctamente.
- Causa: ese modo hace `exit 0` al final de su propio bloque, antes de llegar nunca a la sección que escribe `VERSION=` en `/etc/voxikam.conf` — esa sección solo corría para los modos `upgrade`/`fresh`/`reinstall`. Agregado el mismo `sed -i` que ya usa `upgrade`, justo antes del health-check del modo `update`.

### Fix: panel admin — no había forma de editar el email de un cliente

- El formulario de edición de `Clientes` no tenía ningún campo para `email` (solo Nombre, Empresa, Teléfono, CPS, Calls máx, Plan de tarifas, Estado, Notas) — aunque el backend sí lo acepta en el `PUT`. Como el formulario se inicializa con los datos actuales del cliente, cada guardado reenviaba el email viejo sin cambios, dando la impresión de que el campo estaba bloqueado. Agregado el input de email tanto en la vista de edición como en el detalle de solo lectura.

### Rediseño: `docs/index.html` — landing alineada al Voxi Design System

- La landing pública seguía con el tema claro/azul genérico original (Inter, fondo blanco, `#2563eb`) mientras el producto real es 100% oscuro con acento ámbar desde v2.5 — quien entraba veía un producto visualmente distinto al que después usa. Reescrita completa: tokens ink/superficie/ámbar, Manrope + IBM Plex Mono, íconos de línea (mismo lenguaje que `lucide-react` en el panel real) en vez de emoji.
- Hero rediseñado: en vez de tarjetas de stats genéricas, muestra una ladder SIP animada (INVITE → 100 Trying → 183 → 200 OK → BYE, con "cortó: CLIENTE") — el mismo lenguaje visual del ladder diagram real de Trazas SIP, como pieza central en vez de una ilustración genérica.
- Contenido puesto al día: instalador (`install.sh` → `deploy.sh`), versión (v2.4 → v2.8.9), e historial de releases curado con el contenido real de v2.5 a v2.8.9 (agrupado en tarjetas con sustancia en vez de un dump de las ~26 entradas del CHANGELOG).

### Fix: `kamailio.cfg.j2` — el BYE (y todo mensaje in-dialog) nunca quedaba en `sip_traces`

- Confirmado exportando una llamada a `.pcap` y abriéndola en Wireshark: el flow mostraba el setup completo (100 Trying, INVITE, 183, 200 OK) pero cortaba justo ahí — nunca aparecía el BYE, dando a entender que la llamada no colgaba.
- Causa: `sip_trace()` (el que manda cada mensaje a `hep_listener.py` vía HEP) solo se llamaba una vez, en el INVITE inicial (`route[OUTBOUND_TO_CARRIER]` / `route[INBOUND_TO_ASTERISK]`). El `setflag(28)` de ahí no persiste a los siguientes mensajes del mismo diálogo — BYE, re-INVITE, UPDATE y el ACK final del `has_totag()` nunca pasaban por `sip_trace()`, así que jamás se guardaban en `sip_traces` sin importar que el mensaje sí llegara al SBC (el BYE siempre transita por Kamailio por el Record-Route, así que un `sngrep` en la consola del server sí lo mostraba — el problema era solo de captura/almacenamiento, no de red).
- Fix: agregado `setflag(28); sip_trace();` también dentro del bloque `if (loose_route())` (cubre BYE/re-INVITE/UPDATE/ACK in-dialog) y en el bloque `if (is_method("CANCEL"))`. Requiere `--upgrade` (reinicia Kamailio) para tomar efecto — no es tuneable en caliente vía `kamcmd`.

### Fix: `nft.log`/`dispatcher.log` sin timestamp — imposible correlacionar con un incidente

- `gen_nftables.py` y `gen_dispatcher.py` (cron cada 5 min) solo hacían `print("  ✓ ...")` sin ninguna marca de tiempo — el log en disco era una pared idéntica de líneas repetidas, sin forma de saber cuándo corrió cada ciclo. Agregada una línea de cabecera con timestamp por corrida (mismo formato que ya usan `cron_summary.py`/`cron_quality.py`/`cron_timeseries.py`) y manejo explícito de excepciones (antes un fallo de DB en `gen_nftables.py` podía cortar la ejecución sin dejar ningún rastro de error, solo silencio).
- Investigado a raíz de un reporte de asesores de Vicidial ("a veces se corta la llamada conversando") — se sospechó del reload de firewall cada 5 min, pero se confirmó que **no es la causa**: `nftables.conf` tiene `ct state established,related accept` antes de las listas dinámicas de IPs, así que una conexión ya trackeada por conntrack sigue aceptada aunque su IP salga temporalmente del `customers.nft` regenerado — el reload de `nft -f` es una transacción atómica a nivel de kernel, sin ventana de paquetes perdidos. Mismo razonamiento aplica a `kamcmd dispatcher.reload`: solo afecta la selección de destino de llamadas *nuevas* (`ds_select_dst()`), no diálogos ya establecidos. Con el timestamp ahora sí se puede correlacionar contra la hora real de un corte reportado si se necesita seguir investigando.

### Feature: descargar traza SIP como .pcap (Trazas SIP → admin)

- El ladder diagram en pantalla no siempre deja claro quién originó cada mensaje (p.ej. quién colgó realmente: BYE del cliente vs. BYE del carrier). Nuevo endpoint `GET /api/admin/traces/pcap?call_id=...` reconstruye un `.pcap` (Ethernet/IPv4/UDP sintéticos, con las IPs/puertos/timestamp reales capturados por HEP y el mensaje SIP crudo tal cual) para abrir en Wireshark. Botón "Descargar PCAP" en la vista de llamada seleccionada de `/traces`.

### Fix: portal cliente — gráfico "Mis llamadas" mostraba "Sin nombre" en la leyenda

- `GET /timeseries/my` agrupaba las series por `carrier_name`, un detalle interno de routing del SBC que el cliente no debe ver — y que además suele venir `NULL` para sus propios CDRs, cayendo en el fallback `"Sin nombre"`. Ahora agrupa por el nombre del propio cliente.

### Fix/cleanup: portal cliente — overview redundante y selector de mes sin dropdown

- Quitada la tabla "llamadas activas ahora" de `/my/overview` — duplicaba la info de "últimas llamadas" sin aportar nada distinto en la práctica diaria del cliente. "Últimas llamadas hoy" ahora está explícitamente acotada a los 10 registros más recientes (antes 5, sin indicarlo en el título).
- En `/my/reports`, el `<input type="month">` nativo no abría un desplegable utilizable en todos los navegadores (solo cambiaba con flechas). Reemplazado por dos `<select>` (mes + año) con el estilo propio del portal.

### Fix: navegar a Trazas SIP desde CDRs demoraba ~15s en mostrar el diálogo (a veces nunca lo mostraba)

- Causa real: `_classify_query()` en `traces.py` excluía cualquier query con `@` de la rama de exact-match sobre `call_id`, asumiendo que un Call-ID nunca tenía `@` — pero el Call-ID SIP real es casi siempre `<random>@<host>` (es justo lo que pasa el link "SIP" de `/cdrs`). Como resultado, **toda** navegación desde un CDR caía al fallback `LIKE '%q%'` bilateral sobre `call_id`/`from_uri`/`to_uri`, forzando un full scan de `sip_traces` del día completo — el origen real de la demora. Ahora el exact-match acepta `@`.
- Bug aparte en el frontend: al llegar con `?call_id=...` desde `/cdrs`, el efecto de auto-carga nunca hacía `setSelected()` — el mensaje SIP se cargaba en segundo plano pero el panel derecho se quedaba fijo en "Selecciona una llamada para ver el diálogo SIP" indefinidamente, sin importar cuánto se esperara. Corregido.

## v2.8.8 — 2026-07-02

### Fix: `failure_route[CARRIER_FAILOVER]` decía "FAILOVER" incluso cuando nunca iba a reintentar

- El log `xlog("L_WARN", "... FAILOVER carrier: ... falló ...")` se disparaba **incondicionalmente** para cualquier 5xx/408, antes de siquiera revisar si `ds_next_dst()` iba a encontrar otro carrier. Con un solo carrier por grupo (el caso real en producción hoy), esto hacía parecer que el sistema "intentaba un failover" en cada llamada fallida, cuando en realidad nunca llegaba a intentar nada — `ds_next_dst()` siempre devolvía `false` de inmediato.
- Fix: el mensaje con la palabra "FAILOVER" ahora solo se loguea **después** de confirmar que sí hay otro carrier al cual saltar (o sea, cuando de verdad va a reintentar). Si no hay otro carrier, el mensaje pasa a ser "Llamada fallida: ... sin carrier de respaldo" — sin ninguna palabra que sugiera un reintento que no ocurrió.
- Sin cambios de comportamiento real: la limpieza de RTPEngine (`rtpengine_delete()`) y la respuesta 503 a Asterisk siguen ocurriendo exactamente igual en ambos casos — esto es puramente una corrección de log/diagnóstico, no toca el enrutamiento de llamadas.

## v2.8.7 — 2026-07-02

### Fix: orden de arranque Kamailio/MariaDB tras reboot completo + log de FAILOVER carrier con severidad exagerada

- Confirmado en `vd1sbc2` tras un reboot completo del servidor: Kamailio arrancó antes que MariaDB estuviera lista, y varios workers (módulo `sqlops`) fallaron al conectar (`Can't connect to server on '127.0.0.1'`, `init_child failed`) — incluyendo los procesos `timer`/`secondary timer`, que corren el sondeo periódico de carriers del módulo `dispatcher`. El override systemd de Kamailio (`kamailio.service.d/voxikam-limits.conf`) no tenía ninguna dependencia de orden con MariaDB.
- Fix: agregado `After=mariadb.service` + `Requires=mariadb.service` al override — garantiza que Kamailio nunca arranque antes de que MariaDB esté lista, en cualquier reboot futuro.
- Investigando el mismo incidente se confirmó que los carriers NO quedaron atascados (`kamcmd dispatcher.list` los mostraba `FLAGS: AP`, activos) — el verdadero disparador de `FAILOVER carrier: todos los carriers del grupo N fallaron` era tráfico normal de marcación masiva (503/408 puntuales mezclados con llamadas contestadas, esperable con un solo carrier por grupo sin redundancia). El problema real era el nivel de log: ese mensaje salía como `L_ERR` (alarma de sistema) para algo que es ruido operativo normal por diseño (una llamada agotando el único carrier disponible, no una caída). Bajado a `L_WARN` con texto que ya no da a entender una caída total del sistema.

## v2.8.6 — 2026-07-02

### Fix: regresión crítica — `max-sessions=500` en `rtpengine.conf` seguía en el template, sin comentar

- Confirmado en `vd1sbc2` tras un `--upgrade`: `rtpp_function_call(): proxy replied with error: Unknown call-id` en los logs de Kamailio, con `rtpengine-ctl list numsessions` mostrando 471 sesiones activas — a 29 de tocar el cap de 500. Mismo síntoma exacto que el incidente documentado en `CLAUDE.md` ("El cap de 500 causó 2306 rechazos en 5.5 minutos").
- Causa: el template `rtpengine/rtpengine.conf` en el repo nunca tuvo `max-sessions` comentado — el fix del incidente original se aplicó a mano en el servidor en su momento, pero nunca se llevó al repo. Cualquier `--update`/`--upgrade` que reaplique `rtpengine.conf` desde el template (como el que disparó este hallazgo) pisa silenciosamente ese fix manual y reintroduce el cap.
- Fix: `max-sessions` comentado en el template, con nota explícita para que no se repita. **Esto no corrige servidores ya desplegados** — en cada uno hay que correr `sudo bash scripts/fix_rtpengine.sh` (ya existía, hecho para este incidente) o comentar la línea a mano y `systemctl restart rtpengine` (corta llamadas activas).

## v2.8.5 — 2026-07-02

### Fix: consistencia visual entre familia Voxi (VoxiKam/VoxiDet) — badge de versión solapaba el footer de marca

- El badge de versión del sidebar (`components/Sidebar.tsx`) era `position: fixed` anclado a la esquina inferior derecha del viewport — el mismo lugar exacto donde el footer de página (`(admin)/layout.tsx`, `(client)/layout.tsx`) ya mostraba "KPBTec · Knowledge, Protection & Business Technology". Confirmado por captura: el texto "KPBTec" quedaba tapado por el badge flotante. Mismo bug (mismo patrón `position:fixed`) también existía en VoxiDet (`.version-tag`), aunque ahí no era visible porque VoxiDet no tenía footer de marca con quien solaparse — hasta ahora.
- Fix: el badge de versión deja de ser `position:fixed` — ahora vive en línea, dentro del footer, junto al texto de KPBTec (ambos productos). Sin position:fixed no hay superposición posible.
- VoxiDet ahora también muestra el footer "VoxiDet · Voice Detection AI" / "KPBTec · Knowledge, Protection & Business Technology" en todas sus páginas (antes no existía ningún disclaimer de marca ahí — confirmado, cero menciones a KPBTec en todo el proyecto).
- `deploy.sh`: unificado el estilo de logs de instalación con VoxiDet — `[✓]/[·]/[⚠]/[✗]` en vez de `✓`/`⚠`/`✗` sin corchetes, separadores `── Sección ──` en vez de `══ Sección ══`, y los banners de apertura/resumen final (antes cajas `╔══╗` dibujadas a mano) simplificados al mismo estilo `━━━` de una línea que ya usaba VoxiDet. Se agregó atribución explícita "un desarrollo de KPBTec" en el banner de apertura y en el resumen final (antes solo estaba en un comentario del código fuente, invisible en la terminal).

## v2.8.4 — 2026-07-01

### Fix: sesiones RTPEngine huérfanas — el fix de v2.7.2 no cubría llamadas rechazadas (486/404/503, sin BYE ni CANCEL)

- Confirmado en `vd1sbc2` tras el reboot: el ratio diálogos-Kamailio vs sesiones-RTPEngine seguía subiendo (69→148 recién reiniciado, luego 209→500 con más tráfico) a pesar del fix de `rtpengine_delete()` en BYE/CANCEL de v2.7.2. Causa: ese fix solo cubría llamadas que llegan a contestarse y cuelgan (BYE) o que el llamante cancela antes de contestar (CANCEL) — pero una llamada **rechazada** (486 Busy, 404, o agotados los reintentos de failover con 503) nunca pasa por ninguno de los dos métodos, así que su sesión de RTPEngine (abierta en el INVITE inicial) nunca se liberaba, quedando huérfana hasta expirar sola por timeout interno — exactamente el mismo síntoma original, por una ruta distinta.
- Agregado `rtpengine_delete()` en 6 puntos más de `templates/kamailio.cfg.j2`: los dos `failure_route` (`CARRIER_FAILOVER`/`ASTERISK_FAILOVER`) — tanto cuando se agotan los reintentos de 5xx/408 como cuando la respuesta es un 4xx legítimo que no se reintenta — y los dos puntos de fallo inmediato por falta de destino (`ds_select_dst()` sin carriers/Asterisk disponibles), donde ya se había llamado `rtpengine_manage()` antes de responder 503.
- Además, red de seguridad en `event_route[dialog:failed]` — el módulo `dlg` puede terminar un diálogo por su propio timeout interno, no solo por una respuesta SIP puntual ya cubierta arriba. `rtpengine_delete()` es idempotente (llamarlo dos veces para el mismo call-id no hace nada la segunda vez), así que no hay riesgo de que se solape con las otras 8 llamadas.
- Con esto quedan cubiertos los tres caminos de fin de llamada: contestada y colgada (BYE), cancelada antes de contestar (CANCEL), y rechazada/fallida sin contestar (failure_route / sin destino / timeout del módulo dialog) — antes solo los dos primeros liberaban la sesión. Verificado punto por punto que cada `rtpengine_delete()` nuevo está en una rama que termina en `exit` o al final del bloque — ninguno se ejecuta antes de un reintento (`ds_next_dst()`), y balance de llaves/paréntesis del template confirmado (114/114, 325/325).

## v2.8.3 — 2026-07-01

### Fix crítico: migración la plataforma anterior instalaba en `/root/...` — servicios nunca arrancaban (`Permission denied` en CHDIR)

- Confirmado en producción (`vd1sbc2`): tras el fix de v2.8.2, la migración completó el schema pero `voxikam-backend`/`voxikam-frontend`/`voxikam-hep` quedaron en crash-loop con `Changing to the requested working directory failed: Permission denied`. Causa: sin un marcador previo de VoxiKam, `INSTALL_DIR` caía a `$SCRIPT_DIR` — en este caso `/root/voxikam` (el usuario sube el código manualmente, sin git, y lo subió a `/root/`). `/root` tiene permisos `700`: el usuario de sistema `voxikam` (sin privilegios) nunca puede *entrar* ahí, sin importar qué permisos tenga la subcarpeta — el `CHDIR` de systemd falla siempre, pase lo que pase con `/root/voxikam` en sí.
- Mismo destino fijo que ya usa el modo fresh: si no hay marcador previo (o el marcador apunta a un directorio que no existe todavía), `INSTALL_DIR` ahora siempre es `/opt/voxikam` — nunca `$SCRIPT_DIR` a ciegas. El código se sincroniza igual que siempre (rsync), solo que al destino correcto.
- Nota para recuperar una instalación ya afectada por este bug (marcador con `INSTALL_DIR` apuntando a `/root/...`): corregir `/etc/voxikam.conf` a mano una vez (`INSTALL_DIR=/opt/voxikam`) y volver a correr `deploy.sh --upgrade` — el resto lo hace solo.
- Fix relacionado, mismo run: `kaplabilling.conf` viejo en `/etc/nginx/sites-enabled/` nunca se limpiaba (solo se limpiaba `sip-platform.conf`, el nombre anterior a la plataforma anterior) — con los dos sites cargados a la vez, nginx fallaba con `limit_req_zone "api_limit" is already bound` al recargar, porque ambos definen la misma zona a nivel `http`. Agregado a la misma limpieza.

## v2.8.2 — 2026-07-01

### Fix crítico: migración la plataforma anterior fallaba en PASO 7 por falta de `root_password` de MariaDB

- Confirmado en producción (`vd1sbc2`): la migración automática dejaba `DB_ROOT_PASS=""` a propósito, asumiendo que no hacía falta en modo upgrade — pero PASO 7 (carga de schema/migraciones) sí necesita acceso root a MariaDB, y corre en TODOS los modos, no solo fresh. Resultado: `ERROR 1045 (28000): Access denied for user 'root'@'localhost'` a mitad de deploy, con los servicios `kaplabilling-*` ya detenidos.
- la plataforma anterior (el proyecto del que evolucionó VoxiKam) ya guardaba su propio `credentials.conf` en `/kaplabilling-install/logs-configs/` — mismo formato exacto que usa VoxiKam hoy, con `root_password` incluido. La migración automática no lo sabía y solo miraba `/opt/kaplabilling/backend/.env` (que solo tiene credenciales de nivel aplicación, sin root). Ahora se revisa `/kaplabilling-install/logs-configs/credentials.conf` primero — si existe, trae TODOS los datos de una (incluido `root_password`, `admin_email`, `ssh_port`, `mgmt_ip`, `private_net`, antes vacíos/adivinados). El fallback a `DATABASE_URL` del `.env` de la app se mantiene solo si ese archivo no existiera.
- Fix relacionado: el marcador `/etc/voxikam.conf` nunca se creaba tras una migración de la plataforma anterior (`MODE` queda forzado a `upgrade`, y la escritura del marcador estaba gateada a `MODE != upgrade`) — sin esto, cada corrida futura de `deploy.sh` sin flags hubiera vuelto a detectar "instalación previa de la plataforma anterior" indefinidamente en vez de mostrar el menú normal update/upgrade/reinstall.
- Validado con los datos reales pegados por el usuario desde `vd1sbc2` — extracción de los 14 campos correcta, sin colisión entre `password` y `root_password`.

## v2.8.1 — 2026-07-01

### Symlink visible para credentials.conf (sin tocar el flujo de preguntas)

- VoxiKam ya tenía la lógica correcta que también usa VoxiDet: en instalación fresca se pregunta una sola vez (con defaults auto-detectados que se aceptan con ENTER o se editan ahí mismo — `ask()`/`ask_secret()`), se guarda en `credentials.conf`, y las corridas siguientes (`--upgrade`/`--update`) ya no vuelven a preguntar nada. Ese comportamiento se mantiene intacto — no había nada que arreglar ahí.
- Lo único que sí cambió: `credentials.conf` vive en `/voxikam-install/logs-configs/`, una ruta que no salta a la vista (a diferencia del `.env` de VoxiDet, que está justo en la carpeta del proyecto). Se agrega un symlink `$INSTALL_DIR/credentials.conf → $LOG_DIR/credentials.conf` (se crea tanto en fresh como en upgrade) solo para visibilidad — el archivo real no se mueve, no se toca el path que ya usan el modo `--upgrade` ni la migración de la plataforma anterior.

## v2.8.0 — 2026-07-01

### Autotuneo también en cada arranque — no solo al correr deploy.sh

- Hasta ahora, workers/children/memoria de Kamailio solo se recalculaban corriendo `deploy.sh` a mano. Si el servidor cambia de CPU/RAM (resize en el proveedor cloud + reboot) sin que nadie corra el deploy, queda desactualizado.
- Nuevo `scripts/autotune.sh` — extrae la fórmula (antes inline en `deploy.sh`) a un script reusable, con dos modos:
  - `--no-restart` (usado por `deploy.sh`): solo actualiza los archivos de config y avisa — Kamailio puede tener llamadas en vivo en el momento del deploy, nunca se reinicia solo.
  - Sin flag (usado por el nuevo `voxikam-autotune.service`, systemd oneshot que corre en cada arranque): además reinicia `voxikam-backend`/`kamailio` si detecta cambios, y valida que queden activos (`systemctl is-active`) — seguro en este caso porque un reinicio de sistema ya cortó cualquier llamada en curso, no hay nada que proteger en ese momento.
  - `deploy.sh` habilita el servicio (`systemctl enable`, sin `--now`) — no corre en la misma corrida del deploy, solo queda listo para el próximo arranque.

## v2.7.4 — 2026-07-01

### Memoria de Kamailio — prioriza margen de seguridad sobre ahorro de RAM (decisión explícita del usuario)

- La fórmula de v2.7.1 topaba en 1024MB fijo (suficiente según el consumo medido, ~0.42MB/diálogo, pero conservador). A pedido explícito: en hosts con más de 4GB de RAM, Kamailio recibe directamente **45% de la RAM total** (punto medio del rango 40-50% pedido), no un remanente calculado. Hosts de 4GB o menos mantienen la fórmula conservadora anterior (reservar 25% para MariaDB/RTPEngine/backend primero) — con poca RAM total, un 45% fijo dejaría muy poco para todo lo demás.
- Techo absoluto de 8GB para hosts enormes (32GB+) — más que eso probablemente se toca físicamente al arrancar Kamailio, quitándole RAM real a MySQL/RTPEngine sin necesidad real (el consumo medido nunca se acerca a esa cifra).
- Simulado en el rango 1GB-64GB antes de aplicar: escala como se pidió, techo respeta el límite de seguridad.

## v2.7.3 — 2026-07-01

### Fix: `children=8` de Kamailio también estaba fijo, sin relación al CPU real

- Encontrado por el usuario al revisar el tuning de memoria: `children=8` (procesos SIP de Kamailio) estaba hardcodeado en `templates/kamailio.cfg.j2`, coincidiendo con el host actual (8 vCPU) por casualidad, no porque se calculara. Mismo problema que ya se había arreglado para los workers del backend.
- Cambiado a `children={{ kamailio_children }}`, sustituido en `deploy.sh` con `nproc` real (1:1 con vCPU — los children de Kamailio son mayormente I/O-bound, no CPU-bound, así que compartir núcleos 1:1 con backend/RTPEngine en el mismo host es seguro, mismo criterio que ya usaba el valor original).

## v2.7.2 — 2026-07-01

### Fix: sesiones RTPEngine huérfanas — nunca se liberaban al colgar

- Confirmado en producción (`vd1sbc2`): 1158 sesiones activas en RTPEngine mientras Kamailio solo reportaba 149 diálogos reales en el mismo momento. Causa: `event_route[dialog:end]` y el bloque `is_method("BYE")` del ruteo principal (`templates/kamailio.cfg.j2`) solo hacían el registro de CDR — nunca llamaban `rtpengine_delete()`. Cada llamada colgada dejaba su sesión de RTPEngine viva hasta que expiraba sola por su propio timeout interno (hasta 3600s para streams silenciosos).
- Agregado `rtpengine_delete()` en el bloque `BYE` y en `CANCEL` (llamada cancelada antes de contestar, con early media ya negociado). Requiere recargar `kamailio.cfg` (restart) para aplicar.

## v2.7.1 — 2026-07-01

### Tuning inteligente de memoria de Kamailio — autoajustado por RAM real, no valor fijo

- El fix de memoria de Kamailio (v2.6.4) usaba `SHM_MEMORY=512`/`PKG_MEMORY=32` fijos, calculados a mano con el dato de un solo servidor. Reemplazado por una fórmula basada en la RAM real del host detectada en cada deploy (mismo espíritu que el autotuneo de `WORKERS`): reserva 25% (mínimo 1GB) para MySQL/RTPEngine/backend en el mismo host, y de lo que queda, 1/4 para Kamailio (techo 1024MB — ya cubre ~2400 diálogos con el consumo medido de ~0.42MB/diálogo, muy por encima de las 300-400 llamadas objetivo).
- Si el host crece de RAM en el futuro, el valor sube solo en el próximo deploy, sin tocar código — pedido explícito del usuario.

## v2.7.0 — 2026-07-01

### Migración automática desde la plataforma anterior (evolución del mismo proyecto)

- VoxiKam es la evolución de la plataforma anterior — varios servidores en producción (ej. `vd1sbc2`, servidor de telefonía en vivo) siguen con la instalación vieja (`/opt/kaplabilling`, usuario `kaplabilling`, systemd `kaplabilling-{backend,frontend,hep}.service`, MySQL `sip_platform`). `deploy.sh` no tenía forma de detectar esto — corrido tal cual hubiera intentado una instalación fresca (usuario nuevo, DB nueva vacía), chocando con lo que ya corre y perdiendo el histórico.
- Nuevo bloque de detección en `deploy.sh` (antes del chequeo de marcador): si no hay `/etc/voxikam.conf` pero se detecta `/opt/kaplabilling/backend/.env` o servicios `kaplabilling-*` activos, se extraen `DATABASE_URL` (usuario/password/puerto/DB, vía regex sobre `mysql+aiomysql://...`), `PUBLIC_IP`, `PRIVATE_IP`, `DOMAIN`, `WEB_PORT` y `JWT_SECRET` directo del `.env` viejo — **se reusan tal cual, sin crear ningún objeto nuevo de MySQL** — y se sintetiza `credentials.conf` en el mismo formato que ya lee el flujo de `--upgrade` existente, forzando ese modo. El resto del flujo (creación de usuario `voxikam`, regeneración de `.env`/`kamailio.cfg`, arranque de servicios) ya funcionaba correctamente en modo upgrade sin tocar la base de datos.
- Los servicios `kaplabilling-*` se detienen automáticamente antes de arrancar los `voxikam-*` (mismos puertos). `/opt/kaplabilling` queda intacto como respaldo de rollback — no se mueve ni se borra.
- Probado end-to-end con datos simulados de un la plataforma anterior falso (extracción de `DATABASE_URL` real, generación de `credentials.conf`, relectura con la misma función `_cred()` que usa el resto del script) antes de aplicar — todos los valores redondean correctamente.
- Nuevo aviso en el resumen final del deploy si se tocó la config de Kamailio: recuerda que hace falta `systemctl restart kamailio` manual (no automático) para aplicar, y que corta todas las llamadas activas.

## v2.6.5 — 2026-07-01

### Fix: atribución — "By KPBTec" en 37 archivos (gap del sweep anterior)

- El sweep de v2.6.1 corrigió "KPBTec" → "KPBTec", pero no cubrió esta variante distinta ("By KPBTec · https://github.com/KPBTec") — mismo criterio, cambiado a "By KPBTec · https://github.com/KPBTec".

## v2.6.4 — 2026-07-01

### Fix crítico: techo real de ~90 llamadas concurrentes — memoria compartida de Kamailio en el default de fábrica

- Reportado por el usuario: con Magnus (proveedor anterior) llegaban a 300-400 llamadas simultáneas; con la infraestructura actual no pasa de ~90. Confirmado en producción (`vd1sbc2`): Kamailio corre con `SHM_MEMORY=64` / `PKG_MEMORY=8` (default de fábrica del paquete, pensado para pruebas) — `kamcmd core.shmmem` mostró `max_used: 39376904` (~37.5MB) ya sobre un pool de solo 64MB (58% del total) — con `dialog`+`siptrace`+`dispatcher`+`sqlops` cargados, cada llamada consume memoria de este pool y se agota mucho antes de las 300-400 esperadas.
- El host tiene de sobra (confirmado: 6.7GB RAM libre de 7.75GB, load average 0.6 en 8 cores) — **no es un problema de hardware**, es que Kamailio nunca se configuró para usar más que ese default de fábrica.
- `deploy.sh`: nuevo `/etc/default/kamailio.d/voxikam-memory.conf` (el unit de Kamailio ya soporta `EnvironmentFile=-/etc/default/kamailio.d/*` — no hace falta tocar `ExecStart` ni el paquete) subiendo a `SHM_MEMORY=512`, `PKG_MEMORY=32` — dimensionado con el dato real medido (~0.42MB SHM por llamada, margen 3x).
- **Requiere reiniciar Kamailio para aplicar** — corta todas las llamadas activas en el momento del restart. Aplicar en horario de baja carga.

## v2.6.3 — 2026-07-01

### Fix: `get_current_user()` consultaba MySQL en CADA request sin cache

- Sin Redis en este stack (a diferencia de VoxiDet), `get_current_user()` (`backend/auth.py`) hacía `SELECT ... FROM users WHERE id=:id` en cada request autenticado — y `/traces` en modo "en vivo" hace polling cada 1 segundo, así que cada analista con esa pantalla abierta generaba una query por segundo solo para validar el token.
- Cache simple en memoria por worker con TTL de 20s (sin invalidación activa al desactivar un usuario — por eso el TTL se mantiene corto). Probado: 5 requests seguidas → 1 sola consulta real a MySQL, y expira correctamente pasado el TTL.

## v2.6.2 — 2026-07-01

### Autotuneo de workers del backend según CPU real del host

- `uvicorn --workers 2` estaba fijo en `systemd/voxikam-backend.service` — no escalaba con el tamaño del host. A diferencia de VoxiDet, aquí no hay un modelo ML pesado que compartir entre workers, así que el único límite real es CPU: `deploy.sh` ahora detecta `nproc` y calcula `WORKERS = vCPU - 1` (reservando 1 core para Kamailio/MySQL/RTPEngine, que corren en el mismo host), con techo de 16.
- Nuevo placeholder `__WORKERS__` en `systemd/voxikam-backend.service`, sustituido en los dos puntos del script donde se templetizan los service files (instalación fresca y `--update`/`--upgrade`).

## v2.6.1 — 2026-07-01

### Fix: atribución — "KPBTec" en 37 archivos

- El repo tenía headers `# Copyright (c) 2026 KPBTec` copiados en casi todo `backend/`, `scripts/` y `deploy.sh`, además de la misma línea dos veces en `LICENSE` — a diferencia de VoxiDet, que nunca tuvo headers de copyright por archivo. Reemplazado por `KPBTec` en los 37 archivos (mismo criterio ya aplicado en VoxiDet: la atribución pública es siempre "KPBTec", nunca el nombre personal). `AUTHORS.md` no necesitó cambios — nunca documentó el nombre real, ya usaba solo "KPBTec".

### Fix definitivo: fail2ban.service crasheaba ~1s después de "Server ready" — falta `python3-systemd`

- Tras forzar `backend = systemd` en el jail `sshd` (ver más abajo), el servicio arrancaba y moría casi de inmediato con exit 255, sin reintentar (`RestartPreventExitStatus=0 255` en el unit de systemd lo impide a propósito). El log reveló la causa real: `ERROR Backend 'systemd' failed to initialize due to No module named 'systemd'` → `ERROR Failed to initialize any backend for Jail 'sshd'`. Cuando un jail no puede inicializar su backend, fail2ban aborta el proceso completo. Faltaba `python3-systemd` (bindings de Python para leer journald), que no es una dependencia automática de `fail2ban` en apt. Agregado a `deploy.sh`. Mismo fix en VoxiDet, donde se diagnosticó primero.
- De paso se detectó que este proyecto nunca tuvo detección automática de `SSH_SERVICE` (`ssh.service` vs `sshd.service`) — el jail template tenía el nombre hardcodeado (`journalmatch = _SYSTEMD_UNIT=ssh.service`). Portado el mecanismo que ya usaba VoxiDet (`systemctl list-unit-files` + fallback a `ssh.service`) a los dos lugares donde se detecta `SSH_PORT` (instalación fresca y fallback de instalaciones antiguas), y el jail ahora usa el placeholder `__SSH_SERVICE__` sustituido por `deploy.sh`.
- El `apt-get install fail2ban python3-systemd` estaba condicionado a `if ! command -v fail2ban-client` — en un servidor donde fail2ban ya estaba instalado, el bloque se saltaba y `python3-systemd` nunca se instalaba con solo re-ejecutar `deploy.sh`. Vuelto incondicional (`apt-get install` es idempotente), mismo criterio que ya se usaba para `ethtool` en este mismo script — así una dependencia nueva se garantiza en cada deploy, no solo en la instalación inicial.

### Fix: jail sshd sin backend explícito hacía fallar fail2ban.service completo

- Encontrado al desplegar VoxiDet: `[sshd]` con `backend = auto` sin `logpath` — en Debian/Ubuntu moderno sin `/var/log/auth.log` (todo va a journald), fail2ban no autodetecta de dónde leer y **el servicio entero** falla al arrancar (`ERROR Failed during configuration: Have not found any log file for sshd jail`), no solo ese jail. Forzado `backend = systemd` + `journalmatch = _SYSTEMD_UNIT=ssh.service`, mismo mecanismo que ya usaba `voxikam-security`. Mismo fix aplicado en VoxiDet.

### Fix: detección de puerto SSH podía agarrar un socket de X11 forwarding

- `ss -tlnp | grep sshd` corría antes que `sshd_config` — pero puede matchear el socket que sshd abre para X11 forwarding de una sesión activa (`ssh -X`, típicamente puerto 6000+display, ej. 6010), no el puerto real donde escucha sshd. Encontrado al corregir el mismo bug en VoxiDet (que copió esta lógica de aquí). Invertido el orden en los dos lugares donde aparecía (instalación fresca y fallback de instalaciones antiguas sin `ssh_port` persistido): `sshd_config` primero, `ss` solo como respaldo. Agregado `|| true` a ambos para que un `grep` sin match no mate el script bajo `pipefail`.

### Panel: ver/desbanear IPs de fail2ban desde Firewall

- Nueva sección en la página Firewall (`frontend/app/(admin)/firewall/page.tsx`) mostrando IPs baneadas por jail (`sshd`, `voxikam-security`) con botón "Desbanear". Completa lo que había quedado pendiente en `fail2ban/README.md`.
- Backend corre nativo (no Docker) — a diferencia de VoxiDet, esto sí pudo ser síncrono: `GET /admin/firewall/fail2ban` (lee `fail2ban-client status` en vivo) y `POST /admin/firewall/fail2ban/unban` (`fail2ban-client set <jail> unbanip <ip>` directo). `sudoers/voxikam` ahora también permite `/usr/bin/fail2ban-client`.

## v2.6.0 — 2026-07-01

### Seguridad: fail2ban (sshd + rechazos del backend) — mismo módulo que VoxiDet

- Nuevo `fail2ban/` (`filter.d`/`jail.d` versionado, mismo patrón que `nftables/`/`sudoers/`): jail `sshd` (puerto auto-detectado) + jail propio `voxikam-security`.
- `voxikam-security` lee **journald directo** (`backend = systemd`, `journalmatch = SYSLOG_IDENTIFIER=voxikam-backend`) — `voxikam-backend.service` ya loguea con `StandardOutput=journal`, no hizo falta agregar un archivo de log ni bind mount (a diferencia de VoxiDet, que corre en Docker).
- Banea por **login fallido** (`routers/auth.py`) y **User-Agent de scanner** (`middleware/security.py`) — señales que un usuario legítimo nunca dispara. Deliberadamente NO cuenta el rate-limit de `/api/` (300 req/60s) ni el de `/api/auth/login` (10 req/60s): un cliente de alto tráfico normal puede tocarlos sin ser un ataque, banear por eso sería un auto-DoS.
- `banaction = nftables-allports` explícito (no el default iptables) — mismo criterio que ya se aplicó para evitar conflictos entre iptables y el nftables que ya usa el proyecto.
- Nuevos logs `SECURITY_REJECT ip=<ip> reason=<motivo> path=<path>` vía logger `voxikam-security`.
- Pendiente (no en esta sesión): ver/desbanear IPs desde el panel admin — hoy es solo `fail2ban-client` por SSH.

### Versionado: homogeneizado a `MAJOR.MINOR.PATCH` (antes `MAJOR.MINOR`)

- VoxiDet siempre usó semver completo; VoxiKam usaba `MAJOR.MINOR` a propósito. Unificado a 3 partes en ambos — `release.conf`, badge de `README.md` y el esquema documentado arriba. Headers de versiones anteriores a v2.6.0 quedan como estaban (`v2.5`, `v2.4`, etc.), sin reescribir historial.

## v2.5 — 2026-06-30

### Frontend: versión en badge de esquina (antes solo en README, ya desactualizado)

- El badge de versión en `README.md` estaba clavado en "2.4" a mano y quedó desactualizado apenas subimos a 2.5 — ahora referencia el mismo color de marca (ámbar).
- `next.config.ts` ahora lee `PLATFORM_VERSION` de `release.conf` en build time (`NEXT_PUBLIC_VOXIKAM_VERSION`) — nunca vuelve a desincronizarse. `Sidebar.tsx` muestra un badge fijo en la esquina inferior derecha, separado del wordmark (mismo patrón que VoxiDet).

### Naming: `install.sh` → `deploy.sh` (consistente con VoxiDet)

- Renombrado (`git mv`, historial preservado) para que ambos productos Voxi usen el mismo nombre de script de despliegue. Actualizadas todas las referencias (README raíz + de cada subcarpeta, CLAUDE.md, sudoers/voxikam).

### Diseño: paleta unificada con VoxiDet (Voxi Design System)

- Nuevo documento compartido: `Proyectos-Public/VOXI_DESIGN_SYSTEM.md` — fuente única de paleta/tipografía para toda la familia Voxi (VoxiKam + VoxiDet). Cualquier proyecto nuevo bajo `voxi*` debe leerlo antes de definir su propio tema.
- **Color de marca**: azul/cian (`brand-*` = sky Tailwind) → ámbar/cobre (`#dd8b3d`), tomado del propio rayo del logo (`logo.svg` ya usaba ámbar en el ícono — el azul solo vivía en el texto "Voxi"). Cambio centralizado en `app/globals.css` (`@theme`), se propaga solo a las 22 páginas que ya usaban clases `brand-*`.
- Barridos los usos de `blue-*`/`sky-*` Tailwind hardcodeados que NO pasaban por el token (~14 archivos): botones primarios y links de acción → `brand-*`; badges categóricos neutros (tipo de carrier, código HTTP, estado de factura) → nuevo token `info-*` (azul apagado, reservado para eso — nunca color de marca); lecturas numéricas en vivo (costo, throughput) → `brand-400` + `font-mono`.
- **Fix de naming**: `Sidebar.tsx` todavía mostraba el wordmark viejo "**Kapla**Billing" (pre-rename) en vez de "VoxiKam" — quedó desincronizado del logo real (`logo.svg` ya decía "VoxiKam" desde v2.4). Corregido.
- Tipografía: Inter → **Manrope** (UI), + **IBM Plex Mono** vía `--font-mono` en `@theme` — firma compartida con VoxiDet: toda lectura numérica en vivo (costo, ms, %) se muestra en monoespaciada, como un instrumento de control.

## v2.4 — 2026-06-30

### Frontend: Logo + redesign de plataforma

**Nuevo componente `Logo.tsx`:**
- Icono SVG con lettermark "K" y gradiente azul (`#0ea5e9 → #0284c7`), esquinas redondeadas, punto de acento
- Tres tamaños (`sm`, `md`, `lg`) y modo icon-only
- Nombre "**Kapla**Billing" con tipografía marcada (brand-400 + white), subtítulo "SIP Class 4/5"

**Login (`app/(auth)/login/page.tsx`):**
- Logo centrado sobre el card (ya no texto plano)
- Fondo con gradiente radial azul sutil en la parte superior
- Card con sombra profunda + glow azul difuso
- Labels en uppercase tracking-widest, inputs con focus-border dinámico (JS)
- Botón con glow azul en estado normal, opaco en loading

**Sidebar (`components/Sidebar.tsx`):**
- Logo `<Logo size="sm" />` reemplaza el texto plano en el header
- Gradiente sutil en el fondo del sidebar (azul 4% → transparent)
- Links activos con `borderLeft` azul + fondo semitransparente (inline styles para compatibilidad CSS vars)
- Avatar de usuario con gradiente brand + glow, inicial del nombre
- Hover en logout cambia a rojo (inline JS en lugar de Tailwind)

**Tema (`globals.css`):**
- Colores de fondo más profundos: `--color-surface: #070c16`, `--color-card: #0d1526`
- Paleta extendida: `--color-brand-400`, `--color-card-2`, `--color-border-2`
- Colores de texto más legibles: `--color-text: #e2e8f0`, `--color-text-2: #6b87a8`
- Scrollbar personalizado: 5px, thumb azul oscuro
- `-webkit-font-smoothing: antialiased` en body

**Font (`app/layout.tsx`):**
- Import Google Fonts Inter 400/500/600/700 en `<head>`

---

## v2.3 — 2026-06-25

### Instalador autónomo: Kamailio 5.7 + RTPEngine 10.x · Timer · Feedback

**Instalación del stack SIP desde cero (`scripts/setup/04_install_sip_stack.sh`):**
- El instalador ya no requiere Kamailio ni RTPEngine pre-instalados — los instala automáticamente si no están presentes
- Kamailio 5.7.x desde el repo oficial `deb.kamailio.org/kamailio57` (Debian 12 Bookworm)
- RTPEngine 10.x desde el repo Sipwise `deb.sipwise.com/spce/mr10.5/`
- Incluye módulos requeridos: `kamailio-mysql-modules`, `kamailio-extra-modules`, `kamailio-utils-modules`, `kamailio-tls-modules`
- Si ya están instalados, los detecta y omite sin tocar nada (safe en servidores existentes)
- Confirmación interactiva antes de instalar — el operador puede cancelar para instalar manualmente
- `rtpengine.service` habilitado automáticamente tras la instalación (sin arrancar — la config la aplica el instalador en el paso siguiente)

**Tiempo de instalación en el resumen final:**
- Todos los modos (`fresh`, `--upgrade`, `--update`) muestran el tiempo total al finalizar (formato `Xm Ys`)

**Feedback en el resumen:**
- El resumen final incluye el link a `github.com/KPBTec/VoxiKam` para reportes y comentarios

**Upgrade:**
- `./deploy.sh --upgrade` detecta Kamailio/RTPEngine existentes y los omite — sin cambios en servidores v2.2
- Para servidores nuevos: `./deploy.sh` instala el stack completo desde cero incluyendo el SIP stack

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
- Nuevo modo: `./deploy.sh --update` — actualiza código, deps, DB y frontend sin tocar Kamailio
- Opción 1 en el menú interactivo (recomendada para despliegues de código en producción)
- Pasos: rsync → pip install → migraciones DB → npm build → crontab → restart sip-backend/frontend/hep → nginx reload
- Kamailio, nftables, MariaDB tuning y configuración de OS no se tocan
- `--upgrade` conserva el comportamiento anterior (completo, incluye Kamailio)

**RTPEngine — CLI socket:**
- `listen-cli = 127.0.0.1:9901` en `rtpengine.conf` — habilita `rtpengine-ctl` para estadísticas por sesión (jitter, packet loss)
- Requiere `systemctl restart rtpengine` en ventana de mantenimiento (corta llamadas activas)

**Update:**
- `./deploy.sh --update` aplica todas las migraciones de schema (cpslimit, sip_code)
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
- `./deploy.sh --upgrade` aplica el índice `idx_cid_captured` automáticamente
- Kamailio se reinicia (aplica `dlg_set_timeout`) — hacerlo en horario de baja carga
- Backend/Frontend: `systemctl restart sip-backend sip-frontend` (sin corte de llamadas)

---

## v2.0 — 2026-06-22

### Performance Layer — System Tuning

**sysctl `/etc/sysctl.d/99-voxikam.conf`:**
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
- `./deploy.sh --upgrade` — PASO 8b aplica todo el tuning automáticamente
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
- `deploy.sh` ahora detiene/inicia/verifica `sip-hep` junto con los demás servicios
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
- Modo `upgrade`: detecta la instalación existente via `/etc/voxikam.conf`, detiene servicios, sincroniza código con rsync, aplica migraciones de schema
- Modo `reinstall`: elimina datos y reinstala desde cero conservando la ruta instalada
- Flags `--upgrade` / `--reinstall` para automatización
- `release.conf`: nombre, versión y defaults centralizados — editar para re-brandear

---

## v1.0

### Release inicial

- **Instalador** `deploy.sh`: Debian 12, single-command, ~10 min, sin dependencias previas
- **Backend** FastAPI async: auth JWT, CDRs en tiempo real, carriers, customers, rates, firewall, reports, invoices
- **Frontend** Next.js 15 standalone: panel admin completo con Tailwind v4, dark mode
- **Live dashboard**: llamadas activas en tiempo real via polling
- **Kamailio SBC** + RTPEngine configurados automáticamente
- **nftables** gestionado desde el panel (carriers + clientes en IPs)
- **MariaDB** puerto aleatorio, bind 127.0.0.1
- Usuario `voxikam` sin shell, permisos mínimos
