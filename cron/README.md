# cron/

Archivo crontab del sistema. install.sh aplica `sed` para reemplazar placeholders y lo copia a `/etc/cron.d/kaplabilling`.

## Archivo

`kaplabilling` — crontab con placeholders `__INSTALL_DIR__` y `__LOG_DIR__`.

## Tareas programadas

| Horario | Script | Log |
|---|---|---|
| `5 0 * * *` (00:05 diario) | `cron_summary.py` | `__LOG_DIR__/cron.log` |
| `*/5 * * * *` (cada 5 min) | `gen_nftables.py` | `__LOG_DIR__/nft.log` |
| `*/5 * * * *` (cada 5 min) | `gen_dispatcher.py` | `__LOG_DIR__/dispatcher.log` |

Todos corren como usuario `kaplabilling`.

## Ver logs

```bash
tail -f /kaplabilling-install/logs-configs/cron.log
tail -f /kaplabilling-install/logs-configs/nft.log
tail -f /kaplabilling-install/logs-configs/dispatcher.log
```

## Modificar frecuencia

Editar `/etc/cron.d/kaplabilling` directamente. No tocar `cron/kaplabilling` en el repo (solo se usa durante install). Los cambios en `/etc/cron.d/` son inmediatos, no hace falta recargar cron.

---

> © 2026 [KPBTec](https://github.com/KPBTec) · Ver [Licencia y Autoría](../AUTHORS.md)
