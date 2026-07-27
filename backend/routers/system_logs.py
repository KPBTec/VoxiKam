# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Ver logs completos desde la web sin entrar por SSH — Sistema → Logs.

Hasta ahora `system-health` solo mostraba 5 líneas de preview por servicio
(`services_status.py`) o metadata de salud + última línea por cron job
(`cron_health.py`). Acá se reusan esos mismos mecanismos (journalctl -u para
servicios, tail de archivo para los .log de cron) pero con N configurable y
devolviendo el contenido completo, no solo una vista previa.

Solo lectura — mismo criterio que el resto de este archivo hermano
(services_status.py): reiniciar servicios o seguir logs en vivo por consola
sigue siendo `voxikam -r|-l` (scripts/voxikam-cli.sh), no esto.
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from auth import require_admin
from routers.services_status import _UNITS, _run
from routers.cron_health import LOG_DIR

router = APIRouter()

# fail2ban no vive en _UNITS (services_status.py es específico a servicios
# propios de VoxiKam) pero es un systemd unit real y útil para depurar sin
# SSH — se agrega acá nada más, no se toca services_status.py.
_EXTRA_UNITS = [{"key": "fail2ban", "unit": "fail2ban", "label": "Fail2ban"}]
_UNIT_BY_KEY = {u["key"]: u for u in list(_UNITS) + _EXTRA_UNITS}


@router.get("/sources")
async def list_sources(_=Depends(require_admin)):
    units = [{"id": f"unit:{u['key']}", "label": u["label"]} for u in list(_UNITS) + _EXTRA_UNITS]
    files = sorted(LOG_DIR.glob("*.log")) if LOG_DIR.exists() else []
    file_sources = [{"id": f"file:{p.name}", "label": p.name} for p in files]
    return units + file_sources


@router.get("")
async def get_logs(
    source: str = Query(...),
    lines: int = Query(100, ge=1, le=1000),
    _=Depends(require_admin),
):
    if source.startswith("unit:"):
        entry = _UNIT_BY_KEY.get(source[5:])
        if not entry:
            raise HTTPException(404, "Servicio desconocido")
        out = await _run("journalctl", "-u", entry["unit"], "-n", str(lines), "--no-pager", "-o", "cat")
        return {"source": source, "lines": [l for l in out.splitlines() if l.strip()]}

    if source.startswith("file:"):
        name = source[5:]
        # Sin path traversal: el archivo tiene que resolver exactamente
        # dentro de LOG_DIR, no alcanza con rechazar "..``/" a mano (symlinks,
        # encodings raros) — se compara el padre ya resuelto.
        base = LOG_DIR.resolve()
        path = (LOG_DIR / name).resolve()
        if path.parent != base or path.suffix != ".log" or not path.exists():
            raise HTTPException(404, "Archivo no encontrado")
        text = path.read_text(errors="replace")
        all_lines = [l for l in text.splitlines() if l.strip()]
        return {"source": source, "lines": all_lines[-lines:]}

    raise HTTPException(400, "source inválido — usar unit:<key> o file:<nombre>.log")
