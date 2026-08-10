# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
import time as _time

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from audit import diff_and_record
from auth import require_admin
from database import get_db

router = APIRouter()
log = logging.getLogger("live")

_SNAPSHOT_FILE = Path("/var/lib/voxikam/live_snapshot.json")
_STALE_AFTER_SECONDS = 90  # cron_dlg_stats.py escribe cada 4-12s (configurable, ver /config abajo) — más de esto y algo está fallando

# Intervalo del snapshot de dlg.briefing (cron_dlg_stats.py) — configurable
# desde el panel a pedido del usuario en vez de fijo en código, para no
# necesitar install.sh --update solo para ajustar este número. Valores
# fijos (no un input libre): cron_dlg_stats.py calcula ITERATIONS = 48 //
# interval para mantener el total por corrida siempre ~48s, dentro de la
# ventana de 60s del cron por-minuto (cron/voxikam) con margen — un valor
# arbitrario podría no dividir bien ese presupuesto.
DLG_STATS_ALLOWED_INTERVALS = (4, 8, 12)
DLG_STATS_DEFAULT_INTERVAL = 4


class DlgStatsIntervalIn(BaseModel):
    interval_seconds: int


@router.get("/config")
async def get_live_config(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("SELECT value FROM settings WHERE key_name = 'dlg_stats_interval_seconds'"))
    row = r.first()
    try:
        val = int(row[0]) if row and row[0] else DLG_STATS_DEFAULT_INTERVAL
    except (TypeError, ValueError):
        val = DLG_STATS_DEFAULT_INTERVAL
    if val not in DLG_STATS_ALLOWED_INTERVALS:
        val = DLG_STATS_DEFAULT_INTERVAL
    return {"interval_seconds": val, "allowed": list(DLG_STATS_ALLOWED_INTERVALS)}


@router.put("/config")
async def set_live_config(body: DlgStatsIntervalIn, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    if body.interval_seconds not in DLG_STATS_ALLOWED_INTERVALS:
        return {"ok": False, "error": f"Debe ser uno de estos valores: {', '.join(str(v) for v in DLG_STATS_ALLOWED_INTERVALS)} segundos"}

    before_row = await db.execute(text("SELECT value FROM settings WHERE key_name = 'dlg_stats_interval_seconds'"))
    before_val = before_row.scalar()
    before = {"interval_seconds": int(before_val) if before_val else DLG_STATS_DEFAULT_INTERVAL}

    await db.execute(text("""
        INSERT INTO settings (key_name, value, description)
        VALUES ('dlg_stats_interval_seconds', :v, 'Intervalo en segundos del snapshot de llamadas en vivo (cron_dlg_stats.py)')
        ON DUPLICATE KEY UPDATE value = :v
    """), {"v": str(body.interval_seconds)})

    await diff_and_record(db, "live_config", 1, before, body.model_dump(),
                           ["interval_seconds"], admin.get("name") or admin.get("email"))
    await db.commit()
    # cron_dlg_stats.py lee este valor de la DB en cada corrida (cada minuto) —
    # el cambio se aplica solo, sin reiniciar ningún servicio ni proceso.
    return {"ok": True}


def _read_snapshot() -> dict:
    try:
        return json.loads(_SNAPSHOT_FILE.read_text())
    except Exception:
        return {}


def _snapshot_is_fresh(snap: dict) -> bool:
    """
    Antes esto era `bool(snap)` — siempre True apenas existiera el archivo,
    sin importar qué tan viejo fuera. Si cron_dlg_stats.py se cuelga (kamcmd
    falla/cuelga), el archivo deja de actualizarse pero seguía marcado como
    "available" — el panel Live mostraba números viejos/en cero como si
    fueran el estado real, sin ninguna señal de que algo estaba mal.
    """
    ts = snap.get("ts")
    if not ts:
        return False
    try:
        age = (datetime.now() - datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")).total_seconds()
    except ValueError:
        return False
    return age <= _STALE_AFTER_SECONDS


async def _prefix_map(db) -> dict[str, dict]:
    """
    techprefix → {id, name, label}. Incluye tanto el techprefix principal de
    cada cliente (customers.techprefix, label="Principal") como sus prefijos
    de campaña (customer_prefixes.label — mismo criterio que portal.py::
    my_campaigns()) — cron_dlg_stats.py ya resuelve el `prefijo` exacto
    (longest-prefix-match contra la misma unión de ambas fuentes), así que
    acá alcanza con un lookup exacto por clave.

    El `label` es lo que permite en "Activas por cliente" (live.py) distinguir
    varias filas de UN MISMO cliente con varios prefijos de campaña — antes
    todas mostraban solo el nombre del cliente repetido, como si fueran
    clientes distintos.
    """
    r = await db.execute(text("""
        SELECT c.id, c.techprefix, c.name, 'Principal' AS label FROM customers c
        WHERE c.techprefix IS NOT NULL AND c.techprefix != ''
        UNION ALL
        SELECT cp.customer_id AS id, cp.techprefix, c.name,
               NULLIF(cp.label, '') AS label
        FROM customer_prefixes cp JOIN customers c ON c.id = cp.customer_id
    """))
    return {row["techprefix"]: {"id": row["id"], "name": row["name"], "label": row["label"] or row["techprefix"]}
            for row in r.mappings().all()}


def _resolve(prefijo: str, prefix_map: dict) -> dict | None:
    return prefix_map.get(prefijo)


async def _known_call_ids(db: AsyncSession, call_ids: list[str]) -> dict[str, str | None]:
    """
    {call_id: carrier_name} SOLO para los call_ids que de verdad tienen fila
    en active_calls — la fuente de verdad de "esta llamada sigue viva para
    el sistema". Un BYE duplicado/retransmitido puede confundir al módulo
    dialog interno de Kamailio y dejarlo reportando un diálogo como
    confirmado mucho después de haber cortado de verdad (CDR ya generado,
    active_calls ya borrada — ver CHANGELOG v2.55.1). Cualquier call_id que
    no aparezca en el resultado es una llamada zombie: ya terminó, Kamailio
    todavía no se dio cuenta. Usado por / y /detail para que el conteo de
    arriba y el listado de abajo cuenten siempre lo mismo.
    """
    if not call_ids:
        return {}
    r = await db.execute(text("""
        SELECT ac.call_id, ca.name AS carrier_name
        FROM active_calls ac
        LEFT JOIN carriers ca ON ca.id = ac.carrier_id
        WHERE ac.call_id IN :call_ids
    """).bindparams(bindparam("call_ids", expanding=True)), {"call_ids": call_ids})
    return {row["call_id"]: row["carrier_name"] for row in r.mappings().all()}


@router.get("")
async def live_calls(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    snap    = _read_snapshot()
    resumen = snap.get("resumen", {})
    por_pfx = snap.get("resumen_por_prefijo", [])
    calls   = snap.get("llamadas", [])

    raw_ongoing = resumen.get("llamadas_activas", 0)
    timbrando   = resumen.get("timbrando", 0)
    fresh       = _snapshot_is_fresh(snap)

    # Zombie cleanup silencioso — SOLO si el snapshot es reciente y confiable.
    # Antes esto corría con cualquier snapshot, incluido uno viejo/roto con
    # ongoing=0: con lim=max(0,0)=0, el subquery "ORDER BY... LIMIT 0" no
    # devuelve NINGUNA fila, así que "call_id NOT IN (nada)" hace match con
    # TODAS las filas — ¡borraba activas_calls entera creyendo que eran todas
    # zombies! Encontrado en vivo mientras se investigaba el reporte del
    # usuario de "0 arriba pero 20 llamadas reales abajo". Se basa en
    # raw_ongoing (lo que Kamailio CREE que hay) a propósito — este cleanup
    # ataca el caso contrario al de abajo: active_calls con MÁS filas viejas
    # de las que Kamailio dice, no menos.
    #
    # v2.57.3: la versión anterior mantenía "las N filas con started_at más
    # reciente" (N = raw_ongoing) y borraba el resto — asumía que una llamada
    # vieja siempre termina antes que una nueva, que NO es cierto: una
    # llamada larga iniciada a las 8:00 puede seguir viva mientras una corta
    # iniciada a las 8:15 ya cortó. Si la fila zombie de la de 8:15 nunca se
    # limpió a tiempo (BYE mal manejado, ver _known_call_ids), esta lógica
    # la "salvaba" por ser más reciente y borraba la de 8:00 — la que
    # seguía genuinamente activa. Encontrado en producción (vd1sbc2):
    # cambiar un grupo de ruteo no afecta llamadas ya establecidas, pero
    # coincidió con una tanda de churn de llamadas que disparó este cleanup
    # y borró la fila de una llamada real en curso — desapareció del panel
    # aunque siguió viva en Kamailio. Ahora cruza contra el CONJUNTO real de
    # call_id que el snapshot dice vivos (no una cuenta ni un orden), con un
    # margen de 30s para no pisarse con una llamada recién insertada que
    # todavía no aparece en el snapshot (cron_dlg_stats.py escribe c/5s).
    if fresh:
        total_db = (await db.execute(text("SELECT COUNT(*) FROM active_calls"))).scalar() or 0
        if total_db > raw_ongoing + 5:
            live_call_ids = [c["call_id"] for c in calls if c.get("call_id")]
            if live_call_ids:
                deleted = await db.execute(text("""
                    DELETE FROM active_calls
                    WHERE call_id NOT IN :live_ids
                      AND started_at < NOW() - INTERVAL 30 SECOND
                """).bindparams(bindparam("live_ids", expanding=True)), {"live_ids": live_call_ids})
                await db.commit()
                if deleted.rowcount:
                    log.warning("Auto-sync: %d zombie(s) eliminados", deleted.rowcount)

    # dlg.briefing puede seguir reportando una llamada como "contestada"
    # mucho después de haber cortado de verdad — un BYE duplicado/
    # retransmitido confunde al módulo dialog interno de Kamailio (ver
    # _known_call_ids y CHANGELOG v2.55.1). Recalculamos "ongoing" cruzando
    # cada llamada contra active_calls en vez de confiar en el conteo crudo
    # — mismo criterio que /detail, así las tarjetas de arriba y el listado
    # de abajo nunca se contradicen entre sí.
    call_ids   = [c.get("call_id", "") for c in calls if c.get("call_id")]
    known      = await _known_call_ids(db, call_ids)
    real_calls = [c for c in calls if not c.get("call_id") or c.get("call_id") in known]
    ongoing    = len(real_calls)
    total      = ongoing + timbrando

    active_by_prefix: dict[str, int] = {}
    for c in real_calls:
        pfx = c.get("prefijo", "")
        active_by_prefix[pfx] = active_by_prefix.get(pfx, 0) + 1

    # Enriquecer resumen_por_prefijo con nombre de cliente
    pmap = await _prefix_map(db)
    by_customer = []
    for entry in por_pfx:
        pfx         = entry.get("prefijo", "")
        cust        = _resolve(pfx, pmap)
        real_active = active_by_prefix.get(pfx, 0)
        by_customer.append({
            "prefijo":         pfx,
            "customer_id":     cust["id"]    if cust else None,
            "customer_name":   cust["name"]  if cust else pfx,
            "label":           cust["label"] if cust else None,
            "active_calls":    real_active,
            "timbrando":       entry.get("timbrando", 0),
            "total":           real_active + entry.get("timbrando", 0),
        })
    by_customer.sort(key=lambda x: -x["active_calls"])

    return {
        "total":       total,
        "by_customer": by_customer,
        "kamailio": {
            "ongoing":     ongoing,
            "connecting":  timbrando,
            "starting":    0,
            # antes era bool(snap) — True apenas existiera el archivo, sin
            # importar la antigüedad. Ahora refleja si de verdad es reciente.
            "available":   fresh,
            "snapshot_ts": snap.get("ts", ""),
        },
    }


@router.get("/detail")
async def live_detail(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    snap  = _read_snapshot()
    calls = snap.get("llamadas", [])

    if not calls:
        # Fallback: active_calls DB
        r = await db.execute(text("""
            SELECT ac.call_id, ac.src_number AS origen, ac.dst_number AS destino,
                   ac.src_ip AS ip_origen, ac.started_at,
                   c.name AS customer_name,
                   ca.name AS carrier_name,
                   TIMESTAMPDIFF(SECOND, ac.started_at, NOW()) AS duration_sec
            FROM active_calls ac
            JOIN customers c ON ac.customer_id = c.id
            LEFT JOIN carriers ca ON ca.id = ac.carrier_id
            ORDER BY ac.started_at
        """))
        rows = []
        for row in r.mappings().all():
            d = dict(row)
            if d.get("started_at"):
                d["started_at"] = d["started_at"].isoformat()
            rows.append(d)
        return rows

    pmap = await _prefix_map(db)
    now_ts = int(_time.time())

    # El snapshot liviano (dlg.briefing, cada 5s) no puede traer dlg_vars
    # custom como carrier_id (ver comentario grande sobre esto en gen_
    # dispatcher.py/kamailio.cfg.j2) — pero active_calls SÍ lo tiene, escrito
    # en tiempo real por Kamailio en cada event_route[dialog:start]
    # (kamailio.cfg.j2, INSERT INTO active_calls). Un solo cruce por call_id,
    # sin tocar Kamailio/AWK/ClickHouse.
    call_ids = [c.get("call_id", "") for c in calls if c.get("call_id")]
    carrier_by_call = await _known_call_ids(db, call_ids)

    result = []
    for c in calls:
        cid = c.get("call_id", "")
        # BYEs duplicados/retransmitidos pueden confundir al módulo dialog
        # interno de Kamailio: event_route[dialog:end] ya corrió y borró la
        # fila de active_calls (la llamada terminó de verdad, hay CDR), pero
        # dlg.briefing sigue reportándola como viva — se ve en Live como una
        # llamada zombie con duración creciente y sin carrier (nunca lo va a
        # tener, porque para el sistema de billing esa llamada ya cerró). Sin
        # fila en active_calls == terminada para nosotros — se excluye del
        # listado en vez de mostrarla fantasma con "—". Mismo criterio que
        # el endpoint / (arriba), vía _known_call_ids compartido.
        if cid and cid not in carrier_by_call:
            continue

        pfx     = c.get("prefijo", "")
        cust    = _resolve(pfx, pmap)
        start_ts = c.get("start_ts", 0)
        dur_sec  = max(now_ts - start_ts, 0) if start_ts else 0

        result.append({
            "call_id":       c.get("call_id", ""),
            "ip_origen":     c.get("ip_origen", ""),
            "origen":        c.get("origen", ""),
            "destino":       c.get("destino", ""),
            "prefijo":       pfx,
            "customer_name": cust["name"] if cust else pfx,
            "carrier_name":  carrier_by_call.get(c.get("call_id", "")),
            "tiempo":        c.get("tiempo", "00:00:00"),
            "duration_sec":  dur_sec,
            # ISO UTC para que el browser muestre hora local correcta
            "started_at":    datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat() if start_ts else None,
        })

    return sorted(result, key=lambda x: -(x.get("duration_sec") or 0))


@router.get("/connecting")
async def live_connecting(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    r = await db.execute(text("""
        SELECT
            st.call_id,
            st.from_uri                                          AS src_number,
            REGEXP_REPLACE(st.to_uri, '^[0-9]{2,6}(51[0-9]+)$', '\\\\1')
                                                                 AS dst_number,
            st.to_uri                                            AS dst_raw,
            MIN(st.captured_at)                                  AS started_at,
            TIMESTAMPDIFF(SECOND, MIN(st.captured_at), NOW())   AS ring_sec,
            COALESCE(cu.name, 'Desconocido')                     AS customer_name
        FROM sip_traces st
        LEFT JOIN customer_ips ci ON ci.ip = st.src_ip
        LEFT JOIN customers    cu ON cu.id = ci.customer_id
        WHERE st.captured_at >= NOW() - INTERVAL 3 MINUTE
          AND st.sip_method   = 'INVITE'
          AND st.call_id NOT IN (
              SELECT DISTINCT s2.call_id
              FROM sip_traces s2
              WHERE s2.captured_at >= NOW() - INTERVAL 3 MINUTE
                AND (s2.sip_status = 200 OR s2.sip_method IN ('BYE','CANCEL')
                     OR s2.sip_status >= 300)
          )
        GROUP BY st.call_id, st.from_uri, st.to_uri, cu.name
        ORDER BY started_at ASC
        LIMIT 500
    """))
    rows = []
    for r_ in r.mappings().all():
        rows.append({
            "call_id":       r_["call_id"],
            "src_number":    r_["src_number"],
            "dst_number":    r_["dst_number"] or r_["dst_raw"],
            "started_at":    r_["started_at"].isoformat() if r_["started_at"] else None,
            "ring_sec":      r_["ring_sec"],
            "customer_name": r_["customer_name"],
        })
    return rows


@router.delete("/stale")
async def cleanup_stale(
    max_minutes: int = 60,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    r = await db.execute(text("""
        DELETE FROM active_calls
        WHERE TIMESTAMPDIFF(MINUTE, started_at, NOW()) > :max_min
    """), {"max_min": max_minutes})
    await db.commit()
    return {"deleted": r.rowcount, "max_minutes": max_minutes}
