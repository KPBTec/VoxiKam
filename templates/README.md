# templates/

Plantillas **Jinja2 de runtime** — se renderizan en deploy.sh (via gen_configs.py) o durante la ejecución del sistema (gen_nftables.py).

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
Genera `frontend/.env.local`. Se bakea en el bundle de Next.js durante `npm run build`.

**NO define `NEXT_PUBLIC_API_URL`** — a propósito. `frontend/lib/api.ts` cae a `/api`
(relativo) cuando no está seteada, y nginx ya proxea `/api/` al backend en el
mismo origen — así el frontend funciona con cualquier dominio/IP que apunte al
server, sin rebuild. Antes SÍ se horneaba una URL absoluta con `domain`/`web_port`
acá — bug real encontrado en producción: acceder por un dominio distinto al que
estaba seteado cuando se compiló rompía el frontend (fetch cross-origin bloqueado
por CORS, excepción sin manejar). Ver Sistema → Dominio de acceso para cambiar
de dominio sin tocar el frontend para nada.

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
| `db_user` | Siempre voxikam |
| `db_pass` | Aleatorio generado en install |
| `jwt_secret` | Aleatorio hex32 |
| `install_dir` | Path del repo |
| `log_dir` | /voxikam-install/logs-configs |

---

> © 2026 [KPBTec](https://github.com/KPBTec) · Ver [Licencia y Autoría](../AUTHORS.md)
