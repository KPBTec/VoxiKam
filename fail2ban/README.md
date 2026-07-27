# fail2ban/

Protección contra fuerza bruta. `deploy.sh` instala fail2ban, copia estos archivos (con
sustitución de puerto SSH) y activa el servicio. Mismo módulo que se agregó en VoxiDet
esta sesión — ver también `fail2ban/README.md` de ese proyecto.

## Archivos

```
fail2ban/
  filter.d/
    voxikam-security.conf  ← regex para rechazos del backend (login, User-Agent)
  jail.d/
    voxikam.conf            ← jails sshd + voxikam-security (plantilla, __SSH_PORT__)
```

## Jails

### `sshd` (filtro estándar de fail2ban)
5 intentos fallidos en 10 min → ban 1h. Puerto = el detectado por `deploy.sh` (mismo
mecanismo que ya usa para `nftables.conf`).

### `voxikam-security` (filtro propio, `filter.d/voxikam-security.conf`)
10 rechazos en 1 min → ban 1h. **Lee journald directo** (`backend = systemd`,
`journalmatch = SYSLOG_IDENTIFIER=voxikam-backend`) — `voxikam-backend.service` ya loguea con
`StandardOutput=journal`, no hace falta archivo ni bind mount.

**Por qué NO cuenta el rate-limit de `/api/`:** el filtro solo matchea `reason=blocked_ua` y
`reason=login_failed` — un usuario legítimo nunca las dispara. El límite de `/api/auth/login`
(10/60s) y de `/api/` (300/60s) en `middleware/security.py` siguen devolviendo 429 igual, pero
eso no alimenta un ban de red: un cliente de alto tráfico normal puede tocar esos límites sin ser
un ataque, banearlo sería un auto-DoS.

## banaction — nftables, no iptables

Mismo motivo que el firewall principal: `banaction = nftables-allports` crea un set nftables
propio para IPs baneadas, sin tocar la tabla que ya gestiona `gen_nftables.py`.

## Comandos útiles

```bash
fail2ban-client status
fail2ban-client status sshd
fail2ban-client status voxikam-security
fail2ban-client set voxikam-security unbanip <IP>

# Probar el filtro contra el journal real
fail2ban-regex systemd-journal /etc/fail2ban/filter.d/voxikam-security.conf \
    --journalmatch "SYSLOG_IDENTIFIER=voxikam-backend"
```

## Pendiente (no implementado en esta sesión)

Ver IPs baneadas / desbanear desde el panel admin (como Firewall) — requiere un endpoint que
llame `fail2ban-client` (via sudo) y una sección nueva en la UI. Por ahora es solo CLI en el
servidor.
