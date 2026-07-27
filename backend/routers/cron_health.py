# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Lee los logs que ya escriben los cron jobs (cron/voxikam) — no ejecuta nada,
solo reporta si cada uno corrió a tiempo y si su última corrida tuvo errores.

dlg_stats.py queda afuera a propósito: corre como root y escribe en LOG_DIR
(root-only), que el backend (usuario voxikam) no puede leer.
"""
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends

from auth import require_admin

router = APIRouter()

LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"

CRON_JOBS = [
    {"key": "cron_summary",    "log": "cron.log",       "interval_s": 86400, "label": "Resumen CDR nocturno (00:05)"},
    {"key": "cron_partitions", "log": "partitions.log",  "interval_s": 86400, "label": "Particiones cdrs/sip_traces (00:10)"},
    {"key": "cron_timeseries", "log": "timeseries.log",  "interval_s": 60,    "label": "Timeseries por minuto"},
    {"key": "cron_quality",    "log": "quality.log",     "interval_s": 60,    "label": "Calidad ASR por minuto"},
    {"key": "gen_nftables",    "log": "nft.log",         "interval_s": 300,   "label": "Sync firewall → nftables"},
    {"key": "gen_dispatcher",  "log": "dispatcher.log",  "interval_s": 300,   "label": "Sync dispatcher Kamailio"},
    {"key": "external_sync",  "log": "external_sync.log", "interval_s": 86400, "label": "Sync externa de CDRs (00:15)"},
]

# Múltiplo del intervalo esperado antes de marcar "stale" — da margen a jitter de cron/carga.
_GRACE_FACTOR = 3
_ERROR_MARKERS = ("✗", "Traceback (most recent call last)", "Error:")


def _tail(path: Path, n_bytes: int = 4096) -> str:
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(0, size - n_bytes))
        return f.read().decode(errors="replace")


def _job_status(job: dict) -> dict:
    path = LOG_DIR / job["log"]
    if not path.exists():
        return {**job, "status": "missing", "last_run": None, "age_seconds": None, "last_line": None}

    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    age = (datetime.now(timezone.utc) - mtime).total_seconds()

    tail = _tail(path)
    lines = [l for l in tail.splitlines() if l.strip()]
    last_line = lines[-1] if lines else None
    # Solo la ÚLTIMA línea, no todo el tail de 4KB — estos jobs corren cada
    # 60s y van agregando una línea por corrida al mismo archivo, así que 4KB
    # puede cubrir 40-60 minutos de historial. Buscar el marcador en el tail
    # completo marcaba "error" indefinidamente por una falla vieja aunque las
    # corridas más recientes ya estuvieran bien — falso positivo confuso
    # (reportado: "dice hace 55s pero en rojo, no sé si está bien o mal").
    has_error = bool(last_line) and any(marker in last_line for marker in _ERROR_MARKERS)

    if age > job["interval_s"] * _GRACE_FACTOR:
        status = "stale"
    elif has_error:
        status = "error"
    else:
        status = "ok"

    return {
        **job,
        "status": status,
        "last_run": mtime.isoformat(),
        "age_seconds": int(age),
        "last_line": last_line,
    }


@router.get("")
async def cron_health(_=Depends(require_admin)):
    return [_job_status(job) for job in CRON_JOBS]
