'use client'
import { useEffect, useState } from 'react'
import { apiGet } from '@/lib/api'

interface QRow {
  ts_hour: string; customer_name: string; customer_id: number
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

export default function QualityPage() {
  const [rows, setRows]     = useState<QRow[]>([])
  const [totals, setTotals] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [date, setDate]     = useState(new Date().toISOString().slice(0, 10))
  const [custId, setCustId] = useState('')
  const [customers, setCustomers] = useState<any[]>([])

  useEffect(() => {
    apiGet('/admin/customers').then(setCustomers)
  }, [])

  async function load() {
    setLoading(true)
    try {
      const p = new URLSearchParams({ date })
      if (custId) p.set('customer_id', custId)
      const d = await apiGet(`/quality/admin?${p}`)
      setRows(d.rows); setTotals(d.totals)
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">Calidad ASR</h1>
          <p className="text-xs text-zinc-500 mt-0.5">Answer-Seizure Ratio · resumen horario por cliente</p>
        </div>
      </div>

      {/* Filtros */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 flex flex-wrap gap-3 items-end">
        <div>
          <label className="block text-xs text-zinc-400 mb-1">Fecha</label>
          <input type="date" value={date} onChange={e => setDate(e.target.value)}
            className="bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-sm text-white" />
        </div>
        <div>
          <label className="block text-xs text-zinc-400 mb-1">Cliente</label>
          <select value={custId} onChange={e => setCustId(e.target.value)}
            className="bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-sm text-white">
            <option value="">Todos</option>
            {customers.map((c: any) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>
        <button onClick={load}
          className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded">
          Filtrar
        </button>
      </div>

      {/* Resumen del día por cliente */}
      {totals.length > 0 && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
          <div className="px-6 py-3 border-b border-zinc-800">
            <h2 className="text-sm font-medium text-white">Resumen del día</h2>
          </div>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-zinc-400 uppercase border-b border-zinc-800">
                <th className="px-4 py-2 text-left">Cliente</th>
                <th className="px-4 py-2 text-right">Total</th>
                <th className="px-4 py-2 text-right">Contestadas</th>
                <th className="px-4 py-2 text-right">ASR</th>
                <th className="px-4 py-2 text-right">Buzón &lt;5s</th>
                <th className="px-4 py-2 text-right">487</th>
                <th className="px-4 py-2 text-right">486</th>
                <th className="px-4 py-2 text-right">404</th>
                <th className="px-4 py-2 text-right">503</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {totals.map((t: any) => (
                <tr key={t.customer_id} className="hover:bg-zinc-800/50 font-medium">
                  <td className="px-4 py-2 text-white">{t.customer_name}</td>
                  <td className="px-4 py-2 text-right text-zinc-300">{num(t.total)}</td>
                  <td className="px-4 py-2 text-right text-green-400">{num(t.answered)}</td>
                  <td className="px-4 py-2 text-right"><AsrBadge asr={t.asr} color={t.asr_color} /></td>
                  <td className="px-4 py-2 text-right text-yellow-400">{pct(t.short_pct)}</td>
                  <td className="px-4 py-2 text-right text-zinc-400">{num(t.c_487)}</td>
                  <td className="px-4 py-2 text-right text-zinc-400">{num(t.c_486)}</td>
                  <td className="px-4 py-2 text-right text-orange-400">{num(t.c_404)}</td>
                  <td className="px-4 py-2 text-right text-red-400">{num(t.c_503)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Detalle por hora */}
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
                <th className="px-4 py-2 text-left">Cliente</th>
                <th className="px-4 py-2 text-right">Total</th>
                <th className="px-4 py-2 text-right">Contestadas</th>
                <th className="px-4 py-2 text-right">ASR</th>
                <th className="px-4 py-2 text-right">Buzón &lt;5s</th>
                <th className="px-4 py-2 text-right">487</th>
                <th className="px-4 py-2 text-right">486</th>
                <th className="px-4 py-2 text-right">404</th>
                <th className="px-4 py-2 text-right">503</th>
                <th className="px-4 py-2 text-right">Otros</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {rows.map((r, i) => (
                <tr key={i} className="hover:bg-zinc-800/50">
                  <td className="px-4 py-2 font-mono text-zinc-400">{r.ts_hour}</td>
                  <td className="px-4 py-2 text-white">{r.customer_name}</td>
                  <td className="px-4 py-2 text-right text-zinc-300">{num(r.total)}</td>
                  <td className="px-4 py-2 text-right text-green-400">{num(r.answered)}</td>
                  <td className="px-4 py-2 text-right"><AsrBadge asr={r.asr} color={r.asr_color} /></td>
                  <td className="px-4 py-2 text-right text-yellow-400">{pct(r.short_pct)}</td>
                  <td className="px-4 py-2 text-right text-zinc-400">{num(r.c_487)}</td>
                  <td className="px-4 py-2 text-right text-zinc-400">{num(r.c_486)}</td>
                  <td className="px-4 py-2 text-right text-orange-400">{num(r.c_404)}</td>
                  <td className="px-4 py-2 text-right text-red-400">{num(r.c_503)}</td>
                  <td className="px-4 py-2 text-right text-zinc-500">{num(r.c_other)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
