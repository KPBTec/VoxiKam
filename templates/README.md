# templates/

Plantillas **Jinja2 de runtime** — se renderizan en install.sh (via gen_configs.py) o durante la ejecución del sistema (gen_nftables.py).

**Regla:** Esta carpeta es SOLO para templates que necesitan Jinja2 (loops, condicionales, muchas variables). Las configs estáticas (nginx, nftables base, rtpengine) van en sus propias carpetas con `__PLACEHOLDER__` + `sed`.

## Archivos

### backend.env.j2
Genera `backend/.env`. Variables disponibles: todas las del CLI de gen_configs.py.

```
DATABASE_URL=mysql+aiomysql://{{ db_user }}:{{ db_pass }}@{{ db_host }}:{{ db_port }}/{{ db_name }}
JWT_SECRET={{ jwt_secret }}
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=480
PUBLIC_IP={{ public_ip }}
PRIVATE_IP={{ private_ip }}
INSTALL_DIR={{ install_dir }}
LOG_DIR={{ log_dir }}
```

### frontend.env.j2
Genera `frontend/.env.local`. Se bake en el bundle de Next.js durante `npm run build`.

```
NEXT_PUBLIC_API_URL=http://{{ domain }}:{{ web_port }}/api
```

**Importante:** debe generarse ANTES del `npm run build`. En install.sh esto ocurre en PASO 8, build en PASO 10.

### nftables-dynamic.j2
Renderizado por `gen_nftables.py` en runtime cada 5 minutos. Lee IPs de DB y genera los sets de nftables.

```jinja2
{% if ips %}
define {{ set_name }} = { {{ ips | join(', ') }} }
ip saddr ${{ set_name }} udp dport { 5060, 20000-40000 } accept
{% endif %}
```

Si no hay IPs para un grupo, no genera el bloque (evita sets vacíos que nft rechaza).

## Variables en gen_configs.py

Todas las variables disponibles para `backend.env.j2` y `frontend.env.j2`:

| Variable | Origen |
|---|---|
| `public_ip` | Detectado/ingresado en install |
| `private_ip` | Detectado/ingresado en install |
| `private_net` | Calculado de private_ip |
| `mgmt_ip` | Ingresado en install |
| `web_port` | Ingresado en install (default 7666) |
| `domain` | Ingresado en install |
| `db_host` | Siempre 127.0.0.1 |
| `db_port` | Aleatorio 33100-33999 |
| `db_name` | Siempre sip_platform |
| `db_user` | Siempre kaplabilling |
| `db_pass` | Aleatorio generado en install |
| `jwt_secret` | Aleatorio hex32 |
| `install_dir` | Path del repo |
| `log_dir` | /kaplabilling-install/logs-configs |

---

> © 2026 [KPBTec](https://github.com/KPBTec) · Ver [Licencia y Autoría](../AUTHORS.md)
