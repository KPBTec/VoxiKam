#!/usr/bin/env python3
# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Alerta de infraestructura — el único mecanismo del proyecto que EMPUJA un
correo cuando algo de infra (no de negocio) se rompe, en vez de esperar a
que alguien abra el panel admin a mirar.

Antes de esto, todo el monitoreo (Sistema → Salud, Sistema → Recursos,
cron_health.py) era pull-only: si un cron se colgaba a las 3am o el disco se
llenaba un domingo, nadie se enteraba hasta que algo peor pasaba (un insert
de CDR fallando, por ejemplo).

Corre como root (a diferencia del backend, que corre como `voxikam` sin
privilegios) — a propósito: así puede leer también el log de
cron_dlg_stats.py, que corre como root y cron_health.py excluye
explícitamente porque el backend no puede leerlo. Reimplementa la lógica de
staleness de backend/routers/cron_health.py en vez de importarla — evitar
acoplar un script standalone a un router de FastAPI (auth.py, dependencias
async, etc.) que no necesita para esto. Si cron_health.py cambia sus
umbrales, actualizar acá también.

Uso (vía cron, ver cron/voxikam):
    venv/bin/python3 scripts/cron_infra_alert.py
"""
import json
import os
import smtplib
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path

import pymysql
from dotenv import load_dotenv

_marker = Path("/etc/voxikam.conf")
if _marker.exists():
    for _line in _marker.read_text().splitlines():
        if _line.startswith("INSTALL_DIR="):
            _install = Path(_line.split("=", 1)[1].strip())
            break
    else:
        _install = Path(__file__).parent.parent
else:
    _install = Path(__file__).parent.parent

load_dotenv(_install / "backend" / ".env")

STATE_FILE = Path("/var/lib/voxikam/infra_alert_state.json")
LOG_DIR = _install / "logs"
ROOT_LOG_DIR = Path(os.getenv("LOG_DIR_ROOT", "/voxikam-install/logs-configs"))

# Mismo umbral de cron_health.py — mantener sincronizado si eso cambia.
_GRACE_FACTOR = 3
_ERROR_MARKERS = ("✗", "Traceback (most recent call last)", "Error:")

CRON_JOBS = [
    {"key": "cron_summary",    "log": LOG_DIR / "cron.log",             "interval_s": 86400, "label": "Resumen CDR nocturno (00:05)"},
    {"key": "cron_partitions", "log": LOG_DIR / "partitions.log",       "interval_s": 86400, "label": "Particiones cdrs/sip_traces (00:10)"},
    {"key": "cron_timeseries", "log": LOG_DIR / "timeseries.log",       "interval_s": 60,    "label": "Timeseries por minuto"},
    {"key": "cron_quality",    "log": LOG_DIR / "quality.log",          "interval_s": 60,    "label": "Calidad ASR por minuto"},
    {"key": "gen_nftables",    "log": LOG_DIR / "nft.log",              "interval_s": 300,   "label": "Sync firewall → nftables"},
    {"key": "gen_dispatcher",  "log": LOG_DIR / "dispatcher.log",       "interval_s": 300,   "label": "Sync dispatcher Kamailio"},
    {"key": "external_sync",   "log": LOG_DIR / "external_sync.log",    "interval_s": 86400, "label": "Sync externa de CDRs (00:15)"},
    {"key": "balance_block",   "log": LOG_DIR / "balance_block.log",    "interval_s": 60,    "label": "Bloqueo prepago sin saldo"},
    # dlg_stats — el único que cron_health.py NO puede ver (corre root, log
    # root-only). Acá sí, porque este script también corre como root.
    {"key": "dlg_stats",       "log": ROOT_LOG_DIR / "dlg_stats.log",   "interval_s": 60,    "label": "Snapshot Live (dlg_stats)"},
]

# Disco/memoria — no CPU/load: un umbral fijo de CPU da falsos positivos
# constantes en un SBC con tráfico variable (una hora pico no es una alerta
# real). Disco lleno y memoria agotada sí son señales limpias de "algo se va
# a romper pronto" sin necesitar ventana de tiempo/promedio.
DISK_WARN_PCT = 85
DISK_CRIT_PCT = 95
MEM_WARN_PCT = 90

# No repetir la misma alerta en cada corrida (cada 15 min, ver cron/voxikam)
# — re-avisar cada 4h mientras el problema siga activo es suficiente.
ALERT_THROTTLE_S = 4 * 3600


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state))


def _tail_last_line(path: Path, n_bytes: int = 4096) -> str | None:
    try:
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - n_bytes))
            tail = f.read().decode(errors="replace")
        lines = [l for l in tail.splitlines() if l.strip()]
        return lines[-1] if lines else None
    except Exception:
        return None


def check_crons() -> list[dict]:
    problems = []
    now = datetime.now(timezone.utc)
    for job in CRON_JOBS:
        path = job["log"]
        if not path.exists():
            problems.append({**job, "status": "missing", "detail": "el log nunca se creó"})
            continue
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        age = (now - mtime).total_seconds()
        last_line = _tail_last_line(path)
        has_error = bool(last_line) and any(m in last_line for m in _ERROR_MARKERS)
        if age > job["interval_s"] * _GRACE_FACTOR:
            problems.append({**job, "status": "stale", "detail": f"última corrida hace {int(age/60)} min (esperado cada {job['interval_s']}s)"})
        elif has_error:
            problems.append({**job, "status": "error", "detail": last_line[:200]})
    return problems


def check_resources() -> list[dict]:
    problems = []
    try:
        import psutil
    except ImportError:
        return problems

    for mount in ("/", str(_install)):
        try:
            du = psutil.disk_usage(mount)
        except Exception:
            continue
        if du.percent >= DISK_CRIT_PCT:
            problems.append({"key": f"disk:{mount}", "status": "critical", "label": f"Disco {mount}",
                              "detail": f"{du.percent:.1f}% usado ({du.free // (1024**3)}GB libres)"})
        elif du.percent >= DISK_WARN_PCT:
            problems.append({"key": f"disk:{mount}", "status": "warn", "label": f"Disco {mount}",
                              "detail": f"{du.percent:.1f}% usado ({du.free // (1024**3)}GB libres)"})

    mem = psutil.virtual_memory()
    if mem.percent >= MEM_WARN_PCT:
        problems.append({"key": "memory", "status": "warn", "label": "Memoria RAM",
                          "detail": f"{mem.percent:.1f}% en uso"})
    return problems


def get_db():
    url = os.getenv("DATABASE_URL_SYNC", "")
    parts = url.replace("mysql+pymysql://", "").split("@")
    user_pass = parts[0].split(":")
    host_port_db = parts[1].split("/")
    host_port = host_port_db[0].split(":")
    return pymysql.connect(
        host=host_port[0],
        port=int(host_port[1]) if len(host_port) > 1 else 3306,
        user=user_pass[0], password=user_pass[1],
        database=host_port_db[1], charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def infra_alerts_enabled(conn) -> bool:
    """Toggle desde Sistema → Infraestructura. Sin fila = activado (opt-out)."""
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key_name='infra_alerts_enabled'")
    row = cur.fetchone()
    return row is None or row["value"] != "0"


def get_mail_config(conn) -> dict:
    cur = conn.cursor()
    cur.execute("SELECT key_name, value FROM settings WHERE key_name IN "
                "('mail_provider','resend_api_key','alert_from_email','alert_notify_email',"
                "'smtp_host','smtp_port','smtp_username','smtp_password','smtp_encryption')")
    stored = {r["key_name"]: r["value"] for r in cur.fetchall()}
    return {
        "provider":   stored.get("mail_provider") or "resend",
        "api_key":    stored.get("resend_api_key") or os.getenv("RESEND_API_KEY", ""),
        "from_email": stored.get("alert_from_email") or os.getenv("ALERT_FROM_EMAIL", "no-reply@kpbtec.com"),
        "to_email":   stored.get("alert_notify_email") or os.getenv("ADMIN_EMAIL", "admin@localhost"),
        "smtp_host": stored.get("smtp_host") or "", "smtp_port": int(stored.get("smtp_port") or 587),
        "smtp_username": stored.get("smtp_username") or "", "smtp_password": stored.get("smtp_password") or "",
        "smtp_encryption": stored.get("smtp_encryption") or "tls",
    }


def alert_html(title: str, rows: list[tuple[str, str]]) -> str:
    import html as _html
    rows_html = "".join(
        f'<tr><td style="padding:8px 0;color:#5b7390;font-size:13px;width:220px;">{_html.escape(str(k))}</td>'
        f'<td style="padding:8px 0;color:#e7ecf3;font-size:13px;">{_html.escape(str(v))}</td></tr>'
        for k, v in rows
    )
    safe_title = _html.escape(title)
    return f"""<div style="font-family:sans-serif;max-width:600px;margin:0 auto;background:#070b14;">
      <div style="background:#0d1526;padding:24px;border-radius:12px 12px 0 0;border:1px solid #1a2744;border-bottom:0;">
        <h1 style="color:#dd8b3d;margin:0;font-size:18px;">{safe_title}</h1></div>
      <div style="background:#070b14;border:1px solid #1a2744;border-top:0;border-radius:0 0 12px 12px;padding:20px 24px;">
        <table style="width:100%;border-collapse:collapse;">{rows_html}</table></div></div>"""


def send_email(cfg: dict, subject: str, html: str) -> bool:
    if cfg["provider"] == "smtp":
        if not cfg["smtp_host"] or not cfg["smtp_username"]:
            return False
        msg = MIMEText(html, "html")
        msg["From"] = f"VoxiKam <{cfg['from_email']}>"
        msg["To"] = cfg["to_email"]
        msg["Subject"] = subject
        try:
            with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"], timeout=20) as s:
                if cfg["smtp_encryption"] == "tls":
                    s.starttls()
                if cfg["smtp_username"]:
                    s.login(cfg["smtp_username"], cfg["smtp_password"])
                s.send_message(msg)
            return True
        except Exception as e:
            print(f"send_email (smtp) falló: {e}")
            return False

    if not cfg["api_key"]:
        print("send_email: sin API key de Resend configurada — no se pudo alertar")
        return False
    import httpx
    try:
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {cfg['api_key']}"},
            json={"from": f"VoxiKam <{cfg['from_email']}>", "to": [cfg["to_email"]], "subject": subject, "html": html},
            timeout=20.0,
        )
        return resp.status_code < 300
    except Exception as e:
        print(f"send_email (resend) falló: {e}")
        return False


STATUS_FILE = Path("/var/lib/voxikam/infra_alert_status.json")


def _write_status(problems: list[dict], enabled: bool, mailed: bool) -> None:
    """Estado SIEMPRE actualizado (haya o no problemas) — leído por
    GET /admin/system/infra (Sistema → Infraestructura) para mostrar
    'última verificación: hace N min' incluso cuando todo está bien."""
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps({
        "last_check": datetime.now(timezone.utc).isoformat(),
        "enabled": enabled,
        "problems": [{"key": p["key"], "label": p.get("label", p["key"]),
                      "status": p["status"], "detail": p.get("detail", "")} for p in problems],
        "last_mail_sent": mailed,
    }))


def main():
    cron_problems = check_crons()
    resource_problems = check_resources()
    all_problems = cron_problems + resource_problems

    conn = get_db()
    try:
        enabled = infra_alerts_enabled(conn)
    finally:
        conn.close()

    state = _load_state()
    now_ts = datetime.now(timezone.utc).timestamp()

    to_alert = []
    active_keys = set()
    for p in all_problems:
        key = p["key"]
        active_keys.add(key)
        last_alerted = state.get(key, 0)
        if now_ts - last_alerted >= ALERT_THROTTLE_S:
            to_alert.append(p)
            state[key] = now_ts

    # Limpiar del estado lo que ya se resolvió — la próxima vez que reaparezca, alerta de nuevo sin esperar el throttle completo
    for key in list(state.keys()):
        if key not in active_keys:
            del state[key]

    if not to_alert or not enabled:
        _save_state(state)
        _write_status(all_problems, enabled, mailed=False)
        if to_alert and not enabled:
            print(f"{len(to_alert)} problema(s) detectados pero las alertas por correo están desactivadas desde el panel (Sistema → Infraestructura)")
        return

    print(f"{len(to_alert)} problema(s) de infraestructura detectados — enviando alerta")
    conn = get_db()
    try:
        cfg = get_mail_config(conn)
    finally:
        conn.close()

    rows = []
    for p in to_alert:
        label = p.get("label", p["key"])
        rows.append((label, f"[{p['status'].upper()}] {p.get('detail', '')}"))

    ok = send_email(
        cfg,
        subject=f"VoxiKam — {len(to_alert)} alerta(s) de infraestructura",
        html=alert_html("Alerta de infraestructura", rows),
    )
    print("Correo enviado" if ok else "No se pudo enviar el correo (ver arriba)")
    _save_state(state)
    _write_status(all_problems, enabled, mailed=ok)


if __name__ == "__main__":
    main()
