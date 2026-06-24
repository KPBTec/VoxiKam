# la plataforma anterior — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2025 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2025 – Todos los derechos reservados.

import psutil
from fastapi import APIRouter, Depends
from auth import require_admin

router = APIRouter()


def _fmt_bytes(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


@router.get("")
async def system_stats(_=Depends(require_admin)):
    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()

    net_raw = psutil.net_io_counters(pernic=True)
    net = [
        {
            "iface":   iface,
            "rx_str":  _fmt_bytes(c.bytes_recv),
            "tx_str":  _fmt_bytes(c.bytes_sent),
        }
        for iface, c in net_raw.items()
        if iface != "lo"
    ]

    return {
        "cpu_percent":  cpu,
        "ram_percent":  mem.percent,
        "ram_used_gb":  round(mem.used  / 1024 ** 3, 2),
        "ram_total_gb": round(mem.total / 1024 ** 3, 1),
        "net": net,
    }
