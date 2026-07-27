# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Lee /var/lib/voxikam/hep_stats.json, escrito cada 5s por hep_listener.py
(_stats_loop) — visibilidad real de las colas SIP/RTCP del mini-Homer para
saber si el volumen de llamadas está saturando el proceso, en vez de adivinar.
"""
import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends

from auth import require_admin

router = APIRouter()

_STATS_FILE = Path("/var/lib/voxikam/hep_stats.json")
_STALE_AFTER_SECONDS = 30  # se escribe cada 5s — más de esto y el proceso está colgado/caído


def _read_stats() -> dict:
    try:
        return json.loads(_STATS_FILE.read_text())
    except Exception:
        return {}


def _is_fresh(stats: dict) -> bool:
    ts = stats.get("ts")
    if not ts:
        return False
    try:
        age = (datetime.now() - datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")).total_seconds()
    except ValueError:
        return False
    return age <= _STALE_AFTER_SECONDS


@router.get("")
async def hep_stats(_=Depends(require_admin)):
    stats = _read_stats()
    return {**stats, "available": _is_fresh(stats)}
