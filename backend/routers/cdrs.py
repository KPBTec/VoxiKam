# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

import math

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from alerts import check_balance_alert
from auth import require_admin, require_ingest_secret
from database import get_db
from webhooks import dispatch_event

router = APIRouter()


class CdrIngestIn(BaseModel):
    """
    Único endpoint que mueve dinero (POST /ingest) que recibía `payload: dict`
    crudo, sin ningún schema — auditoría de arquitectura v2.46.0. Protegido
    por X-Ingest-Secret (ver require_ingest_secret), pero eso solo prueba
    quién llama, no que billsec/dst_number vengan con forma válida.
    """
    call_id: str = Field(min_length=1)
    src_ip: str = ""
    src_number: Optional[str] = None
    dst_number: str = ""
    dst_number_raw: Optional[str] = None
    carrier_host: Optional[str] = ""
    billsec: int = Field(default=0, ge=0)
    sessiontime: int = Field(default=0, ge=0)
    start_ts: Optional[str] = None
    answer_ts: Optional[str] = None
    end_ts: Optional[str] = None
    disposition: str = "ANSWERED"
    call_state: Optional[str] = None
    hangup_cause: Optional[str] = None
    sip_code: int = Field(default=200, ge=100, le=699)


def _billable_blocks(seconds: int, initblock: int, billingblock: int) -> int:
    """
    Esquema típico de telco: los primeros `initblock` segundos se facturan
    como un bloque fijo (aunque la llamada dure menos), el resto se redondea
    hacia arriba en incrementos de `billingblock`. `initblock=0` (carrier_rates
    no tiene esta columna) degenera correctamente a "todo en bloques de
    billingblock", el comportamiento de siempre.

    Encontrado en la auditoría global v2.38.0: `initblock` se guardaba desde
    el admin/reseller pero ningún camino de facturación lo leía — un esquema
    configurado como "60/6" facturaba en realidad todo a 6s, sin el primer
    bloque de 60. Este helper es la única fuente de verdad para este cálculo,
    usado también por backend/main.py::_calc_bill() (mismo criterio, sin
    divergencia entre el camino síncrono y el de respaldo).
    """
    if seconds <= initblock:
        return initblock
    return initblock + math.ceil((seconds - initblock) / billingblock) * billingblock


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
    # start_ts SIN envolver en DATE() — "DATE(c.start_ts) >= :x" le impide a MySQL
    # usar tanto el índice (idx_date/idx_customer_date) como el partition pruning
    # de cdrs (particionada por mes vía TO_DAYS(start_ts)) — escaneaba el mes
    # entero para filtrar un solo día. Límite superior exclusivo (+1 día) para
    # cubrir el día completo de date_to sin tener que envolver la columna.
    if date_from:
        filters_ok.append("c.start_ts >= :date_from")
        filters_fail.append("f.start_ts >= :date_from")
        params["date_from"] = date_from
    if date_to:
        filters_ok.append("c.start_ts < DATE_ADD(:date_to, INTERVAL 1 DAY)")
        filters_fail.append("f.start_ts < DATE_ADD(:date_to, INTERVAL 1 DAY)")
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
            c.start_ts, c.sessiontime, c.billsec,
            c.buycost, c.sessionbill, c.lucro,
            c.disposition, c.call_state, c.hangup_cause,
            COALESCE(c.sip_code, 200) AS sip_code,
            cu.name AS customer_name,
            ca.name AS carrier_name,
            ms.max_jitter_ms, ms.max_packet_loss_pct, ms.packets_lost, ms.report_count,
            ROUND(ms.sum_jitter_ms / NULLIF(ms.report_count, 0), 2) AS avg_jitter_ms,
            ROUND(ms.sum_packet_loss_pct / NULLIF(ms.report_count, 0), 2) AS avg_packet_loss_pct
        FROM cdrs c
        LEFT JOIN customers cu ON c.customer_id = cu.id
        LEFT JOIN carriers  ca ON c.carrier_id  = ca.id
        LEFT JOIN call_media_stats ms ON ms.call_id = c.call_id
        WHERE {where_ok}
    """

    if include_failed:
        base_fail = f"""
        SELECT
            f.call_id, f.customer_id, f.carrier_id,
            f.src_number, f.dst_number,
            f.start_ts, 0 AS sessiontime, 0 AS billsec,
            0 AS buycost, 0 AS sessionbill, 0 AS lucro,
            'FAILED'   AS disposition,
            COALESCE(f.call_state, 'REJECTED') AS call_state,
            NULL       AS hangup_cause,
            f.sip_code,
            cu.name AS customer_name,
            ca.name AS carrier_name,
            NULL AS max_jitter_ms, NULL AS max_packet_loss_pct, NULL AS packets_lost, NULL AS report_count,
            NULL AS avg_jitter_ms, NULL AS avg_packet_loss_pct
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

    r    = await db.execute(text(query_sql), params)
    rows = r.mappings().all()

    # El COUNT(*) barre las mismas filas que la query de arriba (mismo WHERE,
    # incluido el `phone LIKE '%...%'` no indexable) — correrlo siempre duplica
    # el costo del scan más caro por cada búsqueda. Si esta página devolvió
    # MENOS filas que el límite pedido, ya sabemos el total exacto sin
    # necesidad de un segundo scan (offset + lo que trajo = todo lo que hay).
    # Solo hace falta el COUNT real cuando la página vino llena (podría haber
    # más después) — típico al navegar sin filtro de teléfono/fecha angosta.
    if len(rows) < limit:
        total_n = offset + len(rows)
    else:
        total = await db.execute(text(count_sql),
                                 {k: v for k, v in params.items() if k not in ("limit", "offset")})
        total_n = total.scalar()

    return {"total": total_n, "rows": rows}


@router.post("/ingest", dependencies=[Depends(require_ingest_secret)])
async def ingest_cdr(body: CdrIngestIn, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """
    Endpoint llamado por Kamailio acc.so (o script de acc) al finalizar cada llamada.
    Calcula buycost y sessionbill, actualiza balance del cliente.

    NOTA (auditoría global v2.38.0): no se encontró ningún llamador real de
    este endpoint en templates/kamailio.cfg.j2 — event_route[dialog:end] ahí
    inserta el CDR directo a MySQL vía sql_query(), y backend/main.py::
    _billing_worker() es quien lo completa (su propio docstring: "procesa
    CDRs escritos por Kamailio, buycost=0"). Este endpoint HTTP puede ser un
    mecanismo de una arquitectura anterior nunca removido — protegido con
    X-Ingest-Secret hasta confirmar en logs de producción si algo lo llama
    todavía; no se borra sin esa confirmación.
    """
    # payload = dict del body ya validado por CdrIngestIn — se mantiene como
    # dict acá abajo (payload.get(...)) a propósito, para no tocar el resto
    # de esta función más de lo necesario; lo que cambió es que ahora nunca
    # llega con billsec/sip_code fuera de rango o sin call_id.
    payload = body.model_dump()

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

    buycost, sessionbill, matched_prefix = 0.0, 0.0, None
    reseller_cost = None

    if carrier_id and billsec > 0:
        # Longest-prefix-match buy rate — filtrado por carrier_id (antes no
        # filtraba, hacía longest-prefix-match contra TODOS los carriers a la
        # vez, pudiendo tomar la tarifa de un carrier distinto al que realmente
        # cursó la llamada si dos carriers tenían el mismo prefijo cargado).
        rb = await db.execute(text("""
            SELECT cr.buy_rate, cr.billingblock, cr.connectcharge
            FROM carrier_rates cr
            JOIN prefixes p ON cr.prefix_id = p.id
            WHERE cr.carrier_id = :carrier_id AND :dst LIKE CONCAT(p.prefix, '%')
            ORDER BY LENGTH(p.prefix) DESC LIMIT 1
        """), {"dst": dst, "carrier_id": carrier_id})
        rate_row = rb.mappings().first()
        if rate_row:
            blocks   = _billable_blocks(billsec, 0, rate_row["billingblock"])
            buycost  = round(blocks * rate_row["buy_rate"] / 60 + rate_row["connectcharge"], 6)

    parent_customer_id = None
    if customer_id and billsec > 0:
        # Longest-prefix-match sell rate — el rate_plan_id del cliente puede
        # ser un plan de la plataforma O uno propio de un reseller (rate_plans
        # .owner_customer_id): la query no cambia, solo sigue el puntero.
        rs = await db.execute(text("""
            SELECT r.rateinitial, r.initblock, r.billingblock, r.connectcharge, r.minimal_time_charge,
                   p.prefix, cu.parent_customer_id
            FROM rates r
            JOIN prefixes p   ON r.prefix_id = p.id
            JOIN customers cu ON r.rate_plan_id = cu.rate_plan_id AND cu.id = :cid
            WHERE :dst LIKE CONCAT(p.prefix, '%') AND r.status = 'active'
            ORDER BY LENGTH(p.prefix) DESC LIMIT 1
        """), {"dst": dst, "cid": customer_id})
        rate_row = rs.mappings().first()
        if rate_row:
            billable    = max(billsec, rate_row["minimal_time_charge"])
            blocks      = _billable_blocks(billable, rate_row["initblock"], rate_row["billingblock"])
            sessionbill = round(blocks * rate_row["rateinitial"] / 60 + rate_row["connectcharge"], 6)
            matched_prefix = rate_row["prefix"]
            parent_customer_id = rate_row["parent_customer_id"]

        # Reventa multinivel: si el cliente depende de un reseller, calcular
        # además cuánto le "cuesta" esta llamada al RESELLER (su propio
        # rate_plan, el que la plataforma le vende a él) — mismo tipo de
        # lookup que arriba, pero contra el customer_id del reseller en vez
        # del sub-cliente. Con esto: margen reseller = sessionbill -
        # reseller_cost; margen plataforma = reseller_cost - buycost. Para
        # clientes sin reseller (mayoría hoy), parent_customer_id es NULL y
        # esto no se ejecuta — cero cambio de comportamiento.
        if parent_customer_id and billsec > 0:
            rr = await db.execute(text("""
                SELECT r.rateinitial, r.initblock, r.billingblock, r.connectcharge, r.minimal_time_charge
                FROM rates r
                JOIN customers cu ON r.rate_plan_id = cu.rate_plan_id AND cu.id = :pid
                JOIN prefixes p   ON r.prefix_id = p.id
                WHERE :dst LIKE CONCAT(p.prefix, '%') AND r.status = 'active'
                ORDER BY LENGTH(p.prefix) DESC LIMIT 1
            """), {"dst": dst, "pid": parent_customer_id})
            reseller_row = rr.mappings().first()
            if reseller_row:
                billable_r = max(billsec, reseller_row["minimal_time_charge"])
                blocks_r   = _billable_blocks(billable_r, reseller_row["initblock"], reseller_row["billingblock"])
                reseller_cost = round(blocks_r * reseller_row["rateinitial"] / 60 + reseller_row["connectcharge"], 6)

    # Derivar call_state estilo sngrep (Kamailio puede enviar DIVERTED explícito)
    disposition = payload.get("disposition", "ANSWERED")
    _state_map = {"ANSWERED": "COMPLETED", "BUSY": "BUSY", "NO_ANSWER": "CANCELLED", "FAILED": "REJECTED"}
    call_state = payload.get("call_state") or _state_map.get(disposition, "REJECTED")

    # Insertar CDR
    await db.execute(text("""
        INSERT INTO cdrs (call_id, customer_id, carrier_id, src_ip, src_number,
                          dst_number, dst_number_raw, prefix_matched,
                          start_ts, answer_ts, end_ts, sessiontime, billsec,
                          buycost, reseller_cost, sessionbill, disposition, call_state, hangup_cause, sip_code)
        VALUES (:call_id, :customer_id, :carrier_id, :src_ip, :src_number,
                :dst_number, :dst_number_raw, :prefix_matched,
                :start_ts, :answer_ts, :end_ts, :sessiontime, :billsec,
                :buycost, :reseller_cost, :sessionbill, :disposition, :call_state, :hangup_cause, :sip_code)
    """), {
        "call_id":       payload.get("call_id"),
        "customer_id":   customer_id,
        "carrier_id":    carrier_id,
        "src_ip":        payload.get("src_ip"),
        "src_number":    payload.get("src_number"),
        "dst_number":    dst,
        "dst_number_raw": payload.get("dst_number_raw", dst_raw),
        "prefix_matched": matched_prefix,
        "start_ts":      payload.get("start_ts"),
        "answer_ts":     payload.get("answer_ts"),
        "end_ts":        payload.get("end_ts"),
        "sessiontime":   payload.get("sessiontime", 0),
        "billsec":       billsec,
        "buycost":       buycost,
        "reseller_cost": reseller_cost,
        "sessionbill":   sessionbill,
        "disposition":   disposition,
        "call_state":    call_state,
        "hangup_cause":  payload.get("hangup_cause"),
        "sip_code":      int(payload.get("sip_code", 200)),
    })

    # Descontar del balance si es prepago — y dejar rastro en balance_transactions
    # + evaluar alerta de saldo, igual que main.py::_billing_worker() (gap
    # encontrado en la auditoría global v2.38.0: este camino descontaba
    # balance pero nunca escribía el ledger ni disparaba alertas de saldo bajo).
    if customer_id and sessionbill > 0:
        await db.execute(text(
            "UPDATE customers SET balance = balance - :bill WHERE id = :id"
        ), {"bill": sessionbill, "id": customer_id})
        bal_row = await db.execute(text(
            "SELECT balance FROM customers WHERE id = :id"
        ), {"id": customer_id})
        new_balance = bal_row.scalar()
        await db.execute(text("""
            INSERT INTO balance_transactions
                (customer_id, type, amount, balance_after, reference)
            VALUES (:cid, 'cdr', :amount, :bal, :ref)
        """), {"cid": customer_id, "amount": -float(sessionbill),
                "bal": new_balance, "ref": payload.get("call_id")})

    # Eliminar de activas
    await db.execute(text("DELETE FROM active_calls WHERE call_id = :call_id"),
                     {"call_id": payload.get("call_id")})

    await db.commit()

    if customer_id and sessionbill > 0:
        await check_balance_alert(db, customer_id)

    background_tasks.add_task(dispatch_event, "cdr.created", {
        "call_id": payload.get("call_id"), "customer_id": customer_id, "carrier_id": carrier_id,
        "dst_number": dst, "billsec": billsec, "buycost": buycost, "sessionbill": sessionbill,
        "disposition": disposition,
    })
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
    # Ver comentario en list_cdrs() más arriba — sargable + partition pruning.
    if date_from:   filters.append("f.start_ts >= :date_from"); params["date_from"] = date_from
    if date_to:     filters.append("f.start_ts < DATE_ADD(:date_to, INTERVAL 1 DAY)"); params["date_to"] = date_to
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

    rows = r.mappings().all()

    # Mismo criterio que list_cdrs() — evita el COUNT(*) duplicado cuando la
    # página ya vino incompleta (no hay más filas después).
    if len(rows) < limit:
        total_n = offset + len(rows)
    else:
        total = await db.execute(text(f"""
            SELECT COUNT(*) FROM cdrs_failed f WHERE {where}
        """), {k: v for k, v in params.items() if k not in ("limit", "offset")})
        total_n = total.scalar()

    return {"total": total_n, "rows": rows}
