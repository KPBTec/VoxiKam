# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Capas de seguridad de la aplicación:
  - Security headers en todas las respuestas
  - Rate limiting por IP (compartido entre workers, ver rate_limit.py)
  - Bloqueo de User-Agents maliciosos
  - Log de intentos de acceso fallidos
"""
import hashlib
import logging
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from database import AsyncSessionLocal
from rate_limit import is_rate_limited

log = logging.getLogger("voxikam-security")

# ── Rate limiting ────────────────────────────────────────────────────────────
# Fixed window (ver rate_limit.py). Orden importa — es match-primero-que-
# aplica (el prefijo más específico va primero), así /api/v1/ no cae en el
# balde genérico /api/ de 300/60s.
RATE_LIMITS = {
    "/api/auth/login": (10,  60),   # 10 intentos / 60s (anti-brute-force)
    "/api/v1/":        (120, 60),   # tráfico de integraciones de clientes — más generoso, keyed por API key, no por IP
    "/api/":           (300, 60),   # 300 req / 60s para el resto de la API
}
# Prefijos cuyo bucket se key-ea por API key (X-API-Key), no por IP — un
# cliente con su propio backend no debería competir con otros clientes detrás
# del mismo NAT/proxy. Si no manda la key (o está malformada), cae a IP.
_KEYED_BY_API_KEY = {"/api/v1/"}

BLOCKED_UAS = {
    "sqlmap", "nikto", "masscan", "nmap", "zgrab",
    "dirbuster", "gobuster", "wfuzz", "hydra",
}

SECURITY_HEADERS = {
    "X-Content-Type-Options":  "nosniff",
    "X-Frame-Options":         "DENY",
    "X-XSS-Protection":        "1; mode=block",
    "Referrer-Policy":         "strict-origin-when-cross-origin",
    "Permissions-Policy":      "geolocation=(), microphone=(), camera=()",
    # Mismo CSP que nginx/voxikam.conf (que es el que realmente protege las
    # páginas — este solo cubre /api/*, principalmente JSON donde no aplica,
    # pero también /api/docs). Sin 'unsafe-eval' — no hace falta acá tampoco.
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self' data:; "
        "connect-src 'self';"
    ),
    "Server": "VoxiKam",
}


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        path      = request.url.path
        ua        = request.headers.get("user-agent", "").lower()

        # Bloquear UAs maliciosos conocidos
        if any(b in ua for b in BLOCKED_UAS):
            log.warning("SECURITY_REJECT ip=%s reason=blocked_ua path=%s", client_ip, path)
            return JSONResponse({"detail": "Forbidden"}, status_code=403)

        # Rate limiting — re-auditoría v2.56.0: migrado de dict en memoria
        # (fragmentado entre workers con --workers>1, mismo bug de fondo que
        # cors_state.ALLOWED_ORIGINS ya tuvo) a rate_limit.py, respaldado en
        # MariaDB (tabla compartida entre todos los procesos).
        for prefix, (max_req, window) in RATE_LIMITS.items():
            if path.startswith(prefix):
                if prefix in _KEYED_BY_API_KEY:
                    api_key = request.headers.get("x-api-key", "")
                    ident = hashlib.sha256(api_key.encode()).hexdigest() if api_key else f"ip:{client_ip}"
                else:
                    ident = client_ip
                key = f"{ident}:{prefix}"
                # Fail-open: si la DB tiene un hipo transitorio, un control de
                # rate limiting caído no debería tumbar TODO el tráfico de la
                # API — se loguea y se deja pasar, igual que cualquier otro
                # background task de este backend (_billing_worker, etc.).
                try:
                    async with AsyncSessionLocal() as rl_db:
                        limited = await is_rate_limited(rl_db, key, max_req, window)
                except Exception:
                    log.exception("Rate limiter: error consultando la DB, dejando pasar (fail-open)")
                    limited = False
                if limited:
                    # No se loguea como SECURITY_REJECT (no alimenta fail2ban):
                    # el login ya tiene su propio límite estricto (10/60s) y un
                    # cliente de alto tráfico normal puede tocar el límite de
                    # /api/ (300/60s) sin ser un ataque — banear por esto sería
                    # arriesgar un auto-DoS, igual que en VoxiDet.
                    return JSONResponse(
                        {"detail": "Too many requests — intenta más tarde"},
                        status_code=429,
                        headers={"Retry-After": str(window)},
                    )
                break

        response = await call_next(request)

        # Agregar security headers a TODAS las respuestas
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value

        return response
