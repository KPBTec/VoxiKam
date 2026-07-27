# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
cors_state.py — orígenes CORS permitidos, como lista mutable a nivel de
módulo (no una constante). main.py se la pasa a CORSMiddleware por
referencia — agregar un origen acá con add_origin() aplica de inmediato
en el proceso corriendo, sin reiniciar el backend. Esto es lo que permite
que Sistema → Dominio de acceso (routers/system.py) cambie el FQDN sin
downtime: guarda el dominio en la tabla `settings` (fuente de verdad
persistente) y llama add_origin() para que el cambio sea efectivo ya.

Sincronizado con voxikam_reload/backend/shared/cors_state.py — ver ese
repo para el detalle de por qué existe este módulo.
"""

import os

ALLOWED_ORIGINS: list[str] = []


def seed_from_env() -> list[str]:
    """Se llama una sola vez al importar main.py. Mismo fallback que antes
    (DOMAIN/WEB_PORT de .env, sembrados por deploy.sh)."""
    origins = os.getenv("ALLOWED_ORIGINS", "").split(",")
    origins = [o for o in origins if o]
    if not origins:
        origins = [f"http://{os.getenv('DOMAIN', 'localhost')}:{os.getenv('WEB_PORT', '7666')}"]
    ALLOWED_ORIGINS[:] = origins
    return ALLOWED_ORIGINS


def add_origin(domain: str, web_port: str | int) -> None:
    """Agrega un origen sin sacar los que ya había — así un FQDN nuevo no
    tira abajo el acceso por IP que sembró el instalador."""
    origin = f"http://{domain}:{web_port}"
    if origin not in ALLOWED_ORIGINS:
        ALLOWED_ORIGINS.append(origin)
