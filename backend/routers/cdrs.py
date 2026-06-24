# la plataforma anterior — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2025 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2025 – Todos los derechos reservados.

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from auth import require_admin
from database import get_db

router = APIRouter()


@router.get("")
async def list_cdrs(
    customer_id:    Optional[int]  = Query(None),
    carrier_id:     Optional[int]  = Query(None),
    date_from:      Optional[str]  = Query(None),
    date_to:        Optional[str]  = Query(None),
    disposition:    Optional[str]  = Query(None),
    phone:          Optional[str]  = Query(None),
    include_failed: bool           = Query(False),
    limit:          int            = Query(200, le=1000),
    offset:         int            = Query(0),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    params: dict = {"limit": limit, "offset": offset}
    filters_ok  = ["1=1"]
    filters_fail= ["1=1"]

    if customer_id:
        filters_ok.append("c.customer_id = :customer_id")
        filters_fail.append("f.customer_id = :customer_id")
        params["customer_id"] = customer_id
    if carrier_id:
        filters_ok.append("c.carrier_id = :carrier_id")
        filters_fail.append("f.carrier_id = :carrier_id")
        params["carrier_id"] = carrier_id
    if date_from:
        filters_ok.append("DATE(c.start_ts) >= :date_from")
        filters_fail.append("DATE(f.start_ts) >= :date_from")
        params["date_from"] = date_from
    if date_to:
        filters_ok.append("DATE(c.start_ts) <= :date_to")
        filters_fail.append("DATE(f.start_ts) <= :date_to")
        params["date_to"] = date_to
    if phone:
        filters_ok.append("(c.src_number LIKE :phone OR c.dst_number LIKE :phone)")
        filters_fail.append("(f.src_number LIKE :phone OR f.dst_number LIKE :phone)")
        params["phone"] = f"%{phone}%"
    # Establecidas = siempre ANSWERED únicamente
    filters_ok.append("c.disposition = 'ANSWERED'")

    where_ok   = " AND ".join(filters_ok)
    where_fail = " AND ".join(filters_fail)

    base_ok = f"""
        SELECT
            c.call_id, c.customer_id, c.carrier_id,
            c.src_number, c.dst_number,
            c.start_ts, c.billsec,
            c.buycost, c.sessionbill, c.lucro,
            c.disposition, c.call_state, c.hangup_cause,
            COALESCE(c.sip_code, 200) AS sip_code,
            cu.name AS customer_name,
            ca.name AS carrier_name
        FROM cdrs c
        LEFT JOIN customers cu ON c.customer_id = cu.id
        LEFT JOIN carriers  ca ON c.carrier_id  = ca.id
        WHERE {where_ok}
    """

    if include_failed:
        base_fail = f"""
        SELECT
            f.call_id, f.customer_id, f.carrier_id,
            f.src_number, f.dst_number,
            f.start_ts, 0 AS billsec,
            0 AS buycost, 0 AS sessionbill, 0 AS lucro,
            'FAILED'   AS disposition,
            COALESCE(f.call_state, 'REJECTED') AS call_state,
            NULL       AS hangup_cause,
            f.sip_code,
            cu.name AS customer_name,
            ca.name AS carrier_name
        FROM cdrs_failed f
        LEFT JOIN customers cu ON f.customer_id = cu.id
        LEFT JOIN carriers  ca ON f.carrier_id  = ca.id
        WHERE {where_fail}
        """
        union_sql = f"({base_ok}) UNION ALL ({base_fail})"
        query_sql = f"SELECT * FROM ({union_sql}) q ORDER BY start_ts DESC LIMIT :limit OFFSET :offset"
        count_sql = f"SELECT COUNT(*) FROM ({union_sql}) q"
    else:
        query_sql = f"{base_ok} ORDER BY c.start_ts DESC LIMIT :limit OFFSET :offset"
        count_sql = f"SELECT COUNT(*) FROM cdrs c WHERE {where_ok}"

    r     = await db.execute(text(query_sql), params)
    total = await db.execute(text(count_sql),
                             {k: v for k, v in params.items() if k not in ("limit", "offset")})

    return {"total": total.scalar(), "rows": r.mappings().all()}


@router.post("/ingest")
async def ingest_cdr(payload: dict, db: AsyncSession = Depends(get_db)):
    """
    Endpoint llamado por Kamailio acc.so (o script de acc) al finalizar cada llamada.
    Calcula buycost y sessionbill, actualiza balance del cliente.
    """
    # Lookup customer por IP
    r = await db.execute(text(
        "SELECT customer_id FROM customer_ips WHERE ip = :ip LIMIT 1"
    ), {"ip": payload.get("src_ip", "")})
    row = r.first()
    customer_id = row[0] if row else None

    # Lookup carrier (por IP del trunk usado)
    rc = await db.execute(text(
        "SELECT id FROM carriers WHERE host = :host LIMIT 1"
    ), {"host": payload.get("carrier_host", "")})
    rowc = rc.first()
    carrier_id = rowc[0] if rowc else None

    billsec = int(payload.get("billsec", 0))
    dst_raw = payload.get("dst_number", "")
    dst     = dst_raw  # se normaliza a continuación

    # ── Normalización del número destino ────────────────────────────────────
    # 1) Quitar techprefix del cliente: el cliente envía TECHPREFIX+NUMERO
    #    (ej: 80011234567890 → 1234567890 si techprefix=8001).
    #    Esto lo debería hacer Kamailio antes del CDR, pero aquí es el fallback.
    if customer_id:
        r_tp = await db.execute(
            text("SELECT techprefix FROM customers WHERE id = :id"), {"id": customer_id}
        )
        tp_row = r_tp.first()
        techprefix = (tp_row[0] or "") if tp_row else ""
        if techprefix and dst.startswith(techprefix):
            dst = dst[len(techprefix):]

    # 2) Quitar outbound_prefix del carrier: Kamailio puede haber reescrito el
    #    R-URI añadiendo el prefijo de salida antes de generar el CDR.
    #    (ej: 001234567890 → 1234567890 si outbound_prefix=00)
    if carrier_id:
        r_pfx = await db.execute(
            text("SELECT outbound_prefix FROM carriers WHERE id = :id"), {"id": carrier_id}
        )
        pfx_row = r_pfx.first()
        outbound_pfx = (pfx_row[0] or "") if pfx_row else ""
        if outbound_pfx and dst.startswith(outbound_pfx):
            dst = dst[len(outbound_pfx):]
    # ────────────────────────────────────────────────────────────────────────

    buycost, sessionbill = 0.0, 0.0

    if carrier_id and billsec > 0:
        # Longest-prefix-match buy rate
        rb = await db.execute(text("""
            SELECT cr.buy_rate, cr.billingblock, cr.connect_charge
            FROM carrier_rates cr
            JOIN prefixes p ON cr.prefix_id = p.id
            WHERE :dst LIKE CONCAT(p.prefix, '%')
            ORDER BY LENGTH(p.prefix) DESC LIMIT 1
        """), {"dst": dst})
        rate_row = rb.mappings().first()
        if rate_row:
            import math
            blocks   = math.ceil(billsec / rate_row["billingblock"]) * rate_row["billingblock"]
            buycost  = round(blocks * rate_row["buy_rate"] / 60 + rate_row["connect_charge"], 6)

    if customer_id and billsec > 0:
        # Longest-prefix-match sell rate
        rs = await db.execute(text("""
            SELECT r.rateinitial, r.billingblock, r.connectcharge, r.minimal_time_charge
            FROM rates r
            JOIN prefixes p   ON r.prefix_id = p.id
            JOIN customers cu ON r.rate_plan_id = cu.rate_plan_id AND cu.id = :cid
            WHERE :dst LIKE CONCAT(p.prefix, '%')
            ORDER BY LENGTH(p.prefix) DESC LIMIT 1
        """), {"dst": dst, "cid": customer_id})
        rate_row = rs.mappings().first()
        if rate_row:
            import math
            billable    = max(billsec, rate_row["minimal_time_charge"])
            blocks      = math.ceil(billable / rate_row["billingblock"]) * rate_row["billingblock"]
            sessionbill = round(blocks * rate_row["rateinitial"] / 60 + rate_row["connectcharge"], 6)

    # Derivar call_state estilo sngrep (Kamailio puede enviar DIVERTED explícito)
    disposition = payload.get("disposition", "ANSWERED")
    _state_map = {"ANSWERED": "COMPLETED", "BUSY": "BUSY", "NO_ANSWER": "CANCELLED", "FAILED": "REJECTED"}
    call_state = payload.get("call_state") or _state_map.get(disposition, "REJECTED")

    # Insertar CDR
    await db.execute(text("""
        INSERT INTO cdrs (call_id, customer_id, carrier_id, src_ip, src_number,
                          dst_number, dst_number_raw, prefix_matched,
                          start_ts, answer_ts, end_ts, sessiontime, billsec,
                          buycost, sessionbill, disposition, call_state, hangup_cause, sip_code)
        VALUES (:call_id, :customer_id, :carrier_id, :src_ip, :src_number,
                :dst_number, :dst_number_raw, :prefix_matched,
                :start_ts, :answer_ts, :end_ts, :sessiontime, :billsec,
                :buycost, :sessionbill, :disposition, :call_state, :hangup_cause, :sip_code)
    """), {
        "call_id":       payload.get("call_id"),
        "customer_id":   customer_id,
        "carrier_id":    carrier_id,
        "src_ip":        payload.get("src_ip"),
        "src_number":    payload.get("src_number"),
        "dst_number":    dst,
        "dst_number_raw": payload.get("dst_number_raw", dst_raw),
        "prefix_matched": payload.get("prefix_matched"),
        "start_ts":      payload.get("start_ts"),
        "answer_ts":     payload.get("answer_ts"),
        "end_ts":        payload.get("end_ts"),
        "sessiontime":   payload.get("sessiontime", 0),
        "billsec":       billsec,
        "buycost":       buycost,
        "sessionbill":   sessionbill,
        "disposition":   disposition,
        "call_state":    call_state,
        "hangup_cause":  payload.get("hangup_cause"),
        "sip_code":      int(payload.get("sip_code", 200)),
    })

    # Descontar del balance si es prepago
    if customer_id and sessionbill > 0:
        await db.execute(text(
            "UPDATE customers SET balance = balance - :bill WHERE id = :id"
        ), {"bill": sessionbill, "id": customer_id})

    # Eliminar de activas
    await db.execute(text("DELETE FROM active_calls WHERE call_id = :call_id"),
                     {"call_id": payload.get("call_id")})

    await db.commit()
    return {"ok": True, "buycost": buycost, "sessionbill": sessionbill}


@router.get("/failed")
async def list_failed_cdrs(
    customer_id: Optional[int] = Query(None),
    carrier_id:  Optional[int] = Query(None),
    date_from:   Optional[str] = Query(None),
    date_to:     Optional[str] = Query(None),
    sip_code:    Optional[int] = Query(None),
    phone:       Optional[str] = Query(None),
    limit:       int           = Query(200, le=1000),
    offset:      int           = Query(0),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """Llamadas no establecidas (487, 486, 404, 503…) — tabla cdrs_failed."""
    filters = ["1=1"]
    params: dict = {"limit": limit, "offset": offset}

    if customer_id: filters.append("f.customer_id = :customer_id"); params["customer_id"] = customer_id
    if carrier_id:  filters.append("f.carrier_id  = :carrier_id");  params["carrier_id"]  = carrier_id
    if date_from:   filters.append("DATE(f.start_ts) >= :date_from"); params["date_from"] = date_from
    if date_to:     filters.append("DATE(f.start_ts) <= :date_to");   params["date_to"]   = date_to
    if sip_code:    filters.append("f.sip_code = :sip_code");         params["sip_code"]  = sip_code
    if phone:       filters.append("(f.src_number LIKE :phone OR f.dst_number LIKE :phone)"); params["phone"] = f"%{phone}%"

    where = " AND ".join(filters)
    r = await db.execute(text(f"""
        SELECT
            f.*,
            cu.name AS customer_name,
            ca.name AS carrier_name
        FROM cdrs_failed f
        LEFT JOIN customers cu ON f.customer_id = cu.id
        LEFT JOIN carriers  ca ON f.carrier_id  = ca.id
        WHERE {where}
        ORDER BY f.start_ts DESC
        LIMIT :limit OFFSET :offset
    """), params)

    total = await db.execute(text(f"""
        SELECT COUNT(*) FROM cdrs_failed f WHERE {where}
    """), {k: v for k, v in params.items() if k not in ("limit", "offset")})

    return {"total": total.scalar(), "rows": r.mappings().all()}
