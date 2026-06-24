# systemd/

Unit files para los dos servicios de la plataforma. Contienen `__INSTALL_DIR__` como placeholder — install.sh los procesa con `sed` y los copia a `/etc/systemd/system/`.

## Servicios

### sip-backend.service
- **Ejecuta:** `uvicorn main:app --host 127.0.0.1 --port 8000 --workers 2`
- **User/Group:** kaplabilling
- **WorkingDirectory:** `__INSTALL_DIR__/backend`
- **EnvironmentFile:** `__INSTALL_DIR__/backend/.env`
- **Depende de:** mariadb.service (`After` + `Requires`)
- **Restart:** always, 5s delay

### sip-frontend.service
- **Ejecuta:** `node __INSTALL_DIR__/frontend/.next/standalone/server.js`
- **User/Group:** kaplabilling
- **WorkingDirectory:** `__INSTALL_DIR__/frontend`
- **Env:** `PORT=3000`, `NODE_ENV=production`, `HOSTNAME=127.0.0.1`
- **Depende de:** sip-backend.service (`After`)
- **Restart:** always, 5s delay

## Comandos útiles

```bash
# Estado
systemctl status sip-backend sip-frontend

# Logs en vivo
journalctl -u sip-backend -f
journalctl -u sip-frontend -f

# Reiniciar
systemctl restart sip-backend
systemctl restart sip-frontend

# Tras cambios en el .service (después de editar /etc/systemd/system/*.service)
systemctl daemon-reload
systemctl restart sip-backend sip-frontend
```

## Modificar el número de workers (backend)

Editar `/etc/systemd/system/sip-backend.service`:
```ini
ExecStart=.../uvicorn main:app --host 127.0.0.1 --port 8000 --workers 4
```
Luego `systemctl daemon-reload && systemctl restart sip-backend`.

## Por qué standalone en el frontend

`output: 'standalone'` en `next.config.ts` genera un `server.js` autocontenido que no necesita `node_modules` completo para correr. Reduce el footprint en producción. Los archivos estáticos se sirven directamente por Nginx (no pasan por Node), lo que mejora el rendimiento.

---

> © 2026 [KPBTec](https://github.com/KPBTec) · Ver [Licencia y Autoría](../AUTHORS.md)
