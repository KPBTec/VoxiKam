# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
sync_runner.py — Wrapper de subprocess.Popen para gen_dispatcher.py / gen_nftables.py
/ backfill_prefix_matched.py, que los routers admin disparan tras cualquier cambio
de config (carrier, grupo, cliente, firewall, LAN peer, portal reseller).

Auditoría v2.55 (workflow multi-agente): antes cada router hacía
subprocess.Popen(...) fire-and-forget puro, sin chequear el resultado — si el
script fallaba (excepción, DB caída, permiso denegado) no quedaba ninguna
señal, ni en el log ni en el panel: dispatcher/nftables quedaban
desincronizados hasta el próximo cron de 5 minutos, sin que el operador se
enterara. Este helper no cambia el timing (el endpoint sigue respondiendo al
toque, sin esperar el proceso) — solo agrega un hilo liviano que espera el
resultado en paralelo y deja un WARNING en el log si el script falla o cuelga.
"""

import logging
import subprocess
import sys
import threading
from pathlib import Path

log = logging.getLogger("voxikam.sync")

_TIMEOUT_S = 30


def run_sync(script: Path, *extra_args: str, timeout: float = _TIMEOUT_S) -> None:
    args = [sys.executable, str(script), *extra_args]
    label = script.name
    try:
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except OSError:
        log.exception("run_sync: no se pudo lanzar %s", label)
        return
    threading.Thread(target=_watch, args=(proc, label, timeout), daemon=True).start()


def _watch(proc: subprocess.Popen, label: str, timeout: float) -> None:
    try:
        _, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        log.warning("run_sync: %s no terminó en %ss (sigue corriendo en background, no se mató)", label, timeout)
        return
    if proc.returncode != 0:
        log.warning("run_sync: %s terminó con código %s: %s", label, proc.returncode, (stderr or "").strip()[-2000:])
