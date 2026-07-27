#!/usr/bin/env python3
# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
cleanup_active_calls.py — Limpia registros zombie de active_calls.

Se llama automáticamente desde el ExecStartPost del servicio Kamailio
para que al reiniciar Kamailio (que pierde todo el estado de diálogos)
el panel no muestre llamadas activas que ya no existen.

También se puede correr manualmente:
  python3 cleanup_active_calls.py           # elimina entradas > 0 min (todas)
  python3 cleanup_active_calls.py 90        # elimina entradas > 90 min

Modo "todas" (max_minutes=0, el que dispara ExecStartPost): antes de borrar,
cada fila de active_calls representa una llamada que SÍ se contestó pero
cuyo BYE nunca le va a llegar a este Kamailio nuevo (perdió el diálogo en
memoria al reiniciar) — event_route[dialog:end] nunca corre para ella, así
que nunca se genera su CDR. Sin este script se perdía en silencio, sin
ningún rastro ni forma de saber que existió. Ahora se inserta un CDR
placeholder con disposition='RESTART_ORPHANED' (billsec/sessionbill en 0 a
propósito — no se autofactura, no sabemos la hora real de colgado) y se
manda un correo al admin para que decida a mano si corresponde cobrar.
disposition distinto de 'ANSWERED' es lo que evita que backend/main.py
::_billing_worker() (WHERE disposition='ANSWERED' AND buycost=0) intente
facturarlo solo con una duración estimada.
"""
import os
import sys
from pathlib import Path
from datetime import datetime

import httpx
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


def get_db():
    url = os.getenv("DATABASE_URL_SYNC", "")
    parts = url.replace("mysql+pymysql://", "").split("@")
    user_pass = parts[0].split(":")
    host_port_db = parts[1].split("/")
    host_port = host_port_db[0].split(":")
    return pymysql.connect(
        host=host_port[0],
        port=int(host_port[1]) if len(host_port) > 1 else 3306,
        user=user_pass[0],
        password=user_pass[1],
        database=host_port_db[1],
        charset="utf8mb4",
        autocommit=True,
    )


def _archive_orphans_as_cdrs(conn) -> list[tuple]:
    """SELECT + INSERT INTO cdrs (disposition='RESTART_ORPHANED') para cada fila
    de active_calls antes de borrarla. billsec/sessionbill quedan en 0 a propósito
    — no se autofactura una duración estimada, queda para revisión manual.
    Un INSERT fallido en una fila no debe frenar el resto ni el DELETE final."""
    cur = conn.cursor()
    cur.execute("""
        SELECT call_id, customer_id, carrier_id, src_ip, src_number, dst_number, started_at
        FROM active_calls
    """)
    rows = cur.fetchall()
    archived = []
    for row in rows:
        call_id, customer_id, carrier_id, src_ip, src_number, dst_number, started_at = row
        try:
            cur.execute("""
                INSERT INTO cdrs
                    (call_id, customer_id, carrier_id, src_ip, src_number, dst_number, dst_number_raw,
                     start_ts, answer_ts, end_ts, sessiontime, billsec, disposition)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(),
                        TIMESTAMPDIFF(SECOND, %s, NOW()), 0, 'RESTART_ORPHANED')
            """, (call_id, customer_id, carrier_id, src_ip, src_number, dst_number, dst_number,
                  started_at, started_at, started_at))
            archived.append(row)
        except Exception as e:
            print(f"  ⚠ No se pudo archivar call_id={call_id}: {e}")
    cur.close()
    return archived


def _alert_restart_orphans(conn, rows: list[tuple]) -> None:
    """Correo best-effort al admin — un fallo acá nunca debe frenar el cleanup
    (mismo criterio que backend/mailer.py::send_email())."""
    if not rows:
        return
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT key_name, value FROM settings "
            "WHERE key_name IN ('resend_api_key','alert_from_email','alert_notify_email',"
            "'alert_restart_orphans_enabled')"
        )
        cfg = dict(cur.fetchall())
        cur.close()

        # Las llamadas se archivan en cdrs siempre (eso nunca se apaga — es lo
        # que evita perder el registro). El correo sí es opcional, apagado por
        # defecto (Sistema → Correo), mismo criterio que invoices_auto_email.
        if cfg.get("alert_restart_orphans_enabled") != "1":
            print("  · alerta de reinicio desactivada (Sistema → Correo) — no se envía correo")
            return

        api_key    = cfg.get("resend_api_key") or os.getenv("RESEND_API_KEY", "")
        from_email = cfg.get("alert_from_email") or os.getenv("ALERT_FROM_EMAIL", "no-reply@kpbtec.com")
        to_email   = cfg.get("alert_notify_email") or os.getenv("ADMIN_EMAIL", "admin@localhost")
        if not api_key:
            print("  ⚠ sin RESEND_API_KEY configurada (Sistema → Correo) — alerta no enviada")
            return

        filas_html = "".join(
            f'<tr><td style="padding:6px 8px 6px 0;color:#5b7390;font-size:12px;">{call_id}</td>'
            f'<td style="padding:6px 8px;color:#e7ecf3;font-size:12px;">{src} → {dst}</td>'
            f'<td style="padding:6px 0;color:#e7ecf3;font-size:12px;">{started}</td></tr>'
            for call_id, _cid, _carid, _ip, src, dst, started in rows
        )
        html = f"""
        <div style="font-family:sans-serif;max-width:560px;margin:0 auto;background:#070b14;">
          <div style="background:#0d1526;padding:24px;border-radius:12px 12px 0 0;border:1px solid #1a2744;border-bottom:0;">
            <h1 style="color:#dd8b3d;margin:0;font-size:18px;">Kamailio se reinició con {len(rows)} llamada(s) en curso</h1>
          </div>
          <div style="background:#070b14;border:1px solid #1a2744;border-top:0;border-radius:0 0 12px 12px;padding:20px 24px;">
            <p style="color:#e7ecf3;font-size:13px;">
              No hay forma de saber la hora real de corte de estas llamadas — quedaron
              registradas en <code>cdrs</code> con <code>disposition='RESTART_ORPHANED'</code>
              y sin monto facturado. Revisar en Reportes → CDRs y decidir a mano si corresponde cobrar.
            </p>
            <table style="width:100%;border-collapse:collapse;">{filas_html}</table>
          </div>
        </div>
        """

        # Timeout corto a propósito: este script corre desde el ExecStartPost
        # de Kamailio (deploy.sh) — es síncrono para systemd, así que un colgado
        # de red acá sumaría directo al tiempo de arranque del servicio. El
        # `|| true` en el ExecStartPost ya evita que un error tumbe el arranque,
        # pero la latencia sí se siente igual.
        with httpx.Client(timeout=8.0) as client:
            resp = client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "from": f"VoxiKam <{from_email}>",
                    "to": [to_email],
                    "subject": f"VoxiKam — {len(rows)} llamada(s) interrumpida(s) por reinicio de Kamailio",
                    "html": html,
                },
            )
        if resp.status_code >= 300:
            print(f"  ⚠ Resend respondió {resp.status_code} — alerta no confirmada")
        else:
            print(f"  ✓ Alerta de reinicio enviada a {to_email}")
    except Exception as e:
        print(f"  ⚠ No se pudo enviar la alerta de reinicio: {e}")


def main():
    max_minutes = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"cleanup_active_calls.py — {ts} (max_minutes={max_minutes})")

    conn = get_db()
    try:
        cur = conn.cursor()
        if max_minutes == 0:
            # Llamado desde ExecStartPost de Kamailio: limpiar TODO
            # Kamailio acaba de reiniciar → perdió todos los diálogos → todo es zombie
            orphans = _archive_orphans_as_cdrs(conn)
            if orphans:
                print(f"  ⚠ {len(orphans)} llamada(s) huérfana(s) por el reinicio — "
                      f"archivadas en cdrs como RESTART_ORPHANED")
                _alert_restart_orphans(conn, orphans)
            cur.execute("DELETE FROM active_calls")
        else:
            cur.execute(
                "DELETE FROM active_calls WHERE TIMESTAMPDIFF(MINUTE, started_at, NOW()) > %s",
                (max_minutes,)
            )
        deleted = cur.rowcount
        if deleted:
            print(f"  ✓ {deleted} registro(s) zombie eliminado(s) de active_calls")
        else:
            print("  ✓ active_calls ya estaba limpia")
        cur.close()
    except Exception as e:
        print(f"  ✗ Error: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
