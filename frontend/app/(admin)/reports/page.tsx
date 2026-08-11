'use client'
import { Fragment, useEffect, useState } from 'react'
import { apiGet } from '@/lib/api'
import { ErrorBanner } from '@/components/ErrorBanner'
import { ClickableRow } from '@/components/ClickableRow'
import { Button } from '@/components/Button'
import { Card } from '@/components/Card'

const MONTH_NAMES = [
  'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
]

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
  useEffect(() => { document.title = 'Consumos · VoxiKam' }, [])

  const today = new Date().toISOString().slice(0, 10)
  const month = today.slice(0, 7)

  const [tab, setTab]           = useState<'day' | 'month'>('month')
  const [date, setDate]         = useState(today)
  const [monthSel, setMonthSel] = useState(month)
  const [view, setView]         = useState<'customer' | 'carrier' | 'provider'>('customer')
  const [rows, setRows]         = useState<any[] | null>(null)
  const [loading, setLoading]   = useState(true) // arranca en true: el useEffect dispara el primer fetch al montar
  const [expanded, setExpanded] = useState<string | null>(null)
  const [error, setError] = useState('')
  // null mientras carga — hasta entonces el selector no debe ofrecer años sin
  // datos reales (mismo criterio que /my/reports, ver portal.py::my_report_range()).
  const [range, setRange] = useState<{ min_month: string | null; current_month: string } | null>(null)

  useEffect(() => {
    apiGet('/admin/reports/range').then(setRange).catch(() => setRange({ min_month: null, current_month: month }))
  }, [])

  const minMonth = range?.min_month ?? range?.current_month ?? month
  const maxMonth = range?.current_month ?? month
  const [yearSel, monthNumSel] = monthSel.split('-').map(Number)
  const [minYear] = minMonth.split('-').map(Number)
  const [maxYear] = maxMonth.split('-').map(Number)
  const YEARS = Array.from({ length: maxYear - minYear + 1 }, (_, i) => maxYear - i)
  const MONTHS_FOR_YEAR = MONTH_NAMES
    .map((name, i) => ({ name, num: i + 1, key: `${yearSel}-${String(i + 1).padStart(2, '0')}` }))
    .filter(({ key }) => key >= minMonth && key <= maxMonth)

  function handleMonthNum(m: number) {
    setMonthSel(`${yearSel}-${String(m).padStart(2, '0')}`)
  }
  function handleYear(y: number) {
    const candidates = MONTH_NAMES
      .map((_, i) => `${y}-${String(i + 1).padStart(2, '0')}`)
      .filter(key => key >= minMonth && key <= maxMonth)
    const target = candidates.includes(`${y}-${String(monthNumSel).padStart(2, '0')}`)
      ? `${y}-${String(monthNumSel).padStart(2, '0')}`
      : candidates[candidates.length - 1]
    setMonthSel(target)
  }

  async function loadCustomerCarrier() {
    setLoading(true); setExpanded(null); setError('')
    try {
      const q = tab === 'day' ? `date=${date}` : `month=${monthSel}`
      const d = await apiGet(`/admin/reports/${tab}?${q}`)
      setRows(d)
    } catch (e: any) { setError(e.message || 'Error generando el reporte') }
    finally { setLoading(false) }
  }

  // Genera automáticamente al entrar y cada vez que cambia el período o la
  // vista — antes había que apretar "Generar" a mano cada vez, lo que se veía
  // como que "faltaba sincronizar" al abrir la página en blanco.
  useEffect(() => {
    loadCustomerCarrier()
  }, [tab, date, monthSel, view]) // eslint-disable-line react-hooks/exhaustive-deps

  function generate() {
    loadCustomerCarrier()
  }

  const byCustomer = rows ? groupBy(rows, 'customer_name') : null
  const byCarrier  = rows ? groupBy(rows, 'carrier_name')  : null
  const byProvider = rows ? groupBy(rows, 'provider_name') : null
  const totals     = rows ? sumRows(rows) : null

  const th    = 'px-4 py-2.5 text-xs text-[var(--color-text-2)] uppercase tracking-wider font-medium'
  const td    = 'px-4 py-3 text-sm'
  const tfoot = 'px-4 py-2.5 text-sm font-semibold'

  const NAME_LABELS: Record<string, string> = { customer_name: 'Cliente', carrier_name: 'Carrier', provider_name: 'Proveedor' }

  function renderSummary(
    grouped: Map<string, any[]>,
    nameKey: 'customer_name' | 'carrier_name' | 'provider_name',
    subKey: 'carrier_name' | 'customer_name',
    prefix: string,
    subLabel: string,
  ) {
    const entries = Array.from(grouped.entries())
    return (
      <Card className="overflow-x-auto">
        <table className="w-full text-sm tabular-nums">
          <thead>
            <tr className="text-left border-b border-[var(--color-border)] bg-[var(--color-surface)]">
              <th className={`${th} text-left`}>{NAME_LABELS[nameKey]}</th>
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
                  <ClickableRow onActivate={() => setExpanded(exp ? null : key)}
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
                    <td className={`${td} text-right font-mono text-danger`}>{money(s.buycost)}</td>
                    <td className={`${td} text-right font-mono text-brand-400`}>{money(s.sessionbill)}</td>
                    <td className={`${td} text-right font-mono text-success`}>{money(s.lucro)}</td>
                    <td className={`${td} text-right font-mono`}>{pct(asr)}</td>
                  </ClickableRow>

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
                      <td className={`${td} text-right font-mono text-danger/70`}>{money(r.buycost)}</td>
                      <td className={`${td} text-right font-mono text-brand-400/70`}>{money(r.sessionbill)}</td>
                      <td className={`${td} text-right font-mono text-success/70`}>{money(r.lucro)}</td>
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
                  Total — {grouped.size} {NAME_LABELS[nameKey].toLowerCase()}{grouped.size > 1 ? 's' : ''}
                </td>
                <td className={`${tfoot} text-right font-mono`}>{totals.nbcall}</td>
                <td className={`${tfoot} text-right font-mono`}>{mins(totals.sessiontime / 60)}</td>
                <td className={`${tfoot} text-right font-mono text-danger`}>{money(totals.buycost)}</td>
                <td className={`${tfoot} text-right font-mono text-brand-400`}>{money(totals.sessionbill)}</td>
                <td className={`${tfoot} text-right font-mono text-success`}>{money(totals.lucro)}</td>
                <td className={tfoot} />
              </tr>
            </tfoot>
          )}
        </table>
      </Card>
    )
  }

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold">Consumos</h1>

      {error && <ErrorBanner>{error}</ErrorBanner>}

      {/* Barra de controles */}
      <Card className="p-4 flex items-center gap-3 flex-wrap">
        {/* Día / Mes */}
        <div className="flex rounded-lg overflow-hidden border border-[var(--color-border)]">
          {(['day', 'month'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={`focus-ring px-4 py-1.5 text-sm transition-colors ${
                tab === t
                  ? 'bg-brand-600 text-white'
                  : 'bg-[var(--color-surface)] text-[var(--color-text-2)] hover:text-[var(--color-text)]'
              }`}>
              {t === 'day' ? 'Día' : 'Mes'}
            </button>
          ))}
        </div>

        {tab === 'day' ? (
          <input type="date" aria-label="Fecha del reporte" value={date} min={`${minMonth}-01`} max={today}
            onChange={e => setDate(e.target.value)}
            className="focus-ring bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-brand-500" />
        ) : (
          <div className="flex gap-2">
            <select aria-label="Mes del reporte" value={monthNumSel} onChange={e => handleMonthNum(Number(e.target.value))}
              className="focus-ring bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-brand-500 cursor-pointer">
              {MONTHS_FOR_YEAR.map(({ name, num }) => (
                <option key={num} value={num}>{name}</option>
              ))}
            </select>
            <select aria-label="Año del reporte" value={yearSel} onChange={e => handleYear(Number(e.target.value))}
              className="focus-ring bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-brand-500 cursor-pointer">
              {YEARS.map(y => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
          </div>
        )}

        <Button onClick={generate} disabled={loading}>
          {loading ? 'Generando…' : 'Actualizar'}
        </Button>

        {/* Vista: por cliente / carrier / proveedor — quién generó el consumo.
            Agrupar por destino (país/grupo de prefijos/prefijo) vive en su
            propia página, Reportes → Por destino, que además tiene ASR/ACD/PDD
            y la herramienta de backfill — tenerlo acá también era redundante. */}
        <div className="ml-auto flex rounded-lg overflow-hidden border border-[var(--color-border)]">
          {([
            ['customer', 'Por cliente'],
            ['carrier',  'Por carrier'],
            ['provider', 'Por proveedor'],
          ] as const).map(([v, label]) => (
            <button key={v} onClick={() => { setView(v); setExpanded(null) }}
              className={`focus-ring px-4 py-1.5 text-sm transition-colors ${
                view === v
                  ? 'bg-brand-600/20 text-brand-400 border-b-2 border-brand-500'
                  : 'bg-[var(--color-surface)] text-[var(--color-text-2)] hover:text-[var(--color-text)]'
              }`}>
              {label}
            </button>
          ))}
        </div>
      </Card>

      {loading && (
        <Card className="p-14 text-center">
          <p className="text-[var(--color-muted)] text-sm">Generando reporte…</p>
        </Card>
      )}

      {!loading && rows !== null && rows.length === 0 && (
        <Card className="p-14 text-center">
          <p className="text-[var(--color-muted)] text-sm">Sin datos para el período seleccionado.</p>
        </Card>
      )}

      {/* Resultados */}
      {!loading && rows !== null && rows.length > 0 && view === 'customer' && byCustomer && (
        renderSummary(byCustomer, 'customer_name', 'carrier_name', 'cust', 'carrier')
      )}

      {!loading && rows !== null && rows.length > 0 && view === 'carrier' && byCarrier && (
        renderSummary(byCarrier, 'carrier_name', 'customer_name', 'carr', 'cliente')
      )}

      {!loading && rows !== null && rows.length > 0 && view === 'provider' && byProvider && (
        renderSummary(byProvider, 'provider_name', 'carrier_name', 'prov', 'carrier')
      )}
    </div>
  )
}
