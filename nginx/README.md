# nginx/

Config de Nginx que actúa como reverse proxy y sirve los archivos estáticos de Next.js.

## Archivo

`kaplabilling.conf` — config con `__PLACEHOLDER__`. install.sh la copia con `apply_conf()` a `/etc/nginx/sites-available/` y crea el symlink en `sites-enabled/`.

## Placeholders usados

| Placeholder | Valor |
|---|---|
| `__PUBLIC_IP__` | IP pública del servidor |
| `__PRIVATE_IP__` | IP privada del servidor |
| `__WEB_PORT__` | Puerto de acceso web (default 7666) |
| `__INSTALL_DIR__` | Path de instalación (default /opt/kaplabilling) |
| `__DOMAIN__` | Dominio (ej: sip.kpbtec.com) |

## Locations clave

```nginx
# Archivos estáticos de Next.js (servidos directamente por Nginx, no pasan por node)
location /_next/static/ {
    alias __INSTALL_DIR__/frontend/.next/static/;
}

# API → FastAPI en :8000
location /api/ {
    proxy_pass http://127.0.0.1:8000;
    # headers X-Real-IP, X-Forwarded-For para rate limiting correcto
}

# Frontend → Next.js en :3000
location / {
    proxy_pass http://127.0.0.1:3000;
}

# Health check rápido (no pasa por proxy)
location = /health {
    return 200 "ok";
}
```

## Rate limiting

```nginx
limit_req_zone $binary_remote_addr zone=api:10m rate=60r/m;
limit_req_zone $binary_remote_addr zone=login:10m rate=10r/m;

# Aplicado en location /api/auth/login
limit_req zone=login burst=5 nodelay;

# Aplicado en location /api/
limit_req zone=api burst=20 nodelay;
```

El backend tiene su propio rate limiting en memoria como segunda capa.

## Cambiar el puerto web

Editar `/etc/nginx/sites-available/kaplabilling.conf`, cambiar `listen <WEB_PORT>`, y `systemctl reload nginx`. También actualizar `NEXT_PUBLIC_API_URL` en `frontend/.env.local` y reconstruir el frontend.

## Verificar config

```bash
nginx -t
systemctl reload nginx
```

---

## 📜 Licencia

Este proyecto está licenciado bajo los términos de la [Licencia MIT](../LICENSE), lo que permite su uso, copia, modificación y distribución con fines personales, académicos o comerciales.

> **Autoría**: Este software fue creado y es mantenido por [@KPBTec](https://github.com/KPBTec).  
> Aunque es de código abierto, se agradece el reconocimiento correspondiente en derivados o menciones públicas.

---

## 👤 Autor

Desarrollado por [@KPBTec](https://github.com/KPBTec)  
© 2025 – Todos los derechos reservados.
