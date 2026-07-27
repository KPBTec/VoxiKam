# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

import hashlib
import os
import socket
import struct
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response

from auth import require_admin
from clickhouse import get_ch

router = APIRouter()


def _mac_for_ip(ip: str) -> bytes:
    """MAC determinística por IP (mismo host → misma MAC en todo el pcap, como en una
    captura real) — bit locally-administered (0x02) para no chocar con MACs reales."""
    return b"\x02\x00" + hashlib.md5(ip.encode()).digest()[:4]


def _ip_checksum(header: bytes) -> int:
    if len(header) % 2:
        header += b"\x00"
    total = sum(struct.unpack(f"!{len(header) // 2}H", header))
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def _build_pcap(rows) -> bytes:
    """
    Reconstruye un .pcap (Ethernet/IPv4/UDP) a partir de sip_traces — no hubo una
    captura de paquetes real, así que los headers L2/L3/L4 son sintéticos, pero
    src/dst IP:puerto, timestamp y el mensaje SIP crudo son los reales capturados
    por HEP. Suficiente para abrir en Wireshark y ver el diálogo completo (incluido
    SDP) sin las limitaciones del ladder diagram en pantalla.
    """
    out = bytearray()
    out += struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)  # global header, LINKTYPE_ETHERNET

    for i, r in enumerate(rows):
        try:
            src_raw = socket.inet_aton(r["src_ip"] or "0.0.0.0")
            dst_raw = socket.inet_aton(r["dst_ip"] or "0.0.0.0")
        except OSError:
            continue  # IPv6 u otro formato no soportado — se omite ese mensaje del pcap

        payload = (r["raw_message"] or "").encode("utf-8", errors="replace")
        src_port = r["src_port"] or 5060
        dst_port = r["dst_port"] or 5060

        udp_len = 8 + len(payload)
        udp_header = struct.pack("!HHHH", src_port, dst_port, udp_len, 0)  # checksum 0 = sin validar

        ip_total_len = 20 + udp_len
        ip_fields = (0x45, 0, ip_total_len, i & 0xFFFF, 0x4000, 64, 17, 0, src_raw, dst_raw)
        checksum = _ip_checksum(struct.pack("!BBHHHBBH4s4s", *ip_fields))
        ip_header = struct.pack("!BBHHHBBH4s4s", *ip_fields[:7], checksum, src_raw, dst_raw)

        eth_header = _mac_for_ip(r["dst_ip"] or "") + _mac_for_ip(r["src_ip"] or "") + b"\x08\x00"

        packet = eth_header + ip_header + udp_header + payload
        ts = r["captured_at"] or datetime.utcnow()
        out += struct.pack("<IIII", int(ts.timestamp()), ts.microsecond, len(packet), len(packet))
        out += packet

    return bytes(out)


def _classify_query(q: str) -> tuple[str, str]:
    """
    Devuelve (cond_sql, q_valor) según el tipo de búsqueda:
    - Call-ID   → exact match en call_id          (usa idx_call_id, instantáneo)
    - Teléfono  → trailing wildcard en from/to_uri (puede usar índice)
    - Vacío     → sin filtro (lista todas del día)
    - Otro      → LIKE '%q%' fallback (lento, pero cubre casos raros)
    """
    q = q.strip()
    if not q:
        return ("", "")

    # Call-ID: alfanumérico largo, sin espacios (>= 20 chars) — SÍ puede tener "@",
    # de hecho el Call-ID SIP real casi siempre es "<random>@<host>" (así lo pasa el
    # link "SIP" de /cdrs). Antes se excluía "@" acá pensando que el Call-ID nunca lo
    # tenía, así que TODA navegación desde CDRs caía al fallback LIKE bilateral de
    # abajo — full scan de sip_traces del día completo, el origen real de la demora
    # de ~15s reportada al entrar a Trazas SIP desde un CDR.
    if len(q) >= 20 and " " not in q:
        return ("AND call_id = {q:String}", q)

    # Número de teléfono: solo dígitos, +, -, máx 20 chars
    stripped = q.lstrip("+").replace("-", "").replace(" ", "")
    if stripped.isdigit() and len(stripped) >= 4:
        return ("AND (from_uri LIKE {q:String} OR to_uri LIKE {q:String})", f"{q}%")

    # Fallback: LIKE bilateral (slow path — avisa con LIMIT bajo)
    return ("AND (call_id LIKE {q:String} OR from_uri LIKE {q:String} OR to_uri LIKE {q:String})", f"%{q}%")


@router.get("/calls")
async def search_calls(
    date: str  = Query(...,  description="Fecha YYYY-MM-DD"),
    q:    str  = Query("",  description="Búsqueda: Call-ID completo o número de teléfono"),
    limit: int = Query(100, le=500),
    ch=Depends(get_ch),
    _: dict = Depends(require_admin),
):
    """
    Lista de llamadas con traza SIP para una fecha.
    Detección automática del tipo de búsqueda:
    - Call-ID >= 20 chars sin @ → exact match (sort key call_id, rápido)
    - Número de teléfono → trailing LIKE (skip index ngrambf_v1)
    - Vacío → lista todas las llamadas del día
    """
    cond, q_val = _classify_query(q)
    params: dict = {"date_from": date, "lim": limit}
    if q_val:
        params["q"] = q_val

    # Concatenado con `+` (no f-string) a propósito: los placeholders
    # {date_from:DateTime}/{lim:UInt32} son sintaxis de ClickHouse, no de
    # Python — un f-string los interpretaría como expresiones y rompería.
    result = await ch.query(
        """
            SELECT
                call_id,
                min(captured_at)             AS first_ts,
                max(captured_at)              AS last_ts,
                count()                       AS msg_count,
                max(sip_method = 'INVITE')    AS has_invite,
                max(ifNull(sip_status, 0))    AS final_status,
                max(from_uri)                 AS from_uri,
                max(to_uri)                   AS to_uri,
                arrayStringConcat(
                    arrayMap(x -> x.3,
                        arraySort(x -> (x.1, x.2),
                            groupArray((captured_at, id, coalesce(sip_method, toString(sip_status))))
                        )
                    ), ','
                )                             AS method_seq
            FROM sip_traces
            WHERE captured_at >= {date_from:DateTime}
              AND captured_at <  {date_from:DateTime} + INTERVAL 1 DAY
              """ + cond + """
            GROUP BY call_id
            ORDER BY first_ts DESC
            LIMIT {lim:UInt32}
        """,
        parameters=params,
    )
    calls = []
    for r in result.named_results():
        calls.append({
            "call_id":      r["call_id"],
            "first_ts":     r["first_ts"].isoformat() if r["first_ts"] else None,
            "last_ts":      r["last_ts"].isoformat()  if r["last_ts"]  else None,
            "msg_count":    r["msg_count"],
            "has_invite":   bool(r["has_invite"]),
            "final_status": r["final_status"] or None,
            "from_uri":     r["from_uri"],
            "to_uri":       r["to_uri"],
            "methods":      (r["method_seq"] or "").split(","),
        })
    return {"date": date, "count": len(calls), "calls": calls}


@router.get("/stream")
async def get_stream(
    since_id: int = Query(0,   description="Devuelve mensajes con id > since_id"),
    limit:    int = Query(200, le=500),
    ch=Depends(get_ch),
    _: dict = Depends(require_admin),
):
    """
    Feed de todos los mensajes SIP recientes — para la vista live.
    Llamar con `since_id` del último mensaje recibido para obtener solo los nuevos.
    """
    result = await ch.query(
        """
            SELECT id, captured_at, call_id, src_ip, src_port, dst_ip, dst_port,
                   sip_method, sip_status, from_uri, to_uri, cseq, user_agent, reason
            FROM sip_traces
            WHERE id > {sid:UInt64}
              AND captured_at >= today()
            ORDER BY id DESC
            LIMIT {lim:UInt32}
        """,
        parameters={"sid": since_id, "lim": limit},
    )
    msgs = []
    for r in result.named_results():
        msgs.append({
            "id":         r["id"],
            "ts":         r["captured_at"].isoformat() if r["captured_at"] else None,
            "call_id":    r["call_id"],
            "src_ip":     r["src_ip"],
            "src_port":   r["src_port"],
            "dst_ip":     r["dst_ip"],
            "dst_port":   r["dst_port"],
            "method":     r["sip_method"],
            "status":     r["sip_status"],
            "from_uri":   r["from_uri"],
            "to_uri":     r["to_uri"],
            "cseq":       r["cseq"],
            "user_agent": r["user_agent"],
            "reason":     r["reason"],
        })
    # Devolver en orden cronológico (más antiguo primero)
    msgs.reverse()
    return {"count": len(msgs), "messages": msgs}


@router.get("")
async def get_trace(
    call_id: str = Query(..., description="Call-ID SIP exacto"),
    since_id: int = Query(0, description="Devuelve solo mensajes con id > since_id (para polling live)"),
    ch=Depends(get_ch),
    _: dict = Depends(require_admin),
):
    """
    Todos los mensajes SIP de una llamada en orden cronológico.
    Usar `since_id` para polling incremental en modo en vivo.
    """
    result = await ch.query(
        """
            SELECT id, captured_at, src_ip, src_port, dst_ip, dst_port,
                   sip_method, sip_status, from_uri, to_uri, raw_message
            FROM sip_traces
            WHERE call_id = {cid:String} AND id > {sid:UInt64}
            ORDER BY captured_at, id
        """,
        parameters={"cid": call_id, "sid": since_id},
    )
    msgs = []
    for r in result.named_results():
        msgs.append({
            "id":       r["id"],
            "ts":       r["captured_at"].isoformat() if r["captured_at"] else None,
            "src_ip":   r["src_ip"],
            "src_port": r["src_port"],
            "dst_ip":   r["dst_ip"],
            "dst_port": r["dst_port"],
            "method":   r["sip_method"],
            "status":   r["sip_status"],
            "from_uri": r["from_uri"],
            "to_uri":   r["to_uri"],
            "raw":      r["raw_message"],
        })
    return {
        "call_id": call_id, "count": len(msgs), "messages": msgs,
        # Para que el ladder etiquete "SBC (LAN)"/"SBC (WAN)" en vez de adivinar
        # por heurística — con dual-NIC el SBC aparece dos veces en la traza
        # (una IP hablando con el cliente, otra con el carrier) y antes solo
        # se reconocía una de las dos como "SBC", la otra quedaba como "Destino".
        "sbc_private_ip": os.getenv("PRIVATE_IP", ""),
        "sbc_public_ip":  os.getenv("PUBLIC_IP", ""),
    }


@router.get("/pcap")
async def download_pcap(
    call_id: str = Query(..., description="Call-ID SIP exacto"),
    ch=Depends(get_ch),
    _: dict = Depends(require_admin),
):
    """
    Exporta el diálogo SIP completo de una llamada como .pcap para abrir en Wireshark —
    el ladder diagram no siempre deja ver con claridad quién originó cada mensaje
    (p.ej. quién colgó realmente: BYE del cliente vs. BYE del carrier).
    """
    result = await ch.query(
        """
            SELECT captured_at, src_ip, src_port, dst_ip, dst_port, raw_message
            FROM sip_traces
            WHERE call_id = {cid:String}
            ORDER BY captured_at, id
        """,
        parameters={"cid": call_id},
    )
    msgs = list(result.named_results())
    pcap_bytes = _build_pcap(msgs)
    safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in call_id)[:60]
    return Response(
        content=pcap_bytes,
        media_type="application/vnd.tcpdump.pcap",
        headers={"Content-Disposition": f'attachment; filename="trace-{safe_name}.pcap"'},
    )
