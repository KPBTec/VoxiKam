'use client'
import { useEffect, useState } from 'react'
import { apiGet } from '@/lib/api'
import { StatusBadge, type BadgeVariant } from '@/components/StatusBadge'
import { ErrorBanner } from '@/components/ErrorBanner'

interface QRow {
  ts_hour: string; customer_name: string; customer_id: number
  total: number; answered: number; short_calls: number
  c_487: number; c_486: number; c_404: number; c_503: number; c_other: number
  asr: number; short_pct: number; asr_color: string
}

function AsrBadge({ asr, color }: { asr: number; color: string }) {
  const variant: BadgeVariant = color === 'green' ? 'success' : color === 'yellow' ? 'warning' : 'danger'
  return (
    <StatusBadge variant={variant} bordered mono rounded="md" className="font-bold">
      {asr}%
    </StatusBadge>
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
  const [error, setError] = useState('')

  useEffect(() => {
    apiGet('/admin/customers').then(setCustomers).catch((e: any) => setError(e.message))
  }, [])

  async function load() {
    setLoading(true); setError('')
    try {
      const p = new URLSearchParams({ date })
      if (custId) p.set('customer_id', custId)
      const d = await apiGet(`/quality/admin?${p}`)
      setRows(d.rows); setTotals(d.totals)
    } catch (e: any) { setError(e.message || 'Error cargando calidad') }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  return (
    <div className="space-y-5">
      {error && <ErrorBanner>{error}</ErrorBanner>}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-[var(--color-text)]">Calidad ASR</h1>
          <p className="text-xs text-[var(--color-muted)] mt-0.5">Answer-Seizure Ratio · resumen horario por cliente</p>
        </div>
      </div>

      {/* Filtros */}
      <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-4 flex flex-wrap gap-3 items-end">
        <div>
          <label className="block text-xs text-[var(--color-text-2)] mb-1">Fecha</label>
          <input type="date" value={date} onChange={e => setDate(e.target.value)}
            className="focus-ring bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-3 py-1.5 text-sm text-[var(--color-text)]" />
        </div>
        <div>
          <label className="block text-xs text-[var(--color-text-2)] mb-1">Cliente</label>
          <select value={custId} onChange={e => setCustId(e.target.value)}
            className="focus-ring bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-3 py-1.5 text-sm text-[var(--color-text)]">
            <option value="">Todos</option>
            {customers.map((c: any) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>
        <button onClick={load}
          className="focus-ring px-4 py-1.5 bg-brand-600 hover:bg-brand-500 text-white text-sm rounded">
          Filtrar
        </button>
      </div>

      {/* Resumen del día por cliente */}
      {totals.length > 0 && (
        <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl overflow-x-auto">
          <div className="px-6 py-3 border-b border-[var(--color-border)]">
            <h2 className="text-sm font-medium text-[var(--color-text)]">Resumen del día</h2>
          </div>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-[var(--color-text-2)] uppercase border-b border-[var(--color-border)]">
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
            <tbody className="divide-y divide-[var(--color-border)]">
              {totals.map((t: any) => (
                <tr key={t.customer_id} className="hover:bg-white/2 font-medium">
                  <td className="px-4 py-2 text-[var(--color-text)]">{t.customer_name}</td>
                  <td className="px-4 py-2 text-right font-mono text-[var(--color-text)]">{num(t.total)}</td>
                  <td className="px-4 py-2 text-right font-mono text-success">{num(t.answered)}</td>
                  <td className="px-4 py-2 text-right"><AsrBadge asr={t.asr} color={t.asr_color} /></td>
                  <td className="px-4 py-2 text-right font-mono text-warning">{pct(t.short_pct)}</td>
                  <td className="px-4 py-2 text-right font-mono text-[var(--color-text-2)]">{num(t.c_487)}</td>
                  <td className="px-4 py-2 text-right font-mono text-[var(--color-text-2)]">{num(t.c_486)}</td>
                  <td className="px-4 py-2 text-right font-mono text-warning">{num(t.c_404)}</td>
                  <td className="px-4 py-2 text-right font-mono text-danger">{num(t.c_503)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Detalle por hora */}
      <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl overflow-x-auto">
        <div className="px-6 py-3 border-b border-[var(--color-border)]">
          <h2 className="text-sm font-medium text-[var(--color-text)]">Detalle por hora</h2>
        </div>
        {loading ? (
          <p className="p-8 text-center text-[var(--color-text-2)] text-sm">Cargando…</p>
        ) : rows.length === 0 ? (
          <p className="p-8 text-center text-[var(--color-muted)] text-sm">Sin datos para esta fecha</p>
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="text-[var(--color-text-2)] uppercase border-b border-[var(--color-border)]">
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
            <tbody className="divide-y divide-[var(--color-border)]">
              {rows.map((r, i) => (
                <tr key={i} className="hover:bg-white/2">
                  <td className="px-4 py-2 font-mono text-[var(--color-text-2)]">{r.ts_hour}</td>
                  <td className="px-4 py-2 text-[var(--color-text)]">{r.customer_name}</td>
                  <td className="px-4 py-2 text-right font-mono text-[var(--color-text)]">{num(r.total)}</td>
                  <td className="px-4 py-2 text-right font-mono text-success">{num(r.answered)}</td>
                  <td className="px-4 py-2 text-right"><AsrBadge asr={r.asr} color={r.asr_color} /></td>
                  <td className="px-4 py-2 text-right font-mono text-warning">{pct(r.short_pct)}</td>
                  <td className="px-4 py-2 text-right font-mono text-[var(--color-text-2)]">{num(r.c_487)}</td>
                  <td className="px-4 py-2 text-right font-mono text-[var(--color-text-2)]">{num(r.c_486)}</td>
                  <td className="px-4 py-2 text-right font-mono text-warning">{num(r.c_404)}</td>
                  <td className="px-4 py-2 text-right font-mono text-danger">{num(r.c_503)}</td>
                  <td className="px-4 py-2 text-right font-mono text-[var(--color-muted)]">{num(r.c_other)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
