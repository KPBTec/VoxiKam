'use client'
import { useEffect, useState } from 'react'
import { apiGet } from '@/lib/api'
import { RefreshCw, AlertTriangle, Hash, Clock } from 'lucide-react'
import { ErrorBanner } from '@/components/ErrorBanner'
import { apiPost } from '@/lib/api'

interface ReportRow {
  area: string
  nbcall: number
  nbcall_fail: number
  sessiontime: number
  buycost: string
  sessionbill: string
  lucro: string
  asr: number | null
  acd: number | null
  pdd_ms: number | null
}

interface CustomerOpt { id: number; name: string }

const card = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'

const MONTH_NAMES = [
  'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
]

function todayISO() { return new Date().toISOString().slice(0, 10) }
function lastDayOfMonthISO(month: string) {
  // Date.UTC evita el bug de timezone: new Date(y, m, 0) usa hora LOCAL y al
  // convertir a ISO con toISOString() puede retroceder un día en timezones
  // adelantados a UTC (ej. Europa) — con Date.UTC el cálculo es directo en UTC.
  const [y, m] = month.split('-').map(Number)
  return new Date(Date.UTC(y, m, 0)).toISOString().slice(0, 10)
}

export default function AreasReportPage() {
  const [error, setError] = useState('')

  const today = todayISO()
  const thisMonth = today.slice(0, 7)
  const [reportTab, setReportTab] = useState<'day' | 'month'>('month')
  const [reportDate, setReportDate] = useState(today)
  const [reportMonthSel, setReportMonthSel] = useState(thisMonth)
  const [reportBy, setReportBy] = useState<'country' | 'area' | 'prefix'>('area')
  const [report, setReport] = useState<ReportRow[]>([])
  const [loadingReport, setLoadingReport] = useState(true)
  const [customers, setCustomers] = useState<CustomerOpt[]>([])
  const [customerId, setCustomerId] = useState('')
  const [range, setRange] = useState<{ min_month: string | null; current_month: string } | null>(null)

  const minMonth = range?.min_month ?? range?.current_month ?? thisMonth
  const maxMonth = range?.current_month ?? thisMonth
  const [yearSel, monthNumSel] = reportMonthSel.split('-').map(Number)
  const [minYear] = minMonth.split('-').map(Number)
  const [maxYear] = maxMonth.split('-').map(Number)
  const YEARS = Array.from({ length: maxYear - minYear + 1 }, (_, i) => maxYear - i)
  const MONTHS_FOR_YEAR = MONTH_NAMES
    .map((name, i) => ({ name, num: i + 1, key: `${yearSel}-${String(i + 1).padStart(2, '0')}` }))
    .filter(({ key }) => key >= minMonth && key <= maxMonth)

  function handleMonthNum(m: number) { setReportMonthSel(`${yearSel}-${String(m).padStart(2, '0')}`) }
  function handleYear(y: number) {
    const candidates = MONTH_NAMES
      .map((_, i) => `${y}-${String(i + 1).padStart(2, '0')}`)
      .filter(key => key >= minMonth && key <= maxMonth)
    const target = candidates.includes(`${y}-${String(monthNumSel).padStart(2, '0')}`)
      ? `${y}-${String(monthNumSel).padStart(2, '0')}`
      : candidates[candidates.length - 1]
    setReportMonthSel(target)
  }

  const [backfill, setBackfill] = useState<{ sin_match: number; total: number; computed_at: string | null; stale: boolean } | null>(null)
  const [backfillRunning, setBackfillRunning] = useState(false)
  const [backfillError, setBackfillError] = useState('')

  async function loadBackfillStatus() {
    try { setBackfill(await apiGet('/admin/areas/backfill-status')); setBackfillError('') }
    catch (err) { setBackfillError(err instanceof Error ? err.message : 'No se pudo consultar el estado') }
  }

  async function runBackfill() {
    if (!confirm('Esto recalcula el área de todo el histórico de CDRs contestados en background — puede tardar unos minutos según cuántas llamadas tengas. ¿Continuar?')) return
    setBackfillRunning(true); setError('')
    try { await apiPost('/admin/areas/backfill-prefix-matched', {}) }
    catch (err) { setError(err instanceof Error ? err.message : 'Error al recalcular') }
    finally { setBackfillRunning(false) }
  }

  async function loadReport() {
    setLoadingReport(true)
    try {
      const dateFrom = reportTab === 'day' ? reportDate : `${reportMonthSel}-01`
      const dateTo   = reportTab === 'day' ? reportDate : lastDayOfMonthISO(reportMonthSel)
      const p = new URLSearchParams({ date_from: dateFrom, date_to: dateTo, by: reportBy })
      if (customerId) p.set('customer_id', customerId)
      setReport(await apiGet(`/admin/areas/report?${p}`))
      setError('')
    } catch (err) { setError(err instanceof Error ? err.message : 'Error cargando reporte') }
    finally { setLoadingReport(false) }
  }

  useEffect(() => {
    loadBackfillStatus()
    apiGet('/admin/customers?exclude_resellers=true').then(setCustomers).catch(() => {})
    apiGet('/admin/reports/range').then(setRange).catch(() => setRange({ min_month: null, current_month: thisMonth }))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { loadReport() }, [reportTab, reportDate, reportMonthSel, reportBy, customerId]) // eslint-disable-line react-hooks/exhaustive-deps

  const fmt = (n: string | number) => `S/. ${parseFloat(String(n)).toFixed(2)}`

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Por destino</h1>
        <p className="text-sm text-[var(--color-text-2)] mt-1">
          Rentabilidad agrupada por país, área o prefijo de destino, según el área que cada CDR
          resolvió al momento de la llamada. Las áreas se crean y editan en{' '}
          <a href="/area-groups" className="underline">Tarifas → Áreas</a>.
        </p>
      </div>

      {error && <ErrorBanner>{error}</ErrorBanner>}

      {backfillError && (
        <ErrorBanner>
          <span className="flex items-start gap-2.5">
            <AlertTriangle size={16} className="flex-shrink-0 mt-0.5" />
            No se pudo consultar si hay CDRs sin área asignada ({backfillError}). El reporte de abajo puede estar incompleto.
          </span>
        </ErrorBanner>
      )}

      {backfill && backfill.stale && (
        <div className="bg-sky-950/20 border border-sky-800/40 rounded-xl p-4 flex items-start gap-2.5">
          <Clock size={16} className="text-sky-400 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-sky-200">
            Todavía no hay un cálculo reciente de CDRs sin área asignada (se genera cada hora) — puede
            ser que el sistema se instaló hace poco o que el cálculo aún no corrió.
            <strong className="block mt-1">Esto no confirma que todo esté bien, solo que todavía no lo sabemos.</strong>
            Recargá esta página en un rato para ver el primer resultado.
          </p>
        </div>
      )}

      {backfill && !backfill.stale && backfill.sin_match > 0 && (
        <div className="bg-yellow-950/30 border border-yellow-800/40 rounded-xl p-4 flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-start gap-2.5">
            <AlertTriangle size={16} className="text-yellow-400 flex-shrink-0 mt-0.5" />
            <p className="text-sm text-yellow-200">
              <strong>{backfill.sin_match.toLocaleString('es-PE')}</strong> de {backfill.total.toLocaleString('es-PE')} CDRs contestados no tienen área asignada todavía
              (llamadas de antes de que este cálculo existiera) — por eso el reporte de abajo las agrupa en "Sin área".
              Recalcular una sola vez las clasifica según las áreas configuradas hoy.
              <span className="block text-yellow-200/60 mt-1">Calculado {new Date(backfill.computed_at!).toLocaleString('es-PE')} · se actualiza cada hora</span>
            </p>
          </div>
          <button onClick={runBackfill} disabled={backfillRunning}
            className="flex items-center gap-1.5 px-3 py-2 bg-yellow-600 hover:bg-yellow-500 disabled:opacity-50 text-white text-xs font-medium rounded-lg flex-shrink-0">
            <RefreshCw size={13} className={backfillRunning ? 'animate-spin' : ''} />
            {backfillRunning ? 'Corriendo en background…' : 'Recalcular histórico'}
          </button>
        </div>
      )}

      <div className={`${card} p-5 flex items-center justify-between gap-4 flex-wrap`}>
        <div className="flex items-start gap-2.5">
          <Hash size={16} className="text-[var(--color-muted)] flex-shrink-0 mt-0.5" />
          <p className="text-sm text-[var(--color-text-2)]">
            Los prefijos (los códigos que arman este directorio de destinos) se crean y editan en{' '}
            <a href="/rates" className="underline text-[var(--color-text)]">Tarifas → Prefijos de destino</a>.
            Ahí también podés asignarle un área a cada uno.
          </p>
        </div>
        <a href="/rates" className="flex-shrink-0 px-3 py-2 bg-brand-600 hover:bg-brand-500 text-white text-xs font-medium rounded-lg">
          Ir a Prefijos
        </a>
      </div>

      <div className={`${card} overflow-x-auto`}>
        <div className="px-5 py-3 border-b border-[var(--color-border)] flex items-center justify-between flex-wrap gap-3">
          <h2 className="font-semibold text-sm">Por destino</h2>
          <div className="flex items-start gap-4 flex-wrap">
            <div className="flex flex-col gap-1">
              <span className="text-[10px] uppercase tracking-wider text-[var(--color-muted)]">Cliente</span>
              <select value={customerId} onChange={e => setCustomerId(e.target.value)}
                className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-2 py-1.5 text-xs cursor-pointer">
                <option value="">Todos los clientes</option>
                {customers.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>

            <div className="w-px self-stretch bg-[var(--color-border)] hidden sm:block" />

            <div className="flex flex-col gap-1">
              <span className="text-[10px] uppercase tracking-wider text-[var(--color-muted)]">Cuándo</span>
              <div className="flex items-center gap-2">
                <div className="flex rounded-lg overflow-hidden border border-[var(--color-border)]">
                  {(['day', 'month'] as const).map(t => (
                    <button key={t} onClick={() => setReportTab(t)}
                      className={`px-3 py-1.5 text-xs transition-colors ${
                        reportTab === t
                          ? 'bg-brand-600 text-white'
                          : 'bg-[var(--color-surface)] text-[var(--color-text-2)] hover:text-[var(--color-text)]'
                      }`}>
                      {t === 'day' ? 'Día' : 'Mes'}
                    </button>
                  ))}
                </div>

                {reportTab === 'day' ? (
                  <input type="date" value={reportDate} min={`${minMonth}-01`} max={today}
                    onChange={e => setReportDate(e.target.value)}
                    className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-2 py-1.5 text-xs" />
                ) : (
                  <div className="flex gap-2">
                    <select value={monthNumSel} onChange={e => handleMonthNum(Number(e.target.value))}
                      className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-2 py-1.5 text-xs cursor-pointer">
                      {MONTHS_FOR_YEAR.map(({ name, num }) => <option key={num} value={num}>{name}</option>)}
                    </select>
                    <select value={yearSel} onChange={e => handleYear(Number(e.target.value))}
                      className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-2 py-1.5 text-xs cursor-pointer">
                      {YEARS.map(y => <option key={y} value={y}>{y}</option>)}
                    </select>
                  </div>
                )}
              </div>
            </div>

            <div className="w-px self-stretch bg-[var(--color-border)] hidden sm:block" />

            <div className="flex flex-col gap-1">
              <span className="text-[10px] uppercase tracking-wider text-[var(--color-muted)]">Agrupar por</span>
              <div className="flex rounded-lg overflow-hidden border border-[var(--color-border)]">
                {([['country', 'Por país'], ['area', 'Por área'], ['prefix', 'Por prefijo']] as const).map(([v, label]) => (
                  <button key={v} onClick={() => setReportBy(v)}
                    className={`px-3 py-1.5 text-xs transition-colors ${
                      reportBy === v
                        ? 'bg-brand-600/20 text-brand-400 border-b-2 border-brand-500'
                        : 'bg-[var(--color-surface)] text-[var(--color-text-2)] hover:text-[var(--color-text)]'
                    }`}>
                    {label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
        {loadingReport ? (
          <div className="text-[var(--color-muted)] p-8 text-center text-sm">Cargando...</div>
        ) : report.length === 0 ? (
          <div className="text-[var(--color-muted)] p-8 text-center text-sm">Sin llamadas contestadas en el rango</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[var(--color-text-2)] text-xs uppercase border-b border-[var(--color-border)]">
                <th className="px-5 py-3 text-left">{reportBy === 'country' ? 'País' : reportBy === 'area' ? 'Área' : 'Prefijo'}</th>
                <th className="px-5 py-3 text-right">Llamadas</th>
                <th className="px-5 py-3 text-right">Minutos</th>
                <th className="px-5 py-3 text-right">Compra</th>
                <th className="px-5 py-3 text-right">Venta</th>
                <th className="px-5 py-3 text-right">Margen</th>
                <th className="px-5 py-3 text-right">ASR</th>
                <th className="px-5 py-3 text-right">ACD</th>
                <th className="px-5 py-3 text-right">PDD</th>
              </tr>
            </thead>
            <tbody>
              {report.map(row => (
                <tr key={row.area} className="border-b border-[var(--color-border)]/50">
                  <td className="px-5 py-2.5">{(row.area === 'Sin área' || row.area === 'Sin prefijo' || row.area === 'Sin país') ? <span className="text-[var(--color-muted)]">{row.area}</span> : row.area}</td>
                  <td className="px-5 py-2.5 text-right">{row.nbcall.toLocaleString('es-PE')}</td>
                  <td className="px-5 py-2.5 text-right">{(row.sessiontime / 60).toFixed(1)}</td>
                  <td className="px-5 py-2.5 text-right font-mono">{fmt(row.buycost)}</td>
                  <td className="px-5 py-2.5 text-right font-mono">{fmt(row.sessionbill)}</td>
                  <td className={`px-5 py-2.5 text-right font-mono ${parseFloat(row.lucro) >= 0 ? 'text-green-400' : 'text-red-400'}`}>{fmt(row.lucro)}</td>
                  <td className="px-5 py-2.5 text-right text-[var(--color-text-2)]">{row.asr != null ? `${row.asr}%` : '—'}</td>
                  <td className="px-5 py-2.5 text-right text-[var(--color-text-2)]">{row.acd != null ? `${row.acd.toFixed(0)}s` : '—'}</td>
                  <td className="px-5 py-2.5 text-right text-[var(--color-text-2)]">{row.pdd_ms != null ? `${row.pdd_ms.toFixed(0)}ms` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
