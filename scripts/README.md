# scripts/

Scripts Python que corren como usuario `kaplabilling`. Todos leen `/etc/kaplabilling.conf` para encontrar `INSTALL_DIR` sin hardcodear paths.

## Patrón común

```python
# Todos los scripts arrancan así:
marker = Path("/etc/kaplabilling.conf")
config = dict(line.split("=", 1) for line in marker.read_text().splitlines()
              if "=" in line and not line.startswith("#"))
install_dir = Path(config["INSTALL_DIR"])
load_dotenv(install_dir / "backend" / ".env")
```

Si el marker no existe (modo dev), hacen fallback a `Path(__file__).parent.parent`.

## Scripts de runtime

### gen_configs.py
**Cuándo:** install.sh PASO 8, una sola vez.
**Qué hace:** Recibe todos los valores de configuración como argumentos CLI y renderiza las plantillas Jinja2:
- `templates/backend.env.j2` → `backend/.env`
- `templates/frontend.env.j2` → `frontend/.env.local`

```bash
python3 gen_configs.py --public-ip X --private-ip Y --domain Z ...
```

### gen_nftables.py
**Cuándo:** Cron cada 5 minutos (`*/5 * * * *`) y cuando el admin cambia IPs desde el panel.
**Qué hace:**
1. Lee DB → `customer_ips` y carrier IPs
2. Renderiza `templates/nftables-dynamic.j2` con las IPs
3. Escribe `/etc/nftables.d/carriers.nft` y `/etc/nftables.d/customers.nft`
4. Ejecuta `sudo nft -f /etc/nftables.conf` para aplicar

Requiere permisos: `kaplabilling` tiene `chown` sobre `/etc/nftables.d/` (grupo) y `sudo /usr/sbin/nft` sin password.

### gen_dispatcher.py
**Cuándo:** Cron cada 5 minutos, y cuando se agrega/modifica un carrier.
**Qué hace:**
1. Lee carriers activos de DB
2. Genera `/etc/kamailio/dispatcher.list` con formato:
   ```
   <group> sip:<host>:<port> <priority>
   ```
   (group = `dispatcher_group` del carrier, generalmente 2)
3. Ejecuta `sudo kamcmd dispatcher.reload`

Requiere: `sudo /usr/sbin/kamcmd` sin password.

### cron_summary.py
**Cuándo:** Cron a las 00:05 todos los días.
**Qué hace:**
1. Agrega CDRs del día anterior en `cdr_summary_day`
2. Actualiza `cdr_summary_month` para el mes actual
3. Limpia `active_calls` con `started_at < NOW() - INTERVAL 4 HOUR` (orphans)

Los reportes del panel admin leen de estas tablas pre-calculadas para no hacer queries pesadas sobre `cdrs` directo.

## Setup scripts (setup/)

Llamados por install.sh PASOS 1-3. No ejecutar directamente.

| Script | Qué verifica/hace |
|---|---|
| `01_check_os.sh` | OS debe ser Debian. Versión ≥ 12 requerida, avisa en ≥ 13. |
| `02_disable_fw.sh` | Deshabilita y para `ufw`, `firewalld`, `iptables-persistent` antes de activar nftables. |
| `03_install_deps.sh` | Verifica y opcionalmente instala: python3, node ≥ 20, npm, nginx, nft, curl, openssl, mariadb-server. Si node < 20, instala Node 20 LTS desde nodesource. |

### `_colors.sh`
Helpers de color para el output del instalador. Expone funciones: `ok`, `err`, `warn`, `info`, `hdr`.

## Ejecución manual (como root o con sudo)

```bash
# Regenerar nftables ahora
sudo -u kaplabilling /opt/kaplabilling/venv/bin/python3 /opt/kaplabilling/scripts/gen_nftables.py

# Regenerar dispatcher ahora
sudo -u kaplabilling /opt/kaplabilling/venv/bin/python3 /opt/kaplabilling/scripts/gen_dispatcher.py

# Ver log de cron
tail -f /kaplabilling-install/logs-configs/cron.log
tail -f /kaplabilling-install/logs-configs/nft.log
tail -f /kaplabilling-install/logs-configs/dispatcher.log
```

---

> © 2026 [KPBTec](https://github.com/KPBTec) · Ver [Licencia y Autoría](../AUTHORS.md)
