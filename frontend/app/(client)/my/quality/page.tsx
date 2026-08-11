'use client'
import { ErrorBanner } from '@/components/ErrorBanner'
import { StatusBadge, type BadgeVariant } from '@/components/StatusBadge'
import { useEffect, useState } from 'react'
import { apiGet } from '@/lib/api'

interface QRow {
  ts_hour: string
  total: number; answered: number; short_calls: number
  c_487: number; c_486: number; c_404: number; c_503: number; c_other: number
  asr: number; short_pct: number; asr_color: string
}

const ASR_VARIANT: Record<string, BadgeVariant> = {
  green: 'success', yellow: 'warning', red: 'danger',
}

function AsrBadge({ asr, color }: { asr: number; color: string }) {
  return (
    <StatusBadge variant={ASR_VARIANT[color] ?? 'danger'} bordered mono className="font-bold">
      {asr}%
    </StatusBadge>
  )
}

function num(n: number) { return n.toLocaleString() }
function pct(n: number) { return `${n}%` }

export default function MyQualityPage() {
  const [rows, setRows]         = useState<QRow[]>([])
  const [totalDay, setTotalDay] = useState<any>(null)
  const [loading, setLoading]   = useState(false)
  const [date, setDate]         = useState(new Date().toISOString().slice(0, 10))
  const [error, setError]       = useState('')

  async function load() {
    setLoading(true); setError('')
    try {
      const d = await apiGet(`/quality/my?date=${date}`)
      setRows(d.rows); setTotalDay(d.total_day)
    } catch (e: any) { setError(e.message || 'Error cargando calidad') }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])
  useEffect(() => { document.title = 'Calidad de tráfico · VoxiKam' }, [])

  return (
    <div className="space-y-5">
      {error && <ErrorBanner>{error}</ErrorBanner>}
      <div>
        <h1 className="text-xl font-semibold text-[var(--color-text)]">Calidad de tráfico</h1>
        <p className="text-xs text-[var(--color-muted)] mt-0.5">
          <span title="Answer-Seizure Ratio — porcentaje de llamadas que se contestan sobre el total de intentos" className="underline decoration-dotted cursor-help">ASR</span>
          {' '}por hora · buzón · desglose de causas
        </p>
      </div>

      {/* Filtro fecha */}
      <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-4 flex gap-3 items-end">
        <div>
          <label htmlFor="quality-date" className="block text-xs text-[var(--color-text-2)] mb-1">Fecha</label>
          <input id="quality-date" type="date" value={date} onChange={e => setDate(e.target.value)}
            className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-3 py-1.5 text-sm text-[var(--color-text)] focus-ring" />
        </div>
        <button onClick={load}
          className="px-4 py-1.5 bg-brand-600 hover:bg-brand-500 text-white text-sm rounded focus-ring">
          Ver
        </button>
      </div>

      {/* Resumen del día */}
      {totalDay && totalDay.total > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-4">
            <p className="text-xs text-[var(--color-text-2)] uppercase tracking-wider">Total intentos</p>
            <p className="text-3xl font-bold font-mono tabular-nums text-[var(--color-text)] mt-1">{num(totalDay.total)}</p>
          </div>
          <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-4">
            <p className="text-xs text-[var(--color-text-2)] uppercase tracking-wider">Contestadas</p>
            <p className="text-3xl font-bold font-mono tabular-nums text-success mt-1">{num(totalDay.answered)}</p>
            <p className="text-xs text-[var(--color-muted)] mt-1">ASR del día: <AsrBadge asr={totalDay.asr} color={totalDay.asr_color} /></p>
          </div>
          <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-4">
            <p className="text-xs text-[var(--color-text-2)] uppercase tracking-wider">Buzón / &lt;5s</p>
            <p className="text-3xl font-bold font-mono tabular-nums text-warning mt-1">{num(totalDay.short_calls)}</p>
            <p className="text-xs text-[var(--color-muted)] mt-1">{pct(totalDay.short_pct)} del contestado</p>
          </div>
          <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-4">
            <p className="text-xs text-[var(--color-text-2)] uppercase tracking-wider">No contestadas</p>
            <p className="text-3xl font-bold font-mono tabular-nums text-danger mt-1">
              {num((totalDay.c_487 || 0) + (totalDay.c_486 || 0) + (totalDay.c_404 || 0) + (totalDay.c_503 || 0) + (totalDay.c_other || 0))}
            </p>
            <p className="text-xs text-[var(--color-muted)] mt-1">{pct(100 - totalDay.asr)} del total</p>
          </div>
        </div>
      )}

      {/* Tabla por hora */}
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
            <tbody className="divide-y divide-[var(--color-border)]">
              {rows.map((r, i) => (
                <tr key={i} className="hover:bg-white/2">
                  <td className="px-4 py-2 font-mono tabular-nums text-[var(--color-text-2)] font-medium">{r.ts_hour}</td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums text-[var(--color-text-2)]">{num(r.total)}</td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums text-success">{num(r.answered)}</td>
                  <td className="px-4 py-2 text-right"><AsrBadge asr={r.asr} color={r.asr_color} /></td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums text-warning">{pct(r.short_pct)}</td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums text-[var(--color-text-2)]">{num(r.c_487)}</td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums text-[var(--color-text-2)]">{num(r.c_486)}</td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums text-warning">{num(r.c_404)}</td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums text-danger">{num(r.c_503)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
