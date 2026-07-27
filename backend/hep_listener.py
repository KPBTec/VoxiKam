#!/usr/bin/env python3
# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Mini-Homer embebido — receptor HEP3 UDP.

Kamailio envía cada mensaje SIP vía módulo HEP a este proceso, que los
almacena en ClickHouse (sip_platform.sip_traces) para visualización en el
panel admin — movido de MariaDB a ClickHouse porque a este volumen de
captura (paquete por paquete, no solo eventos de llamada) la tabla crecía
~8.5GB/día, insostenible en el disco del server con 90 días de retención.
La retención ahora la maneja el TTL nativo de la tabla ClickHouse (ver
backend/routers/traffic_sampling.py::set_config()), no un DELETE periódico.

Mitigaciones de impacto en DB:
  - Cliente ClickHouse dedicado, independiente del pool MySQL del backend
  - Batch insert: acumula paquetes 200ms y hace un insert múltiple
  - Solo tráfico SIP (proto_type == 1)

También recibe RTCP-JSON de RTPEngine (proto_type == 5, PROTO_RTCP_JSON — ver
rtpengine.conf `homer=`) con jitter/packet-loss por llamada, en
`_enqueue_rtcp()` — deliberadamente aislado de `_enqueue()` (SIP) con su
propio try/except en el protocolo: un bug en el parseo de RTCP nunca debe
poder afectar la captura de Trazas SIP. Este camino SÍ sigue en MariaDB
(tabla call_media_stats, sin relación con el volumen de sip_traces) — usa el
pool `aiomysql` de abajo, que ahora es exclusivo de RTCP.

Corre como voxikam-hep.service usando el venv y .env del backend.
"""
import asyncio
import json
import logging
import os
import re
import socket
import struct
import sys
import time
from datetime import datetime
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
import clickhouse_connect

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [voxikam-hep] %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("voxikam-hep")

HEP_HOST         = os.getenv("HEP_HOST", "127.0.0.1")
HEP_PORT         = int(os.getenv("HEP_PORT", "9060"))
BATCH_MS         = 200   # flush batch cada N milisegundos

# Ninguna de las dos colas (SIP ni RTCP) tenía tope — si la DB se atrasara por
# cualquier motivo (lock, red, disco), crecían sin límite hasta reventar la
# memoria del proceso. Con este tope, en vez de eso: se descartan paquetes
# nuevos y se loguea, pero el proceso sigue vivo y se recupera solo apenas la
# DB responde de nuevo — perder algo de historial durante un problema de DB es
# muchísimo mejor que un OOM que además tira abajo la captura de Trazas SIP.
_MAX_QUEUE = 20000

# Buffer de recepción del socket UDP — el default del SO puede quedar corto
# en una ráfaga (varias llamadas colgando/iniciando a la vez) y el kernel
# descarta paquetes ANTES de que Python los vea, sin dejar rastro en ninguna
# de las colas internas. Se pide un valor alto (8 MiB); si `net.core.rmem_max`
# del host es menor, el kernel lo recorta solo — no falla, solo pide de menos
# (queda logueado el valor real negociado al arrancar, ver main()).
_SO_RCVBUF_TARGET = 8 * 1024 * 1024

# Contadores para /var/lib/voxikam/hep_stats.json — visibilidad real de si
# esto alguna vez se acerca a saturarse, en vez de adivinar. Ver panel
# Dashboard → "Captura HEP" (v2.24.10).
_STATS_FILE = Path("/var/lib/voxikam/hep_stats.json")
_sip_dropped_total  = 0
_rtcp_dropped_total = 0
_last_sip_flush_ms   = 0.0
_last_rtcp_flush_ms  = 0.0
_last_sip_batch_size  = 0
_last_rtcp_batch_size = 0

_u = urlparse(os.getenv("DATABASE_URL", ""))
_DB = dict(
    host=_u.hostname or "127.0.0.1",
    port=_u.port or 3306,
    user=_u.username or "voxikam",
    password=_u.password or "",
    db=(_u.path or "/voxikam").lstrip("/"),
    charset="utf8mb4",
    autocommit=True,
)

_pool: aiomysql.Pool | None = None
_pool_lock = asyncio.Lock()


async def _get_pool() -> aiomysql.Pool:
    """
    Doble-check con lock: sin esto, si dos tareas llaman a _get_pool() antes
    de que exista el pool (ambas ven _pool is None y hacen `await create_pool`),
    se crean dos pools y uno queda huérfano sin cerrarse nunca. Exclusivo de
    RTCP/call_media_stats desde la migración de sip_traces a ClickHouse.
    """
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                # Pool pequeño y dedicado — no comparte conexiones con el backend
                _pool = await aiomysql.create_pool(**_DB, minsize=1, maxsize=3)
    return _pool


_ch_u = urlparse(os.getenv("CLICKHOUSE_URL", ""))
_CH = dict(
    host=_ch_u.hostname or "127.0.0.1",
    port=_ch_u.port or 8123,
    username=_ch_u.username or "voxikam",
    password=_ch_u.password or "",
    database=(_ch_u.path or "/sip_platform").lstrip("/"),
)

_ch_client = None
_ch_client_lock = asyncio.Lock()

# Id monotónico para sip_traces en ClickHouse (ya no hay AUTO_INCREMENT de
# MySQL) — sembrado con time_ns() al arrancar el proceso, así queda siempre
# por encima de cualquier id histórico de MySQL (BIGINT, mucho más chico) y
# nunca colisiona con lo migrado por scripts/migrate_sip_traces_to_clickhouse.py.
_next_id = time.time_ns()


async def _get_ch_client():
    """Mismo patrón doble-check-con-lock que _get_pool(), para el cliente ClickHouse."""
    global _ch_client
    if _ch_client is None:
        async with _ch_client_lock:
            if _ch_client is None:
                _ch_client = await clickhouse_connect.get_async_client(**_CH)
    return _ch_client


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

_COLUMNS = (
    "id", "call_id", "captured_at", "src_ip", "src_port", "dst_ip", "dst_port",
    "sip_method", "sip_status", "from_uri", "to_uri",
    "request_uri", "user_agent", "via_branch", "cseq", "reason", "raw_message",
)


async def _flush_loop():
    """Hace flush del batch cada BATCH_MS ms con un solo insert múltiple a ClickHouse."""
    global _last_sip_flush_ms, _last_sip_batch_size
    while True:
        await asyncio.sleep(BATCH_MS / 1000)
        if not _queue:
            continue
        batch, _queue[:] = _queue[:], []
        t0 = time.monotonic()
        try:
            client = await _get_ch_client()
            await client.insert(table="sip_traces", data=batch, column_names=_COLUMNS)
        except Exception as e:
            log.warning("Batch flush error: %s", e)
        finally:
            _last_sip_flush_ms  = (time.monotonic() - t0) * 1000
            _last_sip_batch_size = len(batch)


def _enqueue(pkt: dict) -> None:
    global _sip_dropped_total, _next_id
    payload = pkt.get("payload") or ""
    if not payload:
        return
    # Solo protocolo SIP (proto_type 1); ignora RTCP, DNS, etc.
    if pkt.get("proto_type", 1) != 1:
        return
    if len(_queue) >= _MAX_QUEUE:
        _sip_dropped_total += 1
        log.warning("Cola SIP llena (%d) — la DB no sigue el ritmo, se descartan paquetes nuevos", len(_queue))
        return
    call_id = (pkt.get("call_id") or _extract_call_id(payload)).strip()[:255]
    if not call_id:
        return

    method, status = _sip_summary(payload)
    is_req   = method is not None
    # from_uri/to_uri son String no-nullable en ClickHouse (el índice
    # ngrambf_v1 no soporta Nullable) — '' en vez de None para respuestas o
    # si el regex no matchea.
    from_uri    = (_hdr(_FROM_RE, payload) if is_req else None) or ""
    to_uri      = (_hdr(_TO_RE,   payload) if is_req else None) or ""
    request_uri = _hdr(_REQ_URI_RE, payload, 180) if is_req else None
    user_agent  = _hdr(_UA_RE,      payload, 120)
    via_branch  = _hdr(_VIA_RE,     payload, 80)
    cseq        = _hdr(_CSEQ_RE,    payload, 40)
    reason      = _hdr(_REASON_RE,  payload, 80)
    ts_sec  = pkt.get("ts_sec", 0)
    ts_usec = pkt.get("ts_usec", 0)
    # Hora LOCAL del server (no UTC) — mismo criterio que cdrs.start_ts, que
    # se llena con NOW() de MySQL (hora local del server, sin tz explícita).
    # fromtimestamp() sin tz= convierte el epoch (siempre UTC) a la hora local
    # del sistema; antes se forzaba a UTC y se guardaba naive, quedando 5h
    # adelantado de la hora real en el panel (que nunca hizo conversión de tz).
    captured_at = (
        datetime.fromtimestamp(ts_sec + ts_usec / 1e6)
        if ts_sec else datetime.now()
    )
    _next_id += 1
    _queue.append((
        _next_id, call_id, captured_at,
        pkt.get("src_ip", ""), pkt.get("src_port"),
        pkt.get("dst_ip", ""), pkt.get("dst_port"),
        method, status, from_uri, to_uri,
        request_uri, user_agent, via_branch, cseq, reason,
        payload[:65000],  # tope defensivo — un SIP real nunca se acerca a esto
    ))


# ── RTCP (calidad de medio) — aislado a propósito de lo de arriba ─────────────

PROTO_RTCP_JSON = 5  # PROTO_RTCP_JSON en rtpengine (include/homer.h) — no confundir con 1=SIP

_rtcp_queue: list[tuple] = []

_UPSERT_MEDIA_STATS = """
    INSERT INTO call_media_stats
        (call_id, max_jitter_ms, max_packet_loss_pct, packets_lost, report_count,
         sum_jitter_ms, sum_packet_loss_pct)
    VALUES (%s, %s, %s, %s, 1, %s, %s)
    ON DUPLICATE KEY UPDATE
        max_jitter_ms       = GREATEST(max_jitter_ms, VALUES(max_jitter_ms)),
        max_packet_loss_pct = GREATEST(max_packet_loss_pct, VALUES(max_packet_loss_pct)),
        packets_lost        = GREATEST(packets_lost, VALUES(packets_lost)),
        report_count        = report_count + 1,
        sum_jitter_ms       = sum_jitter_ms + VALUES(sum_jitter_ms),
        sum_packet_loss_pct = sum_packet_loss_pct + VALUES(sum_packet_loss_pct)
"""


def _enqueue_rtcp(pkt: dict) -> None:
    """
    RTPEngine manda esto vía `homer=` en rtpengine.conf — un JSON por paquete
    RTCP recibido (no solo al final de la llamada), con report_blocks por SSRC.

    ia_jitter viene en unidades de reloj RTP, no en ms — se asume 8kHz (G.711/
    G.729, la mayoría del tráfico de este SBC). fraction_lost es un valor
    0-255 (no 0-100), representa % perdido desde el reporte anterior.

    Guarda el PEOR valor observado por llamada (max_*) Y también acumula
    sum_jitter_ms/sum_packet_loss_pct — sum/report_count da el PROMEDIO real
    de toda la llamada. El peor solo no alcanza como badge de calidad: con
    decenas/cientos de reportes por llamada, casi cualquier llamada tiene UN
    microcorte puntual en algún momento, y usar solo el peor marca como mala
    una llamada que en promedio sonó perfecta (caso real: 112 reportes, pico
    de 58ms, promedio real 0.078ms — confirmado contra el propio portal del
    carrier, que reporta jitter promedio, no peor caso).
    """
    global _rtcp_dropped_total
    payload = pkt.get("payload") or ""
    call_id = (pkt.get("call_id") or "").strip()[:255]
    if not payload or not call_id:
        return
    if len(_rtcp_queue) >= _MAX_QUEUE:
        _rtcp_dropped_total += 1
        log.warning("Cola RTCP llena (%d) — la DB no sigue el ritmo, se descartan paquetes nuevos", len(_rtcp_queue))
        return

    report = json.loads(payload)  # levanta y se descarta silenciosamente si no es JSON válido
    blocks = report.get("report_blocks") or []
    if not blocks:
        return

    jitter_ms    = max((b.get("ia_jitter") or 0) for b in blocks) / 8
    loss_pct     = max((b.get("fraction_lost") or 0) for b in blocks) / 256 * 100
    # packets_lost es acumulado (no delta) — GREATEST() en el UPSERT se queda
    # con el valor más alto visto, que es el más reciente al ser monótono creciente.
    packets_lost = max((b.get("packets_lost") or 0) for b in blocks)

    jitter_ms = round(jitter_ms, 2)
    loss_pct  = round(loss_pct, 2)
    # jitter_ms/loss_pct van dos veces: una para el UPDATE de max_* (GREATEST),
    # otra para acumular en sum_* (promedio) — mismo valor de este reporte,
    # dos columnas distintas.
    _rtcp_queue.append((call_id, jitter_ms, loss_pct, packets_lost, jitter_ms, loss_pct))


async def _flush_rtcp_loop():
    global _last_rtcp_flush_ms, _last_rtcp_batch_size
    while True:
        await asyncio.sleep(BATCH_MS / 1000)
        if not _rtcp_queue:
            continue
        batch, _rtcp_queue[:] = _rtcp_queue[:], []
        t0 = time.monotonic()
        try:
            pool = await _get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.executemany(_UPSERT_MEDIA_STATS, batch)
        except Exception as e:
            log.warning("RTCP batch flush error: %s", e)
        finally:
            _last_rtcp_flush_ms  = (time.monotonic() - t0) * 1000
            _last_rtcp_batch_size = len(batch)


# ── Protocol ──────────────────────────────────────────────────────────────────

class _HEPProtocol(asyncio.DatagramProtocol):
    def datagram_received(self, data: bytes, _addr):
        try:
            pkt = _parse_hep3(data)
        except Exception as e:
            log.debug("packet error: %s", e)
            return

        # Ramas con try/except separados a propósito: un bug parseando RTCP
        # nunca debe poder tumbar la captura de SIP, y viceversa.
        if pkt.get("proto_type", 1) == PROTO_RTCP_JSON:
            try:
                _enqueue_rtcp(pkt)
            except Exception as e:
                log.debug("rtcp packet error: %s", e)
        else:
            try:
                _enqueue(pkt)
            except Exception as e:
                log.debug("packet error: %s", e)

    def error_received(self, exc):
        log.warning("UDP error: %s", exc)


_PROC_NET_UDP = Path("/proc/net/udp")


def _read_kernel_udp_drops(port: int) -> int | None:
    """
    Lee la columna `drops` de /proc/net/udp para nuestro socket — paquetes que
    el kernel descartó ANTES de que Python llegara a verlos (buffer del socket
    desbordado en una ráfaga). Esto es un blind spot real que _queue/_rtcp_queue
    nunca pueden ver, porque el paquete ya se perdió antes de llegar ahí.
    Devuelve None si no se puede leer (no-Linux, /proc no montado, etc.) —
    no es un error, simplemente no hay dato.
    """
    try:
        port_hex = f"{port:04X}"
        for line in _PROC_NET_UDP.read_text().splitlines()[1:]:
            fields = line.split()
            if len(fields) < 13:
                continue
            if fields[1].split(":")[1].upper() == port_hex:
                return int(fields[12])
    except Exception:
        return None
    return None


async def _stats_loop():
    """
    Escribe /var/lib/voxikam/hep_stats.json cada 5s — visibilidad real de las
    colas (SIP y RTCP) para el panel Dashboard, en vez de adivinar si esto
    aguanta el volumen real de llamadas. Mismo patrón que live_snapshot.json.
    """
    _STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            _STATS_FILE.write_text(json.dumps({
                "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "sip_queue_len":        len(_queue),
                "rtcp_queue_len":       len(_rtcp_queue),
                "sip_dropped_total":    _sip_dropped_total,
                "rtcp_dropped_total":   _rtcp_dropped_total,
                "kernel_udp_drops":     _read_kernel_udp_drops(HEP_PORT),
                "last_sip_flush_ms":    round(_last_sip_flush_ms, 1),
                "last_rtcp_flush_ms":   round(_last_rtcp_flush_ms, 1),
                "last_sip_batch_size":  _last_sip_batch_size,
                "last_rtcp_batch_size": _last_rtcp_batch_size,
                "max_queue":            _MAX_QUEUE,
            }))
            _STATS_FILE.chmod(0o644)  # legible por voxikam (backend)
        except Exception as e:
            log.warning("stats_loop error: %s", e)
        await asyncio.sleep(5)


async def main():
    loop = asyncio.get_event_loop()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, _SO_RCVBUF_TARGET)
    except OSError as e:
        log.warning("No se pudo ajustar SO_RCVBUF a %d: %s", _SO_RCVBUF_TARGET, e)
    try:
        sock.bind((HEP_HOST, HEP_PORT))
    except OSError as e:
        log.error("No se puede hacer bind en %s:%s — %s", HEP_HOST, HEP_PORT, e)
        sys.exit(1)
    sock.setblocking(False)

    # El kernel puede recortar lo pedido a `net.core.rmem_max` del host —
    # se loguea el valor real negociado (no siempre es lo que se pidió).
    actual_rcvbuf = sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)

    await loop.create_datagram_endpoint(_HEPProtocol, sock=sock)

    log.info("HEP3 listener en udp %s:%s | batch %dms | SO_RCVBUF %d bytes — "
             "sip_traces→ClickHouse (TTL propio), call_media_stats→MariaDB",
             HEP_HOST, HEP_PORT, BATCH_MS, actual_rcvbuf)

    asyncio.create_task(_flush_loop())
    asyncio.create_task(_flush_rtcp_loop())
    asyncio.create_task(_stats_loop())
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
