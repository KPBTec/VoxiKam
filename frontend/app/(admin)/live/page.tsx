'use client'
import { Fragment, useEffect, useState } from 'react'
import { apiGet, apiDelete } from '@/lib/api'
import { groupByCustomer } from '@/lib/liveGrouping'
import { ErrorBanner } from '@/components/ErrorBanner'
import { LiveIndicator } from '@/components/LiveIndicator'
import { ClickableRow } from '@/components/ClickableRow'

function sec2str(s: number) {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60
  if (h > 0) return `${h}h ${m}m`
  return `${m}m ${sec.toString().padStart(2, '0')}s`
}

const card = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'

export default function LivePage() {
  const [data,     setData]     = useState<any>(null)
  const [detail,   setDetail]   = useState<any[]>([])
  const [cleaning, setCleaning] = useState(false)
  const [cleanMsg, setCleanMsg] = useState('')
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)

  const load = async () => {
    try {
      const [s, d] = await Promise.all([
        apiGet('/admin/live'),
        apiGet('/admin/live/detail'),
      ])
      setData(s); setDetail(d); setError('')
    } catch (e: any) { setError(e.message || 'Error actualizando llamadas activas') }
  }

  const cleanStale = async () => {
    const stuckCount = detail.filter((r: any) => r.duration_sec > 3600).length
    if (!confirm(`¿Eliminar ${stuckCount} llamada(s) colgada(s) con más de 1 hora?`)) return
    setCleaning(true); setCleanMsg('')
    try {
      const r = await apiDelete('/admin/live/stale?max_minutes=60')
      setCleanMsg(`${r.deleted} registro(s) eliminado(s)`)
      await load()
    } catch {
      setCleanMsg('Error al limpiar')
    } finally {
      setCleaning(false)
      setTimeout(() => setCleanMsg(''), 5000)
    }
  }

  useEffect(() => {
    load()
    const t = setInterval(load, 10000)
    return () => clearInterval(t)
  }, [])

  const ongoing    = data?.kamailio?.ongoing    ?? 0
  const timbrando  = data?.kamailio?.connecting ?? 0
  const hasColgada = detail.some((r: any) => r.duration_sec > 3600)
  const maxDur     = detail.length > 0 ? Math.max(...detail.map((d: any) => d.duration_sec)) : 0
  const stale      = data != null && data?.kamailio?.available === false

  return (
    <div className="space-y-6">
      {error && <ErrorBanner>{error}</ErrorBanner>}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-[var(--color-text)]">Llamadas en curso</h1>
        <div className="flex items-center gap-3">
          {hasColgada && (
            <button
              onClick={cleanStale}
              disabled={cleaning}
              className="focus-ring flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-danger/15 border border-danger/40 text-danger hover:bg-danger/25 disabled:opacity-50 transition-colors"
            >
              {cleaning ? '…' : '🧹'} Limpiar colgadas
            </button>
          )}
          {cleanMsg ? <span className="text-xs text-[var(--color-muted)]">{cleanMsg}</span> : null}
          <LiveIndicator active label="Actualiza cada 10s" className="text-sm text-[var(--color-text-2)]" />
        </div>
      </div>

      {stale && (
        <div className="bg-warning/10 border border-warning/30 rounded-xl px-5 py-3 text-sm text-warning">
          ⚠ El snapshot de Kamailio no se actualiza — <strong>Contestadas/Timbrando/Clientes activos de abajo no son confiables ahora mismo</strong>.
          La tabla "Llamadas contestadas" sigue siendo real (viene de otra fuente). En el servidor: revisar el log de <code className="text-xs">cron_dlg_stats.py</code> (carpeta de logs root-only) o probar <code className="text-xs">kamcmd dlg.briefing ftcISs</code> a mano.
        </div>
      )}

      {/* KPIs */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <div className={`${card} p-5`}>
          <p className="text-xs text-[var(--color-text-2)] uppercase tracking-wider">Contestadas</p>
          <p className="text-4xl font-bold text-success mt-1">{ongoing}</p>
          <p className="text-xs text-[var(--color-muted)] mt-1">200 OK · confirmadas</p>
        </div>

        <div className={`${card} p-5`}>
          <p className="text-xs text-[var(--color-text-2)] uppercase tracking-wider">Timbrando</p>
          <p className="text-4xl font-bold text-warning mt-1">{timbrando}</p>
          <p className="text-xs text-[var(--color-muted)] mt-1">180 Ringing · sin contestar</p>
        </div>

        <div className={`${card} p-5`}>
          <p className="text-xs text-[var(--color-text-2)] uppercase tracking-wider">Clientes activos</p>
          <p className="text-4xl font-bold text-[var(--color-text)] mt-1">
            {groupByCustomer(data?.by_customer ?? []).filter((g: any) => g.active_calls > 0).length}
          </p>
        </div>

        <div className={`${card} p-5`}>
          <p className="text-xs text-[var(--color-text-2)] uppercase tracking-wider">Mayor tiempo</p>
          <p className="text-4xl font-bold text-[var(--color-text)] mt-1 font-mono">
            {maxDur > 0 ? sec2str(maxDur) : '—'}
          </p>
        </div>
      </div>

      {/* Por cliente */}
      {(data?.by_customer?.length ?? 0) > 0 && (
        <div className={`${card} overflow-x-auto`}>
          <div className="px-6 py-3 border-b border-[var(--color-border)]">
            <h2 className="text-sm font-medium text-[var(--color-text)]">Activas por cliente</h2>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-[var(--color-text-2)] uppercase border-b border-[var(--color-border)]">
                <th className="px-6 py-3 text-left">Cliente</th>
                <th className="px-6 py-3 text-right">Contestadas</th>
                <th className="px-6 py-3 text-right">Timbrando</th>
                <th className="px-6 py-3 text-right">Total</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              {groupByCustomer(data.by_customer).map((g: any) => {
                const key = g.rows[0].customer_id != null ? `c${g.rows[0].customer_id}` : `pfx${g.rows[0].prefijo}`
                const multi = g.rows.length > 1
                const isExp = expanded === key
                return (
                  <Fragment key={key}>
                    <ClickableRow onActivate={() => setExpanded(isExp ? null : key)} disabled={!multi}
                      className={`hover:bg-white/3 ${multi ? 'cursor-pointer' : ''}`}>
                      <td className="px-6 py-3 text-[var(--color-text)]">
                        {multi && (
                          <span className="text-[var(--color-muted)] mr-2 text-xs select-none">{isExp ? '▾' : '▸'}</span>
                        )}
                        {g.customer_name}
                        {multi && (
                          <span className="text-xs text-[var(--color-muted)] ml-2">{g.rows.length} grupos</span>
                        )}
                      </td>
                      <td className="px-6 py-3 text-right">
                        <span className="bg-success/15 text-success px-2 py-0.5 rounded-full text-xs font-mono">{g.active_calls}</span>
                      </td>
                      <td className="px-6 py-3 text-right">
                        <span className="bg-warning/15 text-warning px-2 py-0.5 rounded-full text-xs font-mono">{g.timbrando}</span>
                      </td>
                      <td className="px-6 py-3 text-right text-[var(--color-text-2)] text-xs font-mono">{g.total}</td>
                    </ClickableRow>
                    {multi && isExp && g.rows.map((r: any) => (
                      <tr key={r.prefijo} className="bg-[var(--color-surface)]/60">
                        <td className="px-6 py-2 pl-12 text-[var(--color-text-2)] text-xs">
                          <span className="mr-2 text-[var(--color-muted)]">↳</span>{r.label} ({r.prefijo})
                        </td>
                        <td className="px-6 py-2 text-right text-xs font-mono text-success/70">{r.active_calls}</td>
                        <td className="px-6 py-2 text-right text-xs font-mono text-warning/70">{r.timbrando}</td>
                        <td className="px-6 py-2 text-right text-xs font-mono text-[var(--color-muted)]">{r.total}</td>
                      </tr>
                    ))}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Detalle llamadas contestadas */}
      <div className={`${card} overflow-hidden`}>
        <div className="px-6 py-3 border-b border-[var(--color-border)]">
          <h2 className="text-sm font-medium text-[var(--color-text)]">
            Llamadas contestadas
            {detail.length > 0 && (
              <span className="ml-2 text-xs text-[var(--color-text-2)] font-normal">{detail.length} en curso</span>
            )}
          </h2>
          <p className="text-xs text-[var(--color-muted)] mt-0.5">Directo desde Kamailio · sin zombies</p>
        </div>
        {detail.length === 0 ? (
          <p className="px-6 py-10 text-center text-[var(--color-muted)] text-sm">Sin llamadas activas ahora mismo</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-[var(--color-text-2)] uppercase border-b border-[var(--color-border)]">
                  <th className="px-6 py-3 text-left">Cliente</th>
                  <th className="px-6 py-3 text-left">Carrier</th>
                  <th className="px-6 py-3 text-left">Origen</th>
                  <th className="px-6 py-3 text-left">Destino</th>
                  <th className="px-6 py-3 text-right">Inicio</th>
                  <th className="px-6 py-3 text-right">Duración</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border)]">
                {detail.map((r: any, i: number) => {
                  const stuck = r.duration_sec > 3600
                  return (
                    <tr key={r.call_id || i} className={`hover:bg-white/3 ${stuck ? 'bg-danger/10' : ''}`}>
                      <td className="px-6 py-3 text-[var(--color-text)]">{r.customer_name}</td>
                      <td className="px-6 py-3 text-xs text-[var(--color-text-2)]">{r.carrier_name ?? '—'}</td>
                      <td className="px-6 py-3 font-mono text-xs text-[var(--color-text-2)]">{r.origen}</td>
                      <td className="px-6 py-3 font-mono text-xs text-[var(--color-text)]">{r.destino}</td>
                      <td className="px-6 py-3 text-right font-mono text-[var(--color-text-2)] text-xs">
                        {r.started_at
                          ? new Date(r.started_at).toLocaleTimeString('es-PE', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
                          : r.tiempo}
                      </td>
                      <td className={`px-6 py-3 text-right font-mono text-xs ${stuck ? 'text-danger' : 'text-success'}`}>
                        {sec2str(r.duration_sec)}
                        {stuck && <span className="ml-1 text-danger" title="Posible llamada colgada">⚠</span>}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
