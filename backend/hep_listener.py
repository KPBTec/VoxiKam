#!/usr/bin/env python3
# la plataforma anterior — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Mini-Homer embebido — receptor HEP3 UDP.

Kamailio envía cada mensaje SIP vía módulo HEP a este proceso, que los
almacena en sip_traces para visualización en el panel admin.

Mitigaciones de impacto en DB:
  - Pool dedicado (1-3 conn) independiente del pool del backend
  - Batch insert: acumula paquetes 200ms y hace un INSERT múltiple
  - Retención solo del día actual (ajustable con SIP_TRACE_DAYS, default=1)
  - Solo tráfico SIP (proto_type == 1)

Corre como kaplabilling-hep.service usando el venv y .env del backend.
"""
import asyncio
import logging
import os
import re
import socket
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

# ── Cargar .env del backend ───────────────────────────────────────────────────
_env = Path(__file__).parent / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

import aiomysql

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [kaplabilling-hep] %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("kaplabilling-hep")

HEP_HOST         = os.getenv("HEP_HOST", "127.0.0.1")
HEP_PORT         = int(os.getenv("HEP_PORT", "9060"))
TRACE_RETAIN_DAYS = int(os.getenv("SIP_TRACE_DAYS", "1"))
BATCH_MS         = 200   # flush batch cada N milisegundos

_u = urlparse(os.getenv("DATABASE_URL", ""))
_DB = dict(
    host=_u.hostname or "127.0.0.1",
    port=_u.port or 3306,
    user=_u.username or "kaplabilling",
    password=_u.password or "",
    db=(_u.path or "/kaplabilling").lstrip("/"),
    charset="utf8mb4",
    autocommit=True,
)

_pool: aiomysql.Pool | None = None


async def _get_pool() -> aiomysql.Pool:
    global _pool
    if _pool is None:
        # Pool pequeño y dedicado — no comparte conexiones con el backend
        _pool = await aiomysql.create_pool(**_DB, minsize=1, maxsize=3)
    return _pool


# ── HEP3 parser ───────────────────────────────────────────────────────────────

def _parse_hep3(data: bytes) -> dict:
    if len(data) < 6 or data[:4] != b"HEP3":
        return {}
    total = struct.unpack("!H", data[4:6])[0]
    offset, r = 6, {}
    while offset + 6 <= min(total, len(data)):
        try:
            _, typ, chunk_len = struct.unpack("!HHH", data[offset:offset + 6])
        except struct.error:
            break
        if chunk_len < 6 or offset + chunk_len > len(data):
            break
        val = data[offset + 6:offset + chunk_len]
        offset += chunk_len
        try:
            if   typ == 3:  r["src_ip"]     = socket.inet_ntoa(val)
            elif typ == 4:  r["dst_ip"]     = socket.inet_ntoa(val)
            elif typ == 7:  r["src_port"]   = struct.unpack("!H", val)[0]
            elif typ == 8:  r["dst_port"]   = struct.unpack("!H", val)[0]
            elif typ == 9:  r["ts_sec"]     = struct.unpack("!I", val)[0]
            elif typ == 10: r["ts_usec"]    = struct.unpack("!I", val)[0]
            elif typ == 11: r["proto_type"] = val[0]     # 1 = SIP
            elif typ == 15: r["payload"]    = val.decode("utf-8", errors="replace")
            elif typ == 17: r["call_id"]    = val.decode("utf-8", errors="replace")
        except Exception:
            pass
    return r


_CALL_ID_RE    = re.compile(r"^Call-ID:\s*(.+)$",                 re.MULTILINE | re.IGNORECASE)
_FROM_RE       = re.compile(r"^From:.*?sip:([^@>;\s]+)",          re.MULTILINE | re.IGNORECASE)
_TO_RE         = re.compile(r"^To:.*?sip:([^@>;\s]+)",            re.MULTILINE | re.IGNORECASE)
_UA_RE         = re.compile(r"^User-Agent:\s*(.+)$",              re.MULTILINE | re.IGNORECASE)
_VIA_RE        = re.compile(r"^Via:.*?;branch=([^\s;,\r\n]+)",   re.MULTILINE | re.IGNORECASE)
_CSEQ_RE       = re.compile(r"^CSeq:\s*(.+)$",                   re.MULTILINE | re.IGNORECASE)
_REASON_RE     = re.compile(r"^Reason:\s*(.+)$",                  re.MULTILINE | re.IGNORECASE)
_REQ_URI_RE    = re.compile(r"^(?:INVITE|BYE|CANCEL|ACK|OPTIONS|REGISTER)\s+(sip:[^\s]+)", re.IGNORECASE)


def _extract_call_id(payload: str) -> str:
    m = _CALL_ID_RE.search(payload)
    return m.group(1).strip() if m else ""


def _hdr(pattern: re.Pattern, payload: str, maxlen: int = 80) -> str | None:
    m = pattern.search(payload)
    return m.group(1).strip()[:maxlen] if m else None


def _sip_summary(payload: str):
    line = (payload.split("\r\n", 1)[0] if "\r\n" in payload
            else payload.split("\n", 1)[0]).strip()
    if line.upper().startswith("SIP/2.0"):
        parts = line.split(" ", 2)
        try:
            return None, int(parts[1])
        except (IndexError, ValueError):
            return None, None
    return (line.split(" ", 1)[0].upper() or None), None


# ── Batch insert ──────────────────────────────────────────────────────────────

_queue: list[tuple] = []

_INSERT_BATCH = (
    "INSERT LOW_PRIORITY INTO sip_traces "
    "(call_id, captured_at, src_ip, src_port, dst_ip, dst_port, "
    " sip_method, sip_status, from_uri, to_uri, "
    " request_uri, user_agent, via_branch, cseq, reason, raw_message) VALUES "
)


async def _flush_loop():
    """Hace flush del batch cada BATCH_MS ms con un solo INSERT múltiple."""
    while True:
        await asyncio.sleep(BATCH_MS / 1000)
        if not _queue:
            continue
        batch, _queue[:] = _queue[:], []
        try:
            placeholders = ",".join(["(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"] * len(batch))
            flat = [v for row in batch for v in row]
            pool = await _get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(_INSERT_BATCH + placeholders, flat)
        except Exception as e:
            log.warning("Batch flush error: %s", e)


def _enqueue(pkt: dict) -> None:
    payload = pkt.get("payload") or ""
    if not payload:
        return
    # Solo protocolo SIP (proto_type 1); ignora RTCP, DNS, etc.
    if pkt.get("proto_type", 1) != 1:
        return
    call_id = (pkt.get("call_id") or _extract_call_id(payload)).strip()[:255]
    if not call_id:
        return

    method, status = _sip_summary(payload)
    is_req   = method is not None
    from_uri    = _hdr(_FROM_RE,    payload) if is_req else None
    to_uri      = _hdr(_TO_RE,      payload) if is_req else None
    request_uri = _hdr(_REQ_URI_RE, payload, 180) if is_req else None
    user_agent  = _hdr(_UA_RE,      payload, 120)
    via_branch  = _hdr(_VIA_RE,     payload, 80)
    cseq        = _hdr(_CSEQ_RE,    payload, 40)
    reason      = _hdr(_REASON_RE,  payload, 80)
    ts_sec  = pkt.get("ts_sec", 0)
    ts_usec = pkt.get("ts_usec", 0)
    captured_at = (
        datetime.fromtimestamp(ts_sec + ts_usec / 1e6, tz=timezone.utc).replace(tzinfo=None)
        if ts_sec else datetime.utcnow()
    )
    _queue.append((
        call_id, captured_at,
        pkt.get("src_ip", ""), pkt.get("src_port"),
        pkt.get("dst_ip", ""), pkt.get("dst_port"),
        method, status, from_uri, to_uri,
        request_uri, user_agent, via_branch, cseq, reason,
        payload[:65000],  # cap raw_message al límite TEXT de MySQL
    ))


# ── Protocol ──────────────────────────────────────────────────────────────────

class _HEPProtocol(asyncio.DatagramProtocol):
    def datagram_received(self, data: bytes, _addr):
        try:
            _enqueue(_parse_hep3(data))
        except Exception as e:
            log.debug("packet error: %s", e)

    def error_received(self, exc):
        log.warning("UDP error: %s", exc)


async def _cleanup(pool: aiomysql.Pool) -> None:
    """Elimina trazas de días anteriores (mantiene solo hoy)."""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # captured_at < CURDATE() usa el índice directamente (sin DATE())
            await cur.execute(
                "DELETE FROM sip_traces WHERE captured_at < CURDATE()"
            )
    log.info("Cleanup: trazas de días anteriores eliminadas")


async def _cleanup_loop():
    """Limpieza inicial al arrancar + cada hora (a las :00)."""
    pool = await _get_pool()
    try:
        await _cleanup(pool)
    except Exception as e:
        log.warning("Cleanup inicial error: %s", e)
    while True:
        await asyncio.sleep(3600)
        try:
            await _cleanup(pool)
        except Exception as e:
            log.warning("Cleanup error: %s", e)


async def main():
    loop = asyncio.get_event_loop()
    try:
        await loop.create_datagram_endpoint(_HEPProtocol, local_addr=(HEP_HOST, HEP_PORT))
    except OSError as e:
        log.error("No se puede hacer bind en %s:%s — %s", HEP_HOST, HEP_PORT, e)
        sys.exit(1)

    log.info("HEP3 listener en udp %s:%s | retención %d días | batch %dms",
             HEP_HOST, HEP_PORT, TRACE_RETAIN_DAYS, BATCH_MS)

    asyncio.create_task(_flush_loop())
    asyncio.create_task(_cleanup_loop())
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
