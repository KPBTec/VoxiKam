'use client'
import { useEffect, useState } from 'react'
import { apiGet, apiDelete } from '@/lib/api'

function sec2str(s: number) {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60
  if (h > 0) return `${h}h ${m}m`
  return `${m}m ${sec.toString().padStart(2, '0')}s`
}

export default function LivePage() {
  const [data,     setData]     = useState<any>(null)
  const [detail,   setDetail]   = useState<any[]>([])
  const [cleaning, setCleaning] = useState(false)
  const [cleanMsg, setCleanMsg] = useState('')

  const load = async () => {
    const [s, d] = await Promise.all([
      apiGet('/admin/live'),
      apiGet('/admin/live/detail'),
    ])
    setData(s); setDetail(d)
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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-white">Llamadas en curso</h1>
        <div className="flex items-center gap-3">
          {hasColgada && (
            <button
              onClick={cleanStale}
              disabled={cleaning}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-red-950/60 border border-red-800/60 text-red-400 hover:bg-red-900/60 disabled:opacity-50 transition-colors"
            >
              {cleaning ? '…' : '🧹'} Limpiar colgadas
            </button>
          )}
          {cleanMsg ? <span className="text-xs text-zinc-400">{cleanMsg}</span> : null}
          <div className="flex items-center gap-2 text-sm text-zinc-400">
            <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            Actualiza cada 10s
          </div>
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
          <p className="text-xs text-zinc-400 uppercase tracking-wider">Contestadas</p>
          <p className="text-4xl font-bold text-green-400 mt-1">{ongoing}</p>
          <p className="text-xs text-zinc-600 mt-1">200 OK · confirmadas</p>
        </div>

        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
          <p className="text-xs text-zinc-400 uppercase tracking-wider">Timbrando</p>
          <p className="text-4xl font-bold text-yellow-400 mt-1">{timbrando}</p>
          <p className="text-xs text-zinc-600 mt-1">180 Ringing · sin contestar</p>
        </div>

        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
          <p className="text-xs text-zinc-400 uppercase tracking-wider">Clientes activos</p>
          <p className="text-4xl font-bold text-white mt-1">
            {data?.by_customer?.filter((c: any) => c.active_calls > 0).length ?? 0}
          </p>
        </div>

        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
          <p className="text-xs text-zinc-400 uppercase tracking-wider">Mayor tiempo</p>
          <p className="text-4xl font-bold text-white mt-1 font-mono">
            {maxDur > 0 ? sec2str(maxDur) : '—'}
          </p>
        </div>
      </div>

      {/* Por cliente */}
      {(data?.by_customer?.length ?? 0) > 0 && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
          <div className="px-6 py-3 border-b border-zinc-800">
            <h2 className="text-sm font-medium text-white">Activas por cliente</h2>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-zinc-400 uppercase border-b border-zinc-800">
                <th className="px-6 py-3 text-left">Cliente</th>
                <th className="px-6 py-3 text-right">Contestadas</th>
                <th className="px-6 py-3 text-right">Timbrando</th>
                <th className="px-6 py-3 text-right">Total</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {data.by_customer.map((r: any) => (
                <tr key={r.prefijo} className="hover:bg-zinc-800/50">
                  <td className="px-6 py-3 text-white">{r.customer_name}</td>
                  <td className="px-6 py-3 text-right">
                    <span className="bg-green-500/15 text-green-400 px-2 py-0.5 rounded-full text-xs font-mono">{r.active_calls}</span>
                  </td>
                  <td className="px-6 py-3 text-right">
                    <span className="bg-yellow-500/15 text-yellow-400 px-2 py-0.5 rounded-full text-xs font-mono">{r.timbrando}</span>
                  </td>
                  <td className="px-6 py-3 text-right text-zinc-400 text-xs font-mono">{r.total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Detalle llamadas contestadas */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
        <div className="px-6 py-3 border-b border-zinc-800">
          <h2 className="text-sm font-medium text-white">
            Llamadas contestadas
            {detail.length > 0 && (
              <span className="ml-2 text-xs text-zinc-400 font-normal">{detail.length} en curso</span>
            )}
          </h2>
          <p className="text-xs text-zinc-600 mt-0.5">Directo desde Kamailio · sin zombies</p>
        </div>
        {detail.length === 0 ? (
          <p className="px-6 py-10 text-center text-zinc-500 text-sm">Sin llamadas activas ahora mismo</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-zinc-400 uppercase border-b border-zinc-800">
                <th className="px-6 py-3 text-left">Cliente</th>
                <th className="px-6 py-3 text-left">Origen</th>
                <th className="px-6 py-3 text-left">Destino</th>
                <th className="px-6 py-3 text-right">Inicio</th>
                <th className="px-6 py-3 text-right">Duración</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {detail.map((r: any, i: number) => {
                const stuck = r.duration_sec > 3600
                return (
                  <tr key={r.call_id || i} className={`hover:bg-zinc-800/50 ${stuck ? 'bg-red-950/20' : ''}`}>
                    <td className="px-6 py-3 text-white">{r.customer_name}</td>
                    <td className="px-6 py-3 font-mono text-xs text-zinc-300">{r.origen}</td>
                    <td className="px-6 py-3 font-mono text-xs text-white">{r.destino}</td>
                    <td className="px-6 py-3 text-right font-mono text-zinc-400 text-xs">
                      {r.started_at
                        ? new Date(r.started_at).toLocaleTimeString('es-PE', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
                        : r.tiempo}
                    </td>
                    <td className={`px-6 py-3 text-right font-mono text-xs ${stuck ? 'text-red-400' : 'text-green-400'}`}>
                      {sec2str(r.duration_sec)}
                      {stuck && <span className="ml-1 text-red-500" title="Posible llamada colgada">⚠</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
