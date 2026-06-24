'use client'
import { useEffect, useState } from 'react'
import { apiGet } from '@/lib/api'

interface QRow {
  ts_hour: string
  total: number; answered: number; short_calls: number
  c_487: number; c_486: number; c_404: number; c_503: number; c_other: number
  asr: number; short_pct: number; asr_color: string
}

function AsrBadge({ asr, color }: { asr: number; color: string }) {
  const cls =
    color === 'green'  ? 'bg-green-500/20 text-green-400 border border-green-700/50' :
    color === 'yellow' ? 'bg-yellow-500/20 text-yellow-400 border border-yellow-700/50' :
                         'bg-red-500/20 text-red-400 border border-red-700/50'
  return (
    <span className={`px-2 py-0.5 rounded font-mono text-xs font-bold ${cls}`}>
      {asr}%
    </span>
  )
}

function num(n: number) { return n.toLocaleString() }
function pct(n: number) { return `${n}%` }

export default function MyQualityPage() {
  const [rows, setRows]         = useState<QRow[]>([])
  const [totalDay, setTotalDay] = useState<any>(null)
  const [loading, setLoading]   = useState(false)
  const [date, setDate]         = useState(new Date().toISOString().slice(0, 10))

  async function load() {
    setLoading(true)
    try {
      const d = await apiGet(`/quality/my?date=${date}`)
      setRows(d.rows); setTotalDay(d.total_day)
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-white">Calidad de tráfico</h1>
        <p className="text-xs text-zinc-500 mt-0.5">ASR por hora · buzón · desglose de causas</p>
      </div>

      {/* Filtro fecha */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 flex gap-3 items-end">
        <div>
          <label className="block text-xs text-zinc-400 mb-1">Fecha</label>
          <input type="date" value={date} onChange={e => setDate(e.target.value)}
            className="bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-sm text-white" />
        </div>
        <button onClick={load}
          className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded">
          Ver
        </button>
      </div>

      {/* Resumen del día */}
      {totalDay && totalDay.total > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
            <p className="text-xs text-zinc-400 uppercase tracking-wider">Total intentos</p>
            <p className="text-3xl font-bold text-white mt-1">{num(totalDay.total)}</p>
          </div>
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
            <p className="text-xs text-zinc-400 uppercase tracking-wider">Contestadas</p>
            <p className="text-3xl font-bold text-green-400 mt-1">{num(totalDay.answered)}</p>
            <p className="text-xs text-zinc-600 mt-1">ASR del día: <AsrBadge asr={totalDay.asr} color={totalDay.asr_color} /></p>
          </div>
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
            <p className="text-xs text-zinc-400 uppercase tracking-wider">Buzón / &lt;5s</p>
            <p className="text-3xl font-bold text-yellow-400 mt-1">{num(totalDay.short_calls)}</p>
            <p className="text-xs text-zinc-600 mt-1">{pct(totalDay.short_pct)} del contestado</p>
          </div>
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
            <p className="text-xs text-zinc-400 uppercase tracking-wider">No contestadas</p>
            <p className="text-3xl font-bold text-red-400 mt-1">
              {num((totalDay.c_487 || 0) + (totalDay.c_486 || 0) + (totalDay.c_404 || 0) + (totalDay.c_503 || 0) + (totalDay.c_other || 0))}
            </p>
            <p className="text-xs text-zinc-600 mt-1">{pct(100 - totalDay.asr)} del total</p>
          </div>
        </div>
      )}

      {/* Tabla por hora */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
        <div className="px-6 py-3 border-b border-zinc-800">
          <h2 className="text-sm font-medium text-white">Detalle por hora</h2>
        </div>
        {loading ? (
          <p className="p-8 text-center text-zinc-400 text-sm">Cargando…</p>
        ) : rows.length === 0 ? (
          <p className="p-8 text-center text-zinc-500 text-sm">Sin datos para esta fecha</p>
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="text-zinc-400 uppercase border-b border-zinc-800">
                <th className="px-4 py-2 text-left">Hora</th>
                <th className="px-4 py-2 text-right">Total</th>
                <th className="px-4 py-2 text-right">Contestadas</th>
                <th className="px-4 py-2 text-right">ASR</th>
                <th className="px-4 py-2 text-right">Buzón &lt;5s</th>
                <th className="px-4 py-2 text-right title" title="Request Terminated">487</th>
                <th className="px-4 py-2 text-right" title="Busy">486</th>
                <th className="px-4 py-2 text-right" title="Not Found">404</th>
                <th className="px-4 py-2 text-right" title="Unavailable">503</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {rows.map((r, i) => (
                <tr key={i} className="hover:bg-zinc-800/50">
                  <td className="px-4 py-2 font-mono text-zinc-300 font-medium">{r.ts_hour}</td>
                  <td className="px-4 py-2 text-right text-zinc-300">{num(r.total)}</td>
                  <td className="px-4 py-2 text-right text-green-400">{num(r.answered)}</td>
                  <td className="px-4 py-2 text-right"><AsrBadge asr={r.asr} color={r.asr_color} /></td>
                  <td className="px-4 py-2 text-right text-yellow-400">{pct(r.short_pct)}</td>
                  <td className="px-4 py-2 text-right text-zinc-400">{num(r.c_487)}</td>
                  <td className="px-4 py-2 text-right text-zinc-400">{num(r.c_486)}</td>
                  <td className="px-4 py-2 text-right text-orange-400">{num(r.c_404)}</td>
                  <td className="px-4 py-2 text-right text-red-400">{num(r.c_503)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
