'use client'
import { Fragment, useState } from 'react'
import { apiGet } from '@/lib/api'

function money(n: any) { return `S/ ${parseFloat(n || 0).toFixed(2)}` }
function pct(n: any)   { return `${parseFloat(n || 0).toFixed(1)}%` }
function mins(n: any)  { return `${Math.round(parseFloat(n || 0))} min` }

function sumRows(rows: any[]) {
  return rows.reduce((acc, r) => ({
    nbcall:      (acc.nbcall || 0) + (r.nbcall || 0),
    sessiontime: (acc.sessiontime || 0) + (r.sessiontime || 0),
    buycost:     (acc.buycost || 0) + parseFloat(r.buycost || 0),
    sessionbill: (acc.sessionbill || 0) + parseFloat(r.sessionbill || 0),
    lucro:       (acc.lucro || 0) + parseFloat(r.lucro || 0),
  }), { nbcall: 0, sessiontime: 0, buycost: 0, sessionbill: 0, lucro: 0 })
}

function avgAsr(rows: any[]) {
  if (!rows.length) return 0
  return rows.reduce((a, r) => a + parseFloat(r.asr || 0), 0) / rows.length
}

function groupBy(rows: any[], key: string): Map<string, any[]> {
  const map = new Map<string, any[]>()
  for (const r of rows) {
    const k = r[key] ?? '—'
    if (!map.has(k)) map.set(k, [])
    map.get(k)!.push(r)
  }
  return map
}

export default function ReportsPage() {
  const today = new Date().toISOString().slice(0, 10)
  const month = today.slice(0, 7)

  const [tab, setTab]           = useState<'day' | 'month'>('month')
  const [date, setDate]         = useState(today)
  const [monthSel, setMonthSel] = useState(month)
  const [view, setView]         = useState<'customer' | 'carrier'>('customer')
  const [rows, setRows]         = useState<any[] | null>(null)
  const [loading, setLoading]   = useState(false)
  const [expanded, setExpanded] = useState<string | null>(null)

  async function generate() {
    setLoading(true); setRows(null); setExpanded(null)
    try {
      const q = tab === 'day' ? `date=${date}` : `month=${monthSel}`
      const d = await apiGet(`/admin/reports/${tab}?${q}`)
      setRows(d)
    } finally { setLoading(false) }
  }

  const byCustomer = rows ? groupBy(rows, 'customer_name') : null
  const byCarrier  = rows ? groupBy(rows, 'carrier_name')  : null
  const totals     = rows ? sumRows(rows) : null

  const card  = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'
  const th    = 'px-4 py-2.5 text-xs text-[var(--color-text-2)] uppercase tracking-wider font-medium'
  const td    = 'px-4 py-3 text-sm'
  const tfoot = 'px-4 py-2.5 text-sm font-semibold'

  function renderSummary(
    grouped: Map<string, any[]>,
    nameKey: 'customer_name' | 'carrier_name',
    subKey: 'carrier_name' | 'customer_name',
    prefix: string,
    subLabel: string,
  ) {
    const entries = Array.from(grouped.entries())
    return (
      <div className={`${card} overflow-hidden`}>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left border-b border-[var(--color-border)] bg-[var(--color-surface)]">
              <th className={`${th} text-left`}>{nameKey === 'customer_name' ? 'Cliente' : 'Carrier'}</th>
              <th className={`${th} text-right`}>Llamadas</th>
              <th className={`${th} text-right`}>Minutos</th>
              <th className={`${th} text-right`}>Compra</th>
              <th className={`${th} text-right`}>Venta</th>
              <th className={`${th} text-right`}>Ganancia</th>
              <th className={`${th} text-right`}>ASR</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--color-border)]/40">
            {entries.map(([name, grpRows]) => {
              const s   = sumRows(grpRows)
              const asr = avgAsr(grpRows)
              const key = `${prefix}_${name}`
              const exp = expanded === key

              return (
                <Fragment key={key}>
                  <tr onClick={() => setExpanded(exp ? null : key)}
                    className="hover:bg-white/3 cursor-pointer transition-colors">
                    <td className={`${td} font-medium`}>
                      <span className="text-[var(--color-muted)] mr-2 text-xs select-none">
                        {exp ? '▾' : '▸'}
                      </span>
                      {name}
                      <span className="text-xs text-[var(--color-muted)] ml-2">
                        {grpRows.length} {subLabel}{grpRows.length > 1 ? 's' : ''}
                      </span>
                    </td>
                    <td className={`${td} text-right font-mono`}>{s.nbcall}</td>
                    <td className={`${td} text-right font-mono text-[var(--color-text-2)]`}>
                      {mins(s.sessiontime / 60)}
                    </td>
                    <td className={`${td} text-right font-mono text-red-400`}>{money(s.buycost)}</td>
                    <td className={`${td} text-right font-mono text-blue-400`}>{money(s.sessionbill)}</td>
                    <td className={`${td} text-right font-mono text-green-400`}>{money(s.lucro)}</td>
                    <td className={`${td} text-right font-mono`}>{pct(asr)}</td>
                  </tr>

                  {exp && grpRows.map((r, i) => (
                    <tr key={i} className="bg-[var(--color-surface)]/60 border-b border-[var(--color-border)]/20">
                      <td className={`${td} pl-12 text-[var(--color-text-2)]`}>
                        <span className="mr-2 text-[var(--color-muted)]">↳</span>
                        {r[subKey] ?? '—'}
                      </td>
                      <td className={`${td} text-right font-mono text-[var(--color-text-2)]`}>{r.nbcall}</td>
                      <td className={`${td} text-right font-mono text-[var(--color-text-2)]`}>
                        {mins(r.sessiontime / 60)}
                      </td>
                      <td className={`${td} text-right font-mono text-red-400/70`}>{money(r.buycost)}</td>
                      <td className={`${td} text-right font-mono text-blue-400/70`}>{money(r.sessionbill)}</td>
                      <td className={`${td} text-right font-mono text-green-400/70`}>{money(r.lucro)}</td>
                      <td className={`${td} text-right font-mono text-[var(--color-text-2)]`}>{pct(r.asr)}</td>
                    </tr>
                  ))}
                </Fragment>
              )
            })}
          </tbody>
          {totals && (
            <tfoot>
              <tr className="border-t-2 border-[var(--color-border)] bg-[var(--color-surface)]">
                <td className={tfoot}>
                  Total — {grouped.size} {nameKey === 'customer_name' ? 'cliente' : 'carrier'}{grouped.size > 1 ? 's' : ''}
                </td>
                <td className={`${tfoot} text-right font-mono`}>{totals.nbcall}</td>
                <td className={`${tfoot} text-right font-mono`}>{mins(totals.sessiontime / 60)}</td>
                <td className={`${tfoot} text-right font-mono text-red-400`}>{money(totals.buycost)}</td>
                <td className={`${tfoot} text-right font-mono text-blue-400`}>{money(totals.sessionbill)}</td>
                <td className={`${tfoot} text-right font-mono text-green-400`}>{money(totals.lucro)}</td>
                <td className={tfoot} />
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold">Reportes</h1>

      {/* Barra de controles */}
      <div className={`${card} p-4 flex items-center gap-3 flex-wrap`}>
        {/* Día / Mes */}
        <div className="flex rounded-lg overflow-hidden border border-[var(--color-border)]">
          {(['day', 'month'] as const).map(t => (
            <button key={t} onClick={() => { setTab(t); setRows(null) }}
              className={`px-4 py-1.5 text-sm transition-colors ${
                tab === t
                  ? 'bg-brand-600 text-white'
                  : 'bg-[var(--color-surface)] text-[var(--color-text-2)] hover:text-[var(--color-text)]'
              }`}>
              {t === 'day' ? 'Día' : 'Mes'}
            </button>
          ))}
        </div>

        {tab === 'day' ? (
          <input type="date" value={date} onChange={e => { setDate(e.target.value); setRows(null) }}
            className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-brand-500" />
        ) : (
          <input type="month" value={monthSel} onChange={e => { setMonthSel(e.target.value); setRows(null) }}
            className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-brand-500" />
        )}

        <button onClick={generate} disabled={loading}
          className="bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm px-5 py-1.5 rounded-lg transition-colors font-medium">
          {loading ? 'Generando…' : 'Generar'}
        </button>

        {/* Vista por cliente / carrier — solo visible cuando hay datos */}
        {rows !== null && rows.length > 0 && (
          <div className="ml-auto flex rounded-lg overflow-hidden border border-[var(--color-border)]">
            {([
              ['customer', 'Por cliente'],
              ['carrier',  'Por carrier'],
            ] as const).map(([v, label]) => (
              <button key={v} onClick={() => { setView(v); setExpanded(null) }}
                className={`px-4 py-1.5 text-sm transition-colors ${
                  view === v
                    ? 'bg-brand-600/20 text-brand-400 border-b-2 border-brand-500'
                    : 'bg-[var(--color-surface)] text-[var(--color-text-2)] hover:text-[var(--color-text)]'
                }`}>
                {label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Estado inicial */}
      {rows === null && !loading && (
        <div className={`${card} p-14 text-center`}>
          <p className="text-[var(--color-muted)] text-sm">
            Selecciona el período y haz clic en{' '}
            <button onClick={generate}
              className="text-brand-400 hover:text-brand-300 font-medium underline underline-offset-2">
              Generar
            </button>{' '}
            para ver el reporte.
          </p>
        </div>
      )}

      {loading && (
        <div className={`${card} p-14 text-center`}>
          <p className="text-[var(--color-muted)] text-sm">Generando reporte…</p>
        </div>
      )}

      {rows !== null && !loading && rows.length === 0 && (
        <div className={`${card} p-14 text-center`}>
          <p className="text-[var(--color-muted)] text-sm">Sin datos para el período seleccionado.</p>
        </div>
      )}

      {/* Resultados */}
      {rows !== null && !loading && rows.length > 0 && view === 'customer' && byCustomer && (
        renderSummary(byCustomer, 'customer_name', 'carrier_name', 'cust', 'carrier')
      )}

      {rows !== null && !loading && rows.length > 0 && view === 'carrier' && byCarrier && (
        renderSummary(byCarrier, 'carrier_name', 'customer_name', 'carr', 'cliente')
      )}
    </div>
  )
}
