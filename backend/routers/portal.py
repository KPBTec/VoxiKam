# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""Portal del cliente — solo ve sus propios datos."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from pathlib import Path
import hashlib
import os
import secrets

from audit import record_event
from auth import get_current_user, require_permission, has_permission
from database import get_db
from routers.areas import _area_report_rows
from sync_runner import run_sync

router = APIRouter()
SCRIPTS = Path(__file__).parent.parent.parent / "scripts"

CLIENT_MAX_ROWS = 200   # techo absoluto para clientes — no negociable


def _sync_dispatcher():
    run_sync(SCRIPTS / "gen_dispatcher.py")


def _customer_id(user: dict) -> int:
    return user["customer_id"]


# ── Helpers compartidos con /api/v1 (backend/routers/api_v1.py) — la lógica de
# consulta vive en un solo lugar, tanto el portal (JWT) como la API key la usan
# a través de estas funciones, para que nunca diverjan con el tiempo. ─────────

async def _get_balance(db: AsyncSession, cid: int) -> dict:
    r = await db.execute(text(
        "SELECT balance, credit_limit, currency, billing_type FROM customers WHERE id=:cid"
    ), {"cid": cid})
    return dict(r.mappings().first() or {})


async def _get_calls(
    db: AsyncSession, cid: int,
    date_from: Optional[str], date_to: Optional[str],
    limit: int, offset: int,
) -> dict:
    limit = min(limit, CLIENT_MAX_ROWS)  # techo absoluto, sin importar quién llame

    params = {"cid": cid, "limit": limit, "offset": offset}
    # RESTART_ORPHANED = llamada sin facturar todavía, pendiente de revisión
    # manual admin (ver scripts/cleanup_active_calls.py) — no se le muestra al
    # cliente hasta que se resuelva a una disposition real.
    # start_ts sin envolver en DATE() — permite usar el índice compuesto
    # idx_customer_date (customer_id, start_ts) como range scan real en vez de
    # escanear todo el historial del cliente para filtrar por función.
    filters = ["customer_id = :cid", "disposition != 'RESTART_ORPHANED'"]
    if date_from: filters.append("start_ts >= :date_from"); params["date_from"] = date_from
    if date_to:   filters.append("start_ts < DATE_ADD(:date_to, INTERVAL 1 DAY)"); params["date_to"] = date_to
    where = " AND ".join(filters)

    r = await db.execute(text(f"""
        SELECT call_id, src_number, dst_number, billsec, sessionbill,
               disposition, start_ts, answer_ts, end_ts
        FROM cdrs WHERE {where}
        ORDER BY start_ts DESC LIMIT :limit OFFSET :offset
    """), params)

    count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}
    total_r = await db.execute(text(f"""
        SELECT COUNT(*) FROM (
            SELECT 1 FROM cdrs WHERE {where} LIMIT {CLIENT_MAX_ROWS}
        ) t
    """), count_params)

    total = total_r.scalar()
    return {
        "total":  total,
        "capped": total >= CLIENT_MAX_ROWS,
        "limit":  limit,
        "offset": offset,
        "rows":   r.mappings().all(),
    }


@router.get("/today")
async def today(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    KPIs de hoy + últimas 10 llamadas — cada mitad se omite del payload si el
    cliente no tiene el permiso correspondiente (overview_kpis/
    overview_last_calls), no solo se oculta en el frontend — el admin puede
    querer que un cliente vea SOLO su historial completo en /my/calls (ver
    permiso "calls", ya existente) sin exponerle el resumen de hoy acá.
    """
    cid = _customer_id(user)
    is_admin = user["role"] == "admin"
    show_kpis = is_admin or await has_permission(db, cid, "overview_kpis")
    show_last_calls = is_admin or await has_permission(db, cid, "overview_last_calls")

    # balance/billing_type SIEMPRE se devuelven, independiente de overview_kpis
    # — el aviso de "sin saldo disponible" (frontend, my/overview/page.tsx) los
    # necesita para clientes prepago sin importar si el admin les ocultó las
    # 4 tarjetas de estadística del día.
    b = await _get_balance(db, cid)
    result: dict = dict(b)

    if show_kpis:
        stats = await db.execute(text("""
            SELECT
                COUNT(*)                            AS calls_today,
                SUM(billsec) / 60.0                 AS minutes_today,
                SUM(sessionbill)                    AS cost_today,
                SUM(disposition = 'ANSWERED') * 100.0
                  / NULLIF(COUNT(*), 0)             AS asr_today
            FROM cdrs
            WHERE customer_id = :cid AND start_ts >= CURDATE() AND start_ts < CURDATE() + INTERVAL 1 DAY
              AND disposition != 'RESTART_ORPHANED'
        """), {"cid": cid})
        s = dict(stats.mappings().first() or {})
        result.update(s)
        result["available"] = float(b.get("balance", 0)) - float(s.get("cost_today") or 0)

    if show_last_calls:
        last10 = await db.execute(text("""
            SELECT src_number, dst_number, billsec, sessionbill, disposition, start_ts
            FROM cdrs WHERE customer_id=:cid AND start_ts >= CURDATE() AND start_ts < CURDATE() + INTERVAL 1 DAY
            ORDER BY start_ts DESC LIMIT 10
        """), {"cid": cid})
        result["last_calls"] = last10.mappings().all()

    result["show_kpis"] = show_kpis
    result["show_last_calls"] = show_last_calls
    return result


@router.get("/calls")
async def my_calls(
    date_from: Optional[str] = Query(None),
    date_to:   Optional[str] = Query(None),
    limit:     int           = Query(50, ge=1, le=CLIENT_MAX_ROWS),
    offset:    int           = Query(0, ge=0),
    user=Depends(require_permission("calls")),
    db: AsyncSession = Depends(get_db),
):
    return await _get_calls(db, _customer_id(user), date_from, date_to, limit, offset)


@router.get("/report/range")
async def my_report_range(
    user=Depends(require_permission("reports")),
    db: AsyncSession = Depends(get_db),
):
    """
    Mes más antiguo con datos para este cliente — para que el selector de
    mes/año de /my/reports no ofrezca años/meses sin ningún CDR (ej. mostraba
    2024 en un cliente dado de alta en 2026). Lee de cdr_summary_month (chica,
    indexada por customer_id) en vez de MIN(start_ts) sobre cdrs — eso último
    repetiría el mismo escaneo completo de tabla particionada que se arregló
    en my_report().
    """
    import datetime as _dt
    r = await db.execute(text(
        "SELECT MIN(summary_month) AS min_month FROM cdr_summary_month WHERE customer_id = :cid"
    ), {"cid": _customer_id(user)})
    min_month = r.scalar()
    return {
        "min_month": min_month,
        "current_month": _dt.date.today().strftime("%Y-%m"),
    }


@router.get("/report")
async def my_report(
    month: Optional[str] = Query(None),
    user=Depends(require_permission("reports")),
    db: AsyncSession = Depends(get_db),
):
    """
    Resumen mensual + desglose diario.
    Días completados del mes → cdr_summary_day (agregado nocturno, rápido).
    Hoy (solo si el mes pedido es el actual) → cdrs en vivo, acotado a la
    partición de hoy — mismo patrón híbrido que reports.py::report_month()
    (admin), nunca aplicado acá: esta consulta escaneaba el mes completo en
    vivo contra cdrs en cada carga de /my/reports (~11s con clientes de alto
    volumen).
    """
    import datetime as _dt
    cid = _customer_id(user)
    mon = month or _dt.date.today().strftime("%Y-%m")

    r = await db.execute(text("""
        SELECT
            fecha,
            SUM(llamadas)                                          AS llamadas,
            SUM(fallidas)                                          AS fallidas,
            SUM(segundos)                                          AS segundos,
            ROUND(SUM(segundos) / 60.0, 2)                         AS minutos,
            ROUND(SUM(costo), 4)                                   AS costo,
            ROUND(
                SUM(llamadas) * 100.0
                / NULLIF(SUM(llamadas) + SUM(fallidas), 0), 1
            )                                                      AS asr
        FROM (
            /* Días completados del mes — tabla de resumen */
            SELECT
                summary_date      AS fecha,
                SUM(nbcall)       AS llamadas,
                SUM(nbcall_fail)  AS fallidas,
                SUM(sessiontime)  AS segundos,
                SUM(sessionbill)  AS costo
            FROM cdr_summary_day
            WHERE customer_id = :cid
              AND LEFT(summary_date, 7) = :month
              AND summary_date < CURDATE()
            GROUP BY summary_date

            UNION ALL

            /* Hoy en vivo (solo si pertenece al mes pedido) */
            SELECT
                DATE(start_ts) AS fecha,
                SUM(disposition = 'ANSWERED')                                     AS llamadas,
                SUM(disposition != 'ANSWERED')                                    AS fallidas,
                SUM(CASE WHEN disposition = 'ANSWERED' THEN billsec ELSE 0 END)  AS segundos,
                SUM(sessionbill)                                                  AS costo
            FROM cdrs
            WHERE customer_id = :cid
              AND start_ts >= CURDATE() AND start_ts < CURDATE() + INTERVAL 1 DAY
              AND DATE_FORMAT(start_ts, '%Y-%m') = :month
              AND disposition != 'RESTART_ORPHANED'
            GROUP BY DATE(start_ts)
        ) d
        GROUP BY fecha
        ORDER BY fecha DESC
    """), {"cid": cid, "month": mon})

    rows = [
        {
            "fecha":    str(row["fecha"]),
            "llamadas": int(row["llamadas"] or 0),
            "fallidas": int(row["fallidas"] or 0),
            "segundos": int(row["segundos"] or 0),
            "minutos":  float(row["minutos"] or 0),
            "costo":    float(row["costo"] or 0),
            "asr":      float(row["asr"] or 0),
        }
        for row in r.mappings().all()
    ]

    total_llamadas = sum(d["llamadas"] for d in rows)
    total_fallidas = sum(d["fallidas"] for d in rows)
    total_segundos = sum(d["segundos"] for d in rows)
    total_costo    = round(sum(d["costo"] for d in rows), 4)

    monthly = {
        "mes":      mon,
        "llamadas": total_llamadas,
        "segundos": total_segundos,
        "minutos":  round(total_segundos / 60.0, 2),
        "costo":    total_costo,
        "asr":      round(
            total_llamadas * 100.0 / max(total_llamadas + total_fallidas, 1), 1
        ),
    }

    return {"month": mon, "monthly": monthly, "daily": rows}


@router.get("/report/by-area")
async def my_report_by_area(
    month: Optional[str] = Query(None),
    user=Depends(require_permission("reports")),
    db: AsyncSession = Depends(get_db),
):
    """
    Consumo por área/destino (a qué prefijos está llamando este cliente y
    cuánto le cuesta cada uno) — mismo motor que areas.py::area_report()
    (admin), acá siempre forzado al propio customer_id. No existía ninguna
    vista de esto para el cliente final; solo veía totales por día/mes y por
    campaña propia (prefijo de SU marcador, no destino de la llamada).
    """
    import datetime as _dt
    mon = month or _dt.date.today().strftime("%Y-%m")
    month_start = f"{mon}-01"
    # date_to = último día del mes pedido — _area_report_rows() solo exige
    # date_from/date_to como cotas sueltas, no conoce el concepto de "mes".
    y, m = map(int, mon.split("-"))
    last_day = (_dt.date(y + (m == 12), m % 12 + 1, 1) - _dt.timedelta(days=1)).isoformat()
    rows = await _area_report_rows(db, month_start, last_day, _customer_id(user))
    return {"month": mon, "areas": rows}


@router.get("/campaigns")
async def my_campaigns(
    date_from: Optional[str] = Query(None),
    date_to:   Optional[str] = Query(None),
    user=Depends(require_permission("reports")),
    db: AsyncSession = Depends(get_db),
):
    """
    Desglose de consumo por prefijo de campaña (customer_prefixes) — para
    clientes que usan un techprefix distinto por campaña de su marcador
    (ej. Vicidial), todo bajo el mismo balance.

    Días completados del rango → cdr_summary_day_campaign (agregado
    nocturno). Hoy → cdrs en vivo, acotado a su propia partición diaria —
    mismo patrón híbrido que el resto de esta sesión. Antes escaneaba cdrs
    en vivo para todo el rango pedido en cada carga.

    CDRs de ANTES de que existiera la columna cdrs.techprefix quedan
    agrupados en "Sin campaña" (techprefix NULL) — el dato nunca se guardó
    en ningún lado, no hay forma de reconstruirlo retroactivamente.
    """
    import datetime as _dt
    cid = _customer_id(user)
    d_to = date_to or _dt.date.today().isoformat()
    d_from = date_from or (_dt.date.today() - _dt.timedelta(days=30)).isoformat()

    cust = await db.execute(text(
        "SELECT techprefix FROM customers WHERE id = :cid"
    ), {"cid": cid})
    main_prefix = (cust.mappings().first() or {}).get("techprefix") or ""

    campaigns = await db.execute(text(
        "SELECT techprefix, label FROM customer_prefixes WHERE customer_id = :cid"
    ), {"cid": cid})
    label_map = {row["techprefix"]: (row["label"] or row["techprefix"]) for row in campaigns.mappings().all()}
    if main_prefix:
        label_map[main_prefix] = "Principal"

    r = await db.execute(text("""
        SELECT
            t.techprefix,
            SUM(t.llamadas)              AS llamadas,
            SUM(t.segundos)              AS segundos,
            ROUND(SUM(t.costo), 4)       AS costo
        FROM (
            /* Días completados del rango pedido — tabla de resumen */
            SELECT techprefix, nbcall AS llamadas, sessiontime AS segundos, sessionbill AS costo
            FROM cdr_summary_day_campaign
            WHERE customer_id = :cid
              AND summary_date < CURDATE()
              AND summary_date >= :d_from AND summary_date <= :d_to

            UNION ALL

            /* Hoy en vivo, acotado a su propia partición diaria */
            SELECT techprefix,
                   SUM(disposition = 'ANSWERED')                                     AS llamadas,
                   SUM(CASE WHEN disposition = 'ANSWERED' THEN billsec ELSE 0 END)    AS segundos,
                   SUM(sessionbill)                                                   AS costo
            FROM cdrs
            WHERE customer_id = :cid
              AND start_ts >= CURDATE() AND start_ts < CURDATE() + INTERVAL 1 DAY
              AND start_ts >= :d_from AND start_ts < DATE_ADD(:d_to, INTERVAL 1 DAY)
              AND disposition != 'RESTART_ORPHANED'
            GROUP BY techprefix
        ) t
        GROUP BY t.techprefix
        ORDER BY costo DESC
    """), {"cid": cid, "d_from": d_from, "d_to": d_to})

    rows = []
    for row in r.mappings().all():
        tp = row["techprefix"]
        rows.append({
            "techprefix": tp,
            "label":    label_map.get(tp, tp) if tp else "Sin campaña",
            "llamadas": int(row["llamadas"] or 0),
            "minutos":  round((row["segundos"] or 0) / 60.0, 2),
            "costo":    float(row["costo"] or 0),
        })
    return {"date_from": d_from, "date_to": d_to, "rows": rows}


@router.get("/invoices")
async def my_invoices(
    user=Depends(require_permission("invoices")),
    db: AsyncSession = Depends(get_db),
):
    cid = _customer_id(user)
    r = await db.execute(text("""
        SELECT id, period_start, period_end, nbcall, total_minutes,
               subtotal, tax_amount, total, currency, status, created_at
        FROM invoices WHERE customer_id = :cid ORDER BY created_at DESC
    """), {"cid": cid})
    return r.mappings().all()


@router.get("/invoices/{inv_id}/pdf")
async def my_invoice_pdf(
    inv_id: int,
    user=Depends(require_permission("invoices")),
    db: AsyncSession = Depends(get_db),
):
    """
    Descarga del PDF desde el portal cliente — encontrado en auditoría UX
    que el frontend apuntaba directo a `/api/admin/invoices/{id}/pdf`
    (require_admin), así que un cliente nunca podía descargar su propia
    factura sin loguearse como admin. `WHERE customer_id = :cid` en el
    mismo SELECT (no un chequeo separado) para que sea imposible pedir el
    PDF de la factura de otro cliente cambiando el id en la URL.
    """
    cid = _customer_id(user)
    r = await db.execute(text(
        "SELECT pdf_path FROM invoices WHERE id = :id AND customer_id = :cid"
    ), {"id": inv_id, "cid": cid})
    row = r.first()
    if not row or not row[0]:
        raise HTTPException(404, "Factura no encontrada")
    return FileResponse(row[0], media_type="application/pdf", filename=f"factura-{inv_id}.pdf")


@router.get("/trunk-guide")
async def trunk_guide(
    user=Depends(require_permission("trunk_guide")),
    db: AsyncSession = Depends(get_db),
):
    """
    Manual de trunk Asterisk personalizado con datos del cliente. `prefix`/
    `sip_conf`/`dialplan` (el prefijo PRINCIPAL) se mantienen sin cambios por
    compatibilidad — `prefixes` es nuevo: lista TODOS los prefijos del
    cliente (principal + campañas de customer_prefixes), cada uno con su
    propio fragmento de dialplan, para que un cliente con varias campañas de
    Vicidial/marcador sepa que puede (y cómo) configurar cada una por
    separado. Sin esto, el cliente nunca se entera de que la feature existe.
    """
    cid = _customer_id(user)
    r = await db.execute(text(
        "SELECT name, techprefix, currency FROM customers WHERE id=:cid"
    ), {"cid": cid})
    customer = dict(r.mappings().first() or {})

    public_ip = os.getenv("PUBLIC_IP", "")
    domain    = os.getenv("DOMAIN", "")

    def _dialplan_for(prefix: str) -> str:
        return f"""[voxikam-outbound]
; Marcar 51912345678 → tu Asterisk envía: {prefix or 'XXXX'}51912345678
exten => _X.,1,Dial(SIP/{prefix}${{EXTEN}}@voxikam-trunk)
 same  => n,Hangup()"""

    main_prefix = customer.get("techprefix") or ""
    prefixes = [{"techprefix": main_prefix, "label": "Principal", "dialplan": _dialplan_for(main_prefix)}] if main_prefix else []
    campaigns = await db.execute(text(
        "SELECT techprefix, label FROM customer_prefixes WHERE customer_id = :cid ORDER BY techprefix"
    ), {"cid": cid})
    for row in campaigns.mappings().all():
        prefixes.append({
            "techprefix": row["techprefix"],
            "label": row["label"] or row["techprefix"],
            "dialplan": _dialplan_for(row["techprefix"]),
        })

    return {
        "customer":  customer,
        "sbc_host":  public_ip,
        "sbc_port":  5060,
        "sbc_domain": domain,
        "prefix":    main_prefix,
        "prefixes":  prefixes,
        "sip_conf": f"""[voxikam-trunk]
type=peer
host={public_ip}
port=5060
insecure=port,invite
context=from-voxikam
disallow=all
allow=ulaw,alaw,g729""",
        "dialplan": _dialplan_for(main_prefix),
    }


# ── Selección de grupo de ruteo por prefijo ─────────────────────────────────
# El cliente elige qué GRUPO de ruteo usa cada uno de sus prefijos (principal
# + campañas) — pero NUNCA ve nombres/hosts reales de carriers, solo la
# etiqueta anónima del grupo (customer_carrier_groups.display_label, "Grupo
# 1"/"Grupo 2"/...) asignada una sola vez al momento en que el admin/reseller
# habilitó ese grupo para el cliente (ver assign_carrier_group() en
# customers.py/reseller.py). Reemplaza el pin de carrier único de antes — un
# grupo de 1 solo miembro es el equivalente exacto de "pinear un carrier".

class GroupChoiceIn(BaseModel):
    # None = "sin override, volver al grupo de dispatcher normal (todos los
    # carriers asignados vía customer_carriers, prioridad)". Nunca se expone
    # group_id real acá, solo el display_label anonimizado (ver
    # customers.py::assign_carrier_group).
    group_label: Optional[str] = None


@router.get("/carrier-groups")
async def my_carrier_groups(user=Depends(require_permission("carriers")), db: AsyncSession = Depends(get_db)):
    cid = _customer_id(user)
    r = await db.execute(text(
        "SELECT display_label FROM customer_carrier_groups WHERE customer_id = :cid ORDER BY group_id"
    ), {"cid": cid})
    return [{"label": row["display_label"]} for row in r.mappings().all()]


@router.get("/prefixes")
async def my_prefixes(user=Depends(require_permission("carriers")), db: AsyncSession = Depends(get_db)):
    cid = _customer_id(user)
    cust = await db.execute(text(
        "SELECT techprefix, routing_group_id FROM customers WHERE id = :cid"
    ), {"cid": cid})
    row = cust.mappings().first()
    prefixes = []
    if row and row["techprefix"]:
        prefixes.append({
            "prefix_ref": "main",
            "label": "Principal",
            "routing_group_id": row["routing_group_id"],
        })
    camp = await db.execute(text(
        "SELECT id, label, routing_group_id "
        "FROM customer_prefixes WHERE customer_id = :cid ORDER BY techprefix"
    ), {"cid": cid})
    for row in camp.mappings().all():
        prefixes.append({
            "prefix_ref": str(row["id"]),
            "label": row["label"] or f"Campaña {row['id']}",
            "routing_group_id": row["routing_group_id"],
        })

    # Resolver routing_group_id → display_label DESPUÉS de armar la lista
    # de prefijos — un solo SELECT en vez de uno por prefijo.
    labels = await db.execute(text(
        "SELECT group_id, display_label FROM customer_carrier_groups WHERE customer_id = :cid"
    ), {"cid": cid})
    label_by_group = {row["group_id"]: row["display_label"] for row in labels.mappings().all()}
    for p in prefixes:
        gid_active = p.pop("routing_group_id")
        p["active_group_label"] = label_by_group.get(gid_active) if gid_active else None
    return prefixes


@router.put("/prefixes/{prefix_ref}/group")
async def set_my_prefix_group(
    prefix_ref: str,
    body: GroupChoiceIn,
    user=Depends(require_permission("carriers")),
    db: AsyncSession = Depends(get_db),
):
    """
    `group_label=None` limpia el override (vuelve al grupo de dispatcher
    normal, todos los carriers asignados). `group_label` siempre se resuelve
    contra los grupos YA HABILITADOS para este cliente (customer_carrier_groups)
    — nunca acepta un group_id directo del cliente, así que no hay forma de
    que un cliente apunte a un grupo que no es suyo escribiendo el body a mano.
    """
    cid = _customer_id(user)
    group_id = None
    if body.group_label is not None:
        r = await db.execute(text(
            "SELECT group_id FROM customer_carrier_groups WHERE customer_id = :cid AND display_label = :label"
        ), {"cid": cid, "label": body.group_label})
        row = r.first()
        if not row:
            raise HTTPException(404, f"'{body.group_label}' no es uno de tus grupos habilitados")
        group_id = row[0]

    if prefix_ref == "main":
        exists = await db.execute(text("SELECT 1 FROM customers WHERE id = :cid"), {"cid": cid})
        if not exists.first():
            raise HTTPException(404, "Cliente no encontrado")
        await db.execute(text(
            "UPDATE customers SET routing_group_id = :group_id WHERE id = :cid"
        ), {"group_id": group_id, "cid": cid})
    else:
        try:
            prefix_id = int(prefix_ref)
        except ValueError:
            raise HTTPException(404, "Prefijo no encontrado")
        exists = await db.execute(text(
            "SELECT 1 FROM customer_prefixes WHERE id = :pid AND customer_id = :cid"
        ), {"pid": prefix_id, "cid": cid})
        if not exists.first():
            raise HTTPException(404, "Prefijo no encontrado")
        await db.execute(text(
            "UPDATE customer_prefixes SET routing_group_id = :group_id "
            "WHERE id = :pid AND customer_id = :cid"
        ), {"group_id": group_id, "pid": prefix_id, "cid": cid})
    await db.commit()

    # gen_dispatcher.py corre como subprocess del backend (mismo criterio
    # que customers.py::_sync_dispatcher) — el cambio recién toma efecto
    # real cuando termine de regenerar dispatcher.list/techprefix_map y
    # dispare kamcmd dispatcher.reload/htable.reload (o, en Docker, cuando
    # el watcher del host aplique el reload).
    _sync_dispatcher()
    return {"ok": True}


# ── API keys — autoservicio del cliente para /api/v1/* ────────────────────────

class ApiKeyIn(BaseModel):
    label: str = ""


@router.get("/api-keys")
async def list_api_keys(
    user=Depends(require_permission("api_access")),
    db: AsyncSession = Depends(get_db),
):
    """Nunca devuelve key_hash ni la key en texto plano — eso ya se mostró una sola vez al crearla."""
    r = await db.execute(text("""
        SELECT id, label, key_prefix, created_at, last_used_at, revoked
        FROM api_keys WHERE customer_id = :cid ORDER BY created_at DESC
    """), {"cid": _customer_id(user)})
    return r.mappings().all()


@router.post("/api-keys", status_code=201)
async def create_api_key(
    body: ApiKeyIn,
    user=Depends(require_permission("api_access")),
    db: AsyncSession = Depends(get_db),
):
    full_key = "vk_live_" + secrets.token_hex(24)
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    cid = _customer_id(user)
    result = await db.execute(text("""
        INSERT INTO api_keys (customer_id, label, key_prefix, key_hash)
        VALUES (:cid, :label, :prefix, :hash)
    """), {"cid": cid, "label": body.label, "prefix": full_key[:12], "hash": key_hash})
    await record_event(db, "api_key", result.lastrowid, "created",
                        user.get("name") or user.get("email") or f"customer:{cid}", body.label)
    await db.commit()
    # La key completa se devuelve UNA sola vez — a partir de acá solo se puede
    # ver el prefijo (mismo criterio que webhooks.py::create_webhook()).
    return {"ok": True, "api_key": full_key}


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: int,
    user=Depends(require_permission("api_access")),
    db: AsyncSession = Depends(get_db),
):
    cid = _customer_id(user)
    result = await db.execute(text("""
        UPDATE api_keys SET revoked = 1, revoked_at = NOW()
        WHERE id = :id AND customer_id = :cid AND revoked = 0
    """), {"id": key_id, "cid": cid})
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="API key no encontrada")
    await record_event(db, "api_key", key_id, "revoked",
                        user.get("name") or user.get("email") or f"customer:{cid}")
    await db.commit()
    return {"ok": True}
