# VoxiKam — Esquema de base de datos

Documenta el schema real definido en [`db/schema.sql`](../db/schema.sql) (MariaDB 10.11+, InnoDB, utf8mb4).
21 tablas agrupadas por módulo. A diferencia de VoxiDet (ver `voxidet_logs.param1-4`,
ya migrado a columnas dedicadas en v1.12.0), aquí no hubo columnas genéricas
sobrecargadas que migrar — cada tabla ya nace con nombres semánticos
(`src_number`, `dst_number`, `sip_code`, `disposition`, `hangup_cause`, etc.),
así que este documento es puramente descriptivo.

## Usuarios y clientes

| Tabla | Propósito |
|---|---|
| `users` | Login admin/cliente. `role` (`admin`/`client`) determina si `customer_id` aplica. |
| `customer_profiles` | Perfiles de módulos reutilizables (`show_calls`, `show_quality`, etc.) para asignar a varios clientes a la vez. |
| `customers` | Trunks SIP — balance, límites (`calllimit`/`cpslimit`), `techprefix`, flags de módulos propios (usados si `profile_id` es NULL). |
| `customer_ips` | IPs/CIDRs autorizadas por cliente (además del dispatcher group 1 = LAN Asterisk). |

## Carriers y tarifas

| Tabla | Propósito |
|---|---|
| `carriers` | Providers SIP salientes — prioridad, `outbound_prefix`/`remove_prefix`, `failover_id` (encadena a otro carrier), `dispatcher_group`. |
| `customer_carriers` | Asignación N:M cliente↔carrier con prioridad propia. |
| `prefixes` | Tabla global de destinos (longest-prefix-match, patrón Magnus). |
| `prefix_lengths` | Optimización para el longest-prefix-match — cuenta de prefijos por longitud. |
| `rate_plans` | Planes tarifarios (moneda, estado). |
| `rates` | Sell rates — lo que se cobra al cliente por prefijo (`rateinitial`, `connectcharge`, bloques de facturación). |
| `carrier_rates` | Buy rates — lo que cobra cada carrier por prefijo. |

## CDRs y tiempo real

| Tabla | Propósito |
|---|---|
| `cdrs` | CDR de llamadas contestadas/con intento real. `lucro` es columna generada (`sessionbill - buycost`). `disposition` ENUM, `sip_code`, `call_state` (estilo sngrep), `hangup_cause`. |
| `cdrs_failed` | CDRs de llamadas fallidas, tabla separada para no inflar `cdrs` con el volumen de intentos rechazados. |
| `active_calls` | Llamadas en curso — actualizada por eventos `dialog.so` de Kamailio hacia FastAPI. |
| `calls_timeseries` | Serie de tiempo por minuto (cron), alimenta el dashboard histórico de volumen. |
| `traffic_quality_hourly` | Resumen de calidad ASR por hora/cliente (cron cada minuto vía UPSERT) — desglosa por código SIP (`c_487`, `c_486`, `c_404`, `c_503`, `c_other`) y `short_calls` (billsec < 5s, proxy de buzón). |

## Resúmenes y facturación

| Tabla | Propósito |
|---|---|
| `cdr_summary_day` / `cdr_summary_month` | Precalculados por cron nightly — ASR, ALOC, lucro por cliente/carrier/período. Evitan agregaciones costosas sobre `cdrs` en vivo. |
| `invoices` | Facturas por cliente y período — IGV Perú (`tax_rate` default 18%), estado (`draft`/`sent`/`paid`/`cancelled`). |

## Infraestructura

| Tabla | Propósito |
|---|---|
| `firewall_rules` | Reglas nftables gestionadas desde el panel admin (`action`, `service`, `jail` para fail2ban). |
| `sip_traces` | Mini-Homer embebido — recibe HEP3 desde Kamailio. Retención 7 días (limpieza automática vía `sip-hep.service`). |
| `settings` | Configuración global key-value. |

## Relaciones clave

```
customers ──< customer_ips
customers ──< customer_carriers >── carriers ──> carriers (failover_id, self-ref)
rate_plans ──< rates >── prefixes
carriers ──< carrier_rates >── prefixes
customers ──< cdrs / cdrs_failed / active_calls
customers ──< invoices
```

## Por qué no hace falta migrar nada aquí

El anti-patrón que forzó la migración en VoxiDet (`param1-4` VARCHAR genéricos
reusados con significado distinto según el modo de llamada) no existe en este
schema — cada tabla fue diseñada con columnas dedicadas desde el inicio. Este
documento es solo para tener el mapa completo en un lugar central, ya que no
existía ningún ADR ni doc de esquema para el proyecto antes de esta sesión.
