# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Capas de seguridad de la aplicación:
  - Security headers en todas las respuestas
  - Rate limiting por IP (en memoria, sin Redis)
  - Bloqueo de User-Agents maliciosos
  - Log de intentos de acceso fallidos
"""
import time
from collections import defaultdict
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# ── Rate limiting en memoria ──────────────────────────────────────────────────
# Ventana deslizante por IP: max requests en window_seconds
RATE_LIMITS = {
    "/api/auth/login": (10,  60),   # 10 intentos / 60s (anti-brute-force)
    "/api/":           (300, 60),   # 300 req / 60s para el resto de la API
}
_counters: dict[str, list[float]] = defaultdict(list)

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
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
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
            return JSONResponse({"detail": "Forbidden"}, status_code=403)

        # Rate limiting
        now = time.monotonic()
        for prefix, (max_req, window) in RATE_LIMITS.items():
            if path.startswith(prefix):
                key = f"{client_ip}:{prefix}"
                _counters[key] = [t for t in _counters[key] if now - t < window]
                if len(_counters[key]) >= max_req:
                    return JSONResponse(
                        {"detail": "Too many requests — intenta más tarde"},
                        status_code=429,
                        headers={"Retry-After": str(window)},
                    )
                _counters[key].append(now)
                break

        response = await call_next(request)

        # Agregar security headers a TODAS las respuestas
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value

        return response
