# db/

Schema y seed inicial para MariaDB 10.11+.

## Archivos

| Archivo | Propósito |
|---|---|
| `schema.sql` | Crea las 16 tablas con `IF NOT EXISTS` — idempotente |
| `seed.sql` | Datos iniciales: admin user, plan tarifario, 23 prefijos PE+intl, tarifas de ejemplo |

## Cómo aplicar manualmente

```bash
# Obtener credenciales
cat /kaplabilling-install/logs-configs/credentials.conf

MC="mysql --user=kaplabilling --password=<DB_PASS> --host=127.0.0.1 --port=<DB_PORT>"
$MC sip_platform < schema.sql
$MC sip_platform < seed.sql
```

## Las 16 tablas

```
users              ← login admin + clientes (role: admin|client)
customers          ← trunks SIP (balance, calllimit, cpslimit, techprefix)
customer_ips       ← IPs autorizadas por cliente → nftables
customer_carriers  ← qué carrier usa cada cliente (N:M)
carriers           ← providers SIP salientes (host, port, dispatcher_group)
carrier_rates      ← lo que me COBRA el carrier (buy_rate por prefijo)
prefixes           ← catálogo global de destinos (511=Lima, 519=Móvil, 1=USA...)
prefix_lengths     ← optimización de longest-prefix-match (Magnus pattern)
rate_plans         ← planes tarifarios (nombre + currency)
rates              ← lo que COBRO al cliente (sell rate por prefijo y plan)
cdrs               ← historial llamadas contestadas (lucro = GENERATED ALWAYS)
cdrs_failed        ← llamadas fallidas (separadas para no inflar cdrs)
active_calls       ← llamadas en curso (INVITE → BYE)
cdr_summary_day    ← pre-agregado diario (cron 00:05)
cdr_summary_month  ← pre-agregado mensual
firewall_rules     ← IPs ALLOW/DENY/JAIL desde panel web
invoices           ← facturas con PDF path
settings           ← KV global (platform_name, platform_version, tax_rate, sbc_domain, etc.)
```

## Lógica de billing: longest-prefix-match

Cuando llega un BYE de Kamailio a `/api/admin/cdrs/ingest`, el backend busca la tarifa más específica:

```sql
SELECT r.rateinitial, r.initblock, r.billingblock
FROM rates r JOIN prefixes p ON r.prefix_id = p.id
WHERE :dst LIKE CONCAT(p.prefix, '%')
  AND r.rate_plan_id = :plan_id
ORDER BY LENGTH(p.prefix) DESC
LIMIT 1
```

Ejemplo: para `51987654321` (Claro Perú):
- `51` → 0.120 PEN/min (Peru Fijo)
- `519` → 0.250 PEN/min (Peru Móvil) ← más específico, gana
- `5119` → (si existe) ganaría sobre `519`

## Columna lucro (GENERATED)

```sql
lucro DECIMAL(10,6) GENERATED ALWAYS AS (sessionbill - buycost) STORED
```

No se escribe directamente. MariaDB la calcula automáticamente. Se puede leer y filtrar en queries pero no se hace `INSERT/UPDATE` sobre ella.

## Valores ENUM importantes

```sql
-- cdrs.disposition → usar con underscore, sin espacios:
ENUM('ANSWERED', 'NO_ANSWER', 'BUSY', 'FAILED')

-- invoices.status:
ENUM('draft', 'sent', 'paid', 'cancelled')

-- customers.status:
ENUM('active', 'suspended', 'expired')
```

## Seed: placeholders que reemplaza install.sh

```sql
-- seed.sql contiene:
'__ADMIN_EMAIL__'       ← email ingresado en install
'__ADMIN_HASH__'        ← hash bcrypt generado con venv/bin/python3 (bcrypt directo, sin passlib)
'__PUBLIC_IP__'         ← IP pública detectada
'__PRIVATE_IP__'        ← IP privada detectada
'__SBC_DOMAIN__'        ← dominio ingresado en install
'__PLATFORM_NAME__'     ← leído de release.conf (PLATFORM_NAME)
'__PLATFORM_VERSION__'  ← leído de release.conf (PLATFORM_VERSION)
```

`install.sh` los reemplaza con `sed` antes de pipar a mysql (PASO 9, después de crear venv).
El PASO 7 también hace un upsert de `platform_version` en settings vía SQL directo (garantiza que upgrade actualice la versión aunque seed no se re-ejecute).

## prefix_lengths (optimización)

Tabla auxiliar con los LENGTH(prefix) distintos que existen:

```sql
INSERT INTO prefix_lengths (length, count)
SELECT LENGTH(prefix), COUNT(*) FROM prefixes GROUP BY LENGTH(prefix)
```

Kamailio puede usarla para iterar solo sobre longitudes conocidas en lugar de hacer LIKE sobre todos los prefijos. Actualizar al agregar/quitar prefijos.

---

> © 2026 [KPBTec](https://github.com/KPBTec) · Ver [Licencia y Autoría](../AUTHORS.md)
