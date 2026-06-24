# nftables/

Configuración del firewall. Dos partes: config base estática (este directorio) y archivos dinámicos generados por `gen_nftables.py`.

## Archivos

```
nftables/
  nftables.conf          ← config base con __PLACEHOLDER__, copiada a /etc/nftables.conf
  nftables.d/
    carriers.nft          ← vacío inicial — gen_nftables.py lo regenera cada 5 min
    customers.nft         ← vacío inicial — gen_nftables.py lo regenera cada 5 min
```

## nftables.conf — Estructura base

Config con `__PLACEHOLDER__`. `apply_conf()` en install.sh la copia a `/etc/nftables.conf`.

Incluye al final:
```nft
include "/etc/nftables.d/carriers.nft"
include "/etc/nftables.d/customers.nft"
```

Reglas base:
- Acepta loopback
- Acepta conexiones establecidas/relacionadas
- Permite SSH desde `__MGMT_IP__` (tu IP de gestión)
- Permite HTTPS/HTTP desde `__MGMT_IP__`
- Permite web port `__WEB_PORT__` desde internet
- Rechaza todo lo demás (politica DROP)

## nftables.d/ — Dinámico (gen_nftables.py)

`gen_nftables.py` lee IPs de DB y genera:

**carriers.nft:**
```nft
define carrier_ips = { 1.2.3.4, 5.6.7.8 }
ip saddr $carrier_ips udp dport { 5060, 20000-40000 } accept
```

**customers.nft:**
```nft
define customer_ips = { 10.100.10.20, 10.100.10.21 }
ip saddr $customer_ips udp dport { 5060, 20000-40000 } accept
```

Si no hay IPs en DB, el archivo queda vacío (sin bloques). El include de nftables.conf sigue funcionando.

## Permisos

```
/etc/nftables.conf        → root:root 600
/etc/nftables.d/          → root:kaplabilling 775  (kaplabilling escribe los .nft)
/etc/nftables.d/*.nft     → kaplabilling:kaplabilling (creados por gen_nftables.py)
```

`kaplabilling` puede ejecutar `sudo /usr/sbin/nft` sin password para aplicar la config.

## Aplicar cambios manualmente

```bash
# Verificar sintaxis
nft -c -f /etc/nftables.conf

# Aplicar
sudo nft -f /etc/nftables.conf

# Ver reglas activas
nft list ruleset

# Forzar regeneración desde DB ahora
sudo -u kaplabilling /opt/kaplabilling/venv/bin/python3 /opt/kaplabilling/scripts/gen_nftables.py
```

## Firewall panel web → nftables

El panel Admin → Firewall escribe en la tabla `firewall_rules`. `gen_nftables.py` lee esa tabla y puede agregar:
- IPs ALLOW: reglas `accept` con alta prioridad
- IPs DENY: reglas `drop` explícitas
- IPs JAIL (bloqueo temporal): igual que DENY pero con campo `jail=1`

---

> © 2026 [KPBTec](https://github.com/KPBTec) · Ver [Licencia y Autoría](../AUTHORS.md)
