# Validar contra Kamailio real

**Actualización — sí hay forma de probar contra un Kamailio real en este
sandbox.** Hay un rootless Docker corriendo (`docker-rootless` en el
scratchpad de la sesión, socket en `/run/user/1000/docker.sock`) — se
puede levantar un contenedor `debian:12`, instalar el paquete `kamailio`
real (5.6.3 en bookworm) + `kamailio-mysql-modules` +
`kamailio-extra-modules` (trae `htable`, `rtimer`, `async`, `rtpengine`,
etc.), copiar el `.cfg` renderizado y correr `kamailio -c -f` (config
check) o incluso `kamailio -DD -E -f` (arranque real — llega hasta donde
puede sin una DB/RTPEngine de verdad detrás, pero valida el parseo Y el
`mod_init()` de cada módulo). Esto reemplaza lo que antes era pura
inferencia contra la documentación — encontró bugs reales que la
inferencia no detectó (ver sección 1). Repetir este mismo procedimiento
para cualquier cambio futuro a `kamailio.cfg.j2` antes de darlo por
bueno.

## 1. Pacing de CPS por carrier (esperar en vez de rechazar)

**PROBADO END-TO-END con tráfico SIP real, no solo config-check.** Rig
completo: Kamailio 5.6.3 real (Docker/Debian 12) + MariaDB real (schema
completo + datos sembrados: 1 cliente, 1 carrier con `cps_limit=3`) +
`sipp` como generador de tráfico (UAC simulando Asterisk) + `sipp` como
UAS simulando el carrier. Se probaron los dos caminos:

- **Ráfaga de 8 llamadas simultáneas contra `cps_limit=3`**: las
  primeras 3 pasan directo, las 5 restantes quedan reintentando
  (`async_ms_sleep(100)` en bucle) y **las 8 terminan con `200 OK`**
  dentro de ~1.1s — ninguna se pierde, ninguna queda colgada.
- **Ráfaga de 30 llamadas contra el mismo límite**: 17 terminan en `200
  OK` (repartidas en el tiempo, respetando el límite de 3/s) y **21
  terminan en `503` exactamente a los 2000ms** de espera — la válvula de
  seguridad corta como se diseñó, ninguna llamada queda esperando para
  siempre.

Se llegó a este diseño (y a esta validación) recién en la TERCERA
iteración — las dos anteriores fallaron contra el Kamailio real, cada
una por una razón distinta:

**Intento 1 — diseño original (cola FIFO + `rtimer` + `t_continue()`):**
la idea era encolar con `t_suspend()`, guardar el índice/label de la
transacción en una cola FIFO propia (htable), y que un `rtimer` cada
100ms la reanudara llamando `t_continue(idx, label, ruta)` con esos
valores. `kamailio -c` real tiró:
- `$shtinc(...)` usado como sentencia suelta — es un pvar de solo
  lectura, hay que asignarlo a algo.
- `continue;` dentro de un `while` — **no existe en el lenguaje de
  config de Kamailio** (confirmado con un `.cfg` mínimo aislado — lo
  trata como un identificador de función desconocido). `break` sí existe.
- El hallazgo que tiró el diseño completo: **`t_continue()` exige que
  sus 2 primeros parámetros sean constantes literales en el config, no
  acepta `$var()`/`$avp()` con un valor leído en runtime** (confirmado
  con un `.cfg` mínimo aislado: `t_continue(5, 7, "R")` parsea bien,
  `t_continue($var(x), $var(y), "R")` con los mismos valores no). Es
  **imposible** reanudar una transacción elegida dinámicamente desde una
  ruta de `rtimer` con esta función.

**Intento 2 — rediseño con el módulo `async` (`async_ms_sleep`):**
en vez de una cola central, cada llamada se reintenta a sí misma
(`async_ms_sleep("100")` + `route(CPS_GATE)` de nuevo) — el módulo
`async` reanuda automáticamente ESA llamada específica, sin necesitar
guardar ningún id a mano, y **sí acepta el delay como valor runtime**
(`async_ms_sleep("$var(d)")` parsea bien, confirmado). Pero al probar
con tráfico real:
- `$shtinc(cps=>key)` (para incrementar el contador) **siempre devolvía
  0 y nunca persistía nada en la htable** — confirmado con un `.cfg`
  mínimo aislado, llamándolo 3 veces seguidas con la misma key: las 3
  devuelven 0. Contradice lo que dice el código fuente del módulo (que
  sí debería incrementar) — posible bug real del binario empaquetado en
  Debian 12, o diferencia de versión. Reemplazado por lectura+escritura
  manual (`$sht()` de toma y daca, que sí funciona, confirmado aparte).
- `sht_lock()`/`sht_unlock()` (para hacer esa lectura+escritura atómica)
  **tampoco aceptan un argumento con `$var()`** — ni siquiera una
  referencia simple sin concatenar. Mismo mensaje que `t_continue()`:
  "parameter 1 is not constant". Reemplazado por un lock GLOBAL fijo
  (`sht_lock("cps=>lock")`, string literal) en vez de uno por
  carrier/segundo — la sección crítica es mínima (2 operaciones), no
  debería notarse en la práctica.
- Con esos dos fixes, las primeras 3 llamadas pasaban bien, pero las que
  necesitaban esperar **se colgaban para siempre** — ni 200 ni 503,
  nunca. El log mostró la causa real: `WARNING: async_task_push():
  async task pushed, but no async workers - ignoring`. `async_ms_sleep()`
  depende de un parámetro de **core** (`async_workers=N`, una directiva
  suelta como `children=`, no un `modparam`) — `modparam("async",
  "workers", N)` es del módulo `async` (para `async_route`/timers) y NO
  alcanza por sí solo. Agregado `async_workers=4` a nivel core — con eso
  recién funcionó de punta a punta.

Diseño final, en `templates/kamailio.cfg.j2` (idéntico en ambos repos):

- `async_workers=4` (core, nuevo) + `loadmodule "async.so"` (en vez de
  `rtimer.so`) + `modparam("async", "workers", 2)` +
  `modparam("async", "ms_timer", 10)`.
- Un solo htable `cps` (contador por carrier/segundo). Ya no existe la
  cola `cpsq` del intento 1.
- `route[CPS_GATE]`: `sht_lock("cps=>lock")` → lee contador → si hay
  lugar, `$sht(...) = cnt+1` (escritura manual, no `$shtinc`),
  `sht_unlock`, relay directo. Si no hay lugar, `sht_unlock`, y
  `async_ms_sleep("100")` + `route(CPS_GATE)` de nuevo, hasta
  `{{ cps_max_wait_ms }}` (vía `$avp(cps_waited)`, sobrevive el sleep
  igual que `$avp(carrier_id)`/`$avp(cps_limit)` — mismo criterio
  $avp() vs $var() de siempre) — ahí responde 503 vía
  `route[CPS_TIMEOUT]`.

### Cómo reproducir esta validación

```bash
# 1. Config-check + arranque real (confirma parseo + mod_init de todos
#    los módulos, incluyendo dispatcher/async — no hace falta MySQL real
#    para esto, solo para que el proceso quede completamente arriba)
kamailio -c -f /etc/kamailio/kamailio.cfg
kamailio -DD -E -f /etc/kamailio/kamailio.cfg

# 2. Carrier de prueba con cps_limit bajo (ej. 3), un UAS simple (sipp o
#    similar) simulando el carrier, y una ráfaga de INVITEs con sipp por
#    encima del límite:
sipp -sf uac_call.xml -i <ip> -p <puerto> -m 8 -r 200 <ip_kamailio>:5060

# 3. Confirmar en el log:
#    - Los primeros N (=cps_limit) pasan directo (sin línea "esperando").
#    - El resto loguea "CPS_GATE: carrier X al límite — esperando (llevo
#      Nms)" en incrementos de 100ms, y TODAS terminan en 200 o 503.
#    - Ninguna queda sin una línea REPLY/CPS_TIMEOUT final — si una
#      llamada nunca se resuelve, es la señal exacta del bug de
#      async_workers descrito arriba.
```

Si algo de esto falla en staging: el fallback más seguro es no setear
`cps_limit` en ningún carrier (columna NULL = cero cambio de
comportamiento, todo el resto del SIP sigue exactamente igual que antes
de este feature).

## 2. Fix: `customer_id` mal calculado en llamadas con carrier override

Bug encontrado (preexistente, no introducido por la sesión de CPS):
`route[CARRIER_SEND]` calculaba `dlg_var(customer_id) = $avp(grp) - 100`,
asumiendo que el grupo dispatcher siempre es `100+customer_id`. Para
llamadas de un cliente que eligió un carrier específico en el portal
(grupo de override, `90000+cid` o `95000+customer_prefixes.id`), esto
daba un `customer_id` inventado (ej. grupo `90008` → `customer_id=89908`
en vez de `8`) — como `cdrs.customer_id` no tiene FK (a propósito, ver
`db/schema.sql`), el INSERT no fallaba, simplemente el CDR quedaba
huérfano: nunca se le facturaba a nadie, no aparecía en el
dashboard/historial de ese cliente.

Fix: `gen_dispatcher.py::build_routes_cfg` ahora emite `$var(cid) = N`
(el customer_id real) junto con `$var(grp)`, en vez de derivarlo. Se
propaga a `$avp(cid)` en `route[OUTBOUND_TO_CARRIER]` (mismo patrón que
`orig_rU`/`grp`, sobrevive `t_suspend()`), y `route[CARRIER_SEND]` lo usa
directo. Validado en sandbox: render real de `build_routes_cfg()` con un
cliente sin override (grupo `105` → `cid=5`, correcto siempre) y uno con
override (grupo `90008` → `cid=8`, antes hubiera dado `89908`).

Falta probar contra Kamailio real: generar una llamada de prueba desde un
cliente CON `active_carrier_id` seteado (elegido vía portal) y confirmar
en la tabla `cdrs` que `customer_id` es el real, no un número gigante sin
sentido. Si en producción hay CDRs viejos con `customer_id` en el rango
`89900+`/`94900+` (fuera de cualquier ID real de `customers`), son
huérfanos de este bug — vale la pena un query exploratorio antes de dar
el fix por probado:

```sql
SELECT customer_id, COUNT(*) FROM cdrs
WHERE customer_id NOT IN (SELECT id FROM customers)
GROUP BY customer_id ORDER BY customer_id;
```

## 3. Reparto de tráfico por % entre carriers (algoritmo 11)

Qué se agregó: `customers.carrier_split_mode` ('priority' default / 'weight')
+ `customer_carriers.weight`. En modo 'weight', `gen_dispatcher.py` agrega
`rweight=N` a cada destino del grupo default (`100+cid`) en `dispatcher.list`
(1 si el carrier no tiene peso seteado — nunca se omite el atributo, ver
comentario en `_dispatcher_line`), y `voxikam-routes.cfg` emite `$var(alg) =
11;` SOLO para ese grupo — los grupos de override (carrier pineado por el
cliente vía portal) nunca llevan `rweight=` ni `$var(alg)=11`, siguen
siendo de prioridad/único destino como siempre. `kamailio.cfg.j2` usa
`$var(alg)` si vino seteado, si no cae al `$shv(carrier_alg)` global de
siempre (route[OUTBOUND_TO_CARRIER]).

Verificado contra la documentación real de Kamailio (WebFetch, dispatcher
module 5.7.x): alg 11 no requiere modparam extra, solo el atributo
`rweight`; y el failover real (`ds_next_dst()` en
`failure_route[CARRIER_FAILOVER]`, ya existente) sigue funcionando —
camina el resto de destinos ya armados por `ds_select_dst()`, agnóstico al
algoritmo que los generó. Esto último es una inferencia de cómo está
implementado el módulo, **no está documentado explícito** — es lo primero
a confirmar con tráfico real.

Validado en sandbox con render real de `build_dispatcher_list()`/
`build_routes_cfg()` (fixtures con un cliente en modo weight, un carrier
con peso NULL, y una campaña con pin de portal activo): `rweight=1`
default correcto para el carrier sin peso, `$var(alg)=11` solo en el grupo
default, ausente en el grupo de override de la campaña con pin. También
`alembic upgrade head` (0001→0002) contra una DB de prueba vacía, y las
mismas migraciones corridas dos veces seguidas (idempotencia de `ADD
COLUMN IF NOT EXISTS`).

Falta probar contra Kamailio real:

```bash
# Carrier de prueba: cliente con 2 carriers en modo weight (30/70).
# Generar tráfico real (sipp, o llamadas de prueba) y confirmar:
# - La proporción real de llamadas por carrier se acerca a 30/70 (no exacta
#   con poco volumen — es probabilístico, no round-robin).
# - Si uno de los 2 carriers se cae (ds_probing lo marca down), el 100%
#   del tráfico nuevo va al que queda (sin que haga falta tocar nada).
# - Un 5xx/408 real dispara failover al otro carrier del grupo (ver
#   CARRIER_FAILOVER) tal como con alg 8 — confirmar que ds_next_dst()
#   funciona igual con alg 11 (inferido, no documentado explícito).
kamcmd dispatcher.list   # confirmar que el grupo trae rweight= visible
```

Si algo de esto falla: el fallback más seguro es dejar `carrier_split_mode`
en 'priority' (default) para ese cliente — cero cambio de comportamiento.
