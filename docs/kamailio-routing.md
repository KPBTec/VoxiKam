# Kamailio — Routing y transformación de números

La plataforma no incluye `kamailio.cfg` porque es externa, pero este documento describe
la lógica de routing que debe implementarse para que el billing funcione correctamente.

## Flujo de una llamada

```
Cliente Asterisk          SBC Kamailio              Carrier
    │                          │                       │
    │  INVITE sip:             │                       │
    │  8001<dst>@sbc           │                       │
    ├─────────────────────────>│                       │
    │                          │  1. Identifica        │
    │                          │     cliente por IP    │
    │                          │  2. Strip techprefix  │
    │                          │     8001<dst> → <dst> │
    │                          │  3. Añade outbound_   │
    │                          │     prefix del carrier│
    │                          │     <dst> → 00<dst>   │
    │                          ├──────────────────────>│
    │                          │  INVITE sip:00<dst>@  │
    │                          │  carrier:5060         │
```

## Snippet de kamailio.cfg

El siguiente bloque maneja la transformación en el `request_route`:

```kamailio
# ── INVITE: identificar cliente y normalizar número ──────────────────────────
if (is_method("INVITE") && !has_totag()) {

    # 1. Verificar que el cliente está autorizado por IP
    if (!ds_is_in_list("$si", "", "1")) {
        # Si no está en el dispatcher group 1 (Asterisk LAN), verificar en customer_ips
        sql_query("kaplabilling",
            "SELECT c.id, c.techprefix FROM customers c
             JOIN customer_ips ci ON ci.customer_id = c.id
             WHERE ci.ip = '$si' AND c.status = 'active' LIMIT 1",
            "$var(res)"
        );
        if ($var(res) == 0) {
            sl_send_reply("403", "Forbidden");
            exit;
        }
        $var(customer_id)  = $(sqlrows{s.int});  # leer customer_id
        $var(techprefix)   = ...;                # leer techprefix
    }

    # 2. Strip del techprefix del cliente
    #    El cliente envía: TECHPREFIX + NUMERO  (ej: 8001 + 51912345678)
    #    $rU tiene el user del R-URI: "800151912345678"
    if ($var(techprefix) != "" && $(rU{s.substr,0,4}) == $var(techprefix)) {
        # Alternativa con longitud dinámica:
        $var(pfx_len) = $(var(techprefix){s.len});
        $rU = $(rU{s.substr,$var(pfx_len),0});
        # Ahora $rU = "51912345678"
    }

    # 3. Seleccionar carrier por dispatcher group del cliente
    #    group = 100 + customer_id  (ver gen_dispatcher.py)
    $var(dgroup) = 100 + $var(customer_id);
    if (!ds_select_dst($var(dgroup), 4)) {
        sl_send_reply("503", "No carriers available");
        exit;
    }
    # El dispatcher añade automáticamente el outbound_prefix del carrier
    # gracias al atributo prefix= en dispatcher.list (gen_dispatcher.py lo genera)

    # 4. Registrar llamada activa en DB
    sql_query("kaplabilling",
        "INSERT INTO active_calls (call_id, customer_id, carrier_id, src_number, dst_number, started_at)
         VALUES ('$ci', $var(customer_id), carrier_id, '$fU', '$rU', NOW())",
        "$var(r)"
    );

    route(RELAY);
    exit;
}
```

## Variables importantes

| Variable Kamailio | Descripción |
|---|---|
| `$si` | IP fuente de la petición SIP |
| `$rU` | User-part del Request-URI (el número marcado) |
| `$fU` | User-part del From header (número del llamante) |
| `$ci` | Call-ID |

## Transformación del número (resumen)

```
Entrada de cliente:  8001 51912345678
                     ↑↑↑↑ ↑↑↑↑↑↑↑↑↑↑↑
                     │    └─ número destino real (E.164)
                     └─ techprefix del cliente

Tras strip:          51912345678

Carrier outbound_prefix = 00  →  kamailio + dispatcher → 0051912345678 al carrier
```

## Normalización en el billing (CDR ingest)

Aunque Kamailio haga el strip, el endpoint `/api/admin/cdrs/ingest` también
normaliza el número como fallback:

1. Strip del `techprefix` del cliente si el número llega sin procesar
2. Strip del `outbound_prefix` del carrier si Kamailio reescribió el R-URI antes del CDR

Esto garantiza que el prefix-matching de billing siempre opere sobre el número E.164 limpio
independientemente de cómo esté configurado el kamailio.cfg.

Los campos en la tabla `cdrs`:
- `dst_number` → número normalizado (sin prefijos), usado para billing y display
- `dst_number_raw` → número tal como llegó en el payload del CDR (para auditoría)
