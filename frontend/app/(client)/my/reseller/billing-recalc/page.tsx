'use client'
import { useEffect, useState } from 'react'
import { apiGet, apiPost } from '@/lib/api'
import { RefreshCcw, AlertTriangle, CheckCircle2 } from 'lucide-react'
import { ErrorBanner } from '@/components/ErrorBanner'

interface Option { id: number; name: string }

interface CustomerDelta {
  customer_id: number; customer_name: string; n_cdrs: number
  old_sessionbill: number; new_sessionbill: number; delta_sessionbill: number
  old_buycost: number; new_buycost: number; delta_buycost: number
}

interface BlockedInvoice {
  id: number; customer_id: number; customer_name: string
  period_start: string; period_end: string; status: string
}

interface RecalcResult {
  total_scanned: number; affected_cdrs: number
  customers: CustomerDelta[]; blocked_invoices: BlockedInvoice[]
  can_apply?: boolean; applied?: boolean; message?: string
}

const card = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'
const input = 'bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus-ring'
const lbl = 'text-[10px] uppercase tracking-wider text-[var(--color-muted)]'

function todayISO() { return new Date().toISOString().slice(0, 10) }
function lastDayOfMonthISO(month: string) {
  // Date.UTC evita el bug de timezone: new Date(y, m, 0) usa hora LOCAL y al
  // convertir a ISO con toISOString() puede retroceder un día en timezones
  // adelantados a UTC (ej. Europa) — con Date.UTC el cálculo es directo en UTC.
  const [y, m] = month.split('-').map(Number)
  return new Date(Date.UTC(y, m, 0)).toISOString().slice(0, 10)
}
function fmt(n: number) { return `S/ ${n.toFixed(2)}` }

export default function ResellerBillingRecalcPage() {
  const API = '/reseller/billing-recalc'

  const [scope, setScope] = useState<'customer' | 'carrier'>('customer')
  const [customers, setCustomers] = useState<Option[]>([])
  const [carriers, setCarriers] = useState<Option[]>([])
  const [targetId, setTargetId] = useState('')

  const today = todayISO()
  const thisMonth = today.slice(0, 7)
  const [periodTab, setPeriodTab] = useState<'month' | 'range'>('month')
  const [monthSel, setMonthSel] = useState(thisMonth)
  const [dateFrom, setDateFrom] = useState(`${thisMonth}-01`)
  const [dateTo, setDateTo] = useState(today)

  const [preview, setPreview] = useState<RecalcResult | null>(null)
  const [applied, setApplied] = useState<RecalcResult | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [applying, setApplying] = useState(false)
  const [progress, setProgress] = useState<{ scanned?: number; total?: number; applying?: number; total_to_apply?: number } | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    apiGet(`${API}/customers`).then(setCustomers).catch((e: any) => setError(e.message))
    apiGet(`${API}/carriers`).then(setCarriers).catch((e: any) => setError(e.message))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { document.title = 'Recalcular tarifas · VoxiKam' }, [])

  function resetTarget(next: 'customer' | 'carrier') {
    setScope(next); setTargetId(''); setPreview(null); setApplied(null); setError('')
  }

  function body() {
    const date_from = periodTab === 'month' ? `${monthSel}-01` : dateFrom
    const lastDay = periodTab === 'month' ? lastDayOfMonthISO(monthSel) : dateTo
    const date_to = new Date(new Date(lastDay).getTime() + 86400000).toISOString().slice(0, 10)
    return { scope, target_id: Number(targetId), date_from, date_to }
  }

  // El scan corre en background (puede tardar minutos con millones de CDRs,
  // ya no cabe en la ventana de un solo request HTTP) — se arranca un job y
  // se sondea su estado cada 1.5s hasta que termina.
  async function pollJob(jobId: string, onDone: (result: any) => void, onError: (msg: string) => void) {
    let notFoundStreak = 0
    for (;;) {
      await new Promise(r => setTimeout(r, 1500))
      let job: any
      try {
        job = await apiGet(`${API}/jobs/${jobId}`)
        notFoundStreak = 0
      } catch (e: any) {
        // Mismo fix que admin/billing-recalc — un 404 aislado es el job
        // arrancando, no un error real; recién a los ~15s seguidos se
        // considera error de verdad.
        notFoundStreak++
        if (notFoundStreak >= 10) { onError(e.message || 'Error consultando el estado del job'); return }
        continue
      }
      if (job.status === 'running') { setProgress(job.progress || null); continue }
      if (job.status === 'error') { onError(job.error || 'Error en el recálculo'); return }
      onDone(job.result)
      return
    }
  }

  async function runPreview() {
    if (!targetId) return
    setPreviewing(true); setError(''); setPreview(null); setApplied(null); setProgress(null)
    try {
      const { job_id } = await apiPost(`${API}/preview`, body())
      await pollJob(job_id, (result) => setPreview(result), (msg) => setError(msg))
    } catch (e: any) { setError(e.message || 'Error generando la vista previa') }
    finally { setPreviewing(false); setProgress(null) }
  }

  async function runApply() {
    if (!preview?.can_apply) return
    if (!confirm(`Esto va a modificar ${preview.affected_cdrs} CDR(s) y ajustar el balance de ${preview.customers.length} sub-cliente(s) — ¿confirmás?`)) return
    setApplying(true); setError(''); setProgress(null)
    try {
      const { job_id } = await apiPost(`${API}/apply`, body())
      await pollJob(job_id, (result) => { setApplied(result); setPreview(null) }, (msg) => setError(msg))
    } catch (e: any) { setError(e.message || 'Error aplicando el recálculo') }
    finally { setApplying(false); setProgress(null) }
  }

  const targets = scope === 'customer' ? customers : carriers

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><RefreshCcw size={22} className="text-brand-500" /> Recalcular tarifas</h1>
        <p className="text-sm text-[var(--color-text-2)] mt-1">
          Recalcula el costo/venta de CDRs ya facturados contra tus tarifas <strong>actuales</strong> — para cuando
          negociás un precio nuevo con un sub-cliente (o cambia la tarifa de uno de tus carriers) y debe aplicar
          retroactivamente a llamadas ya hechas en el período. Solo ve tus propios sub-clientes y carriers.
        </p>
      </div>

      {error && <ErrorBanner>{error}</ErrorBanner>}

      <div className={`${card} p-5 space-y-4`}>
        <div className="flex items-start gap-4 flex-wrap">
          <div className="flex flex-col gap-1">
            <span className={lbl}>Alcance</span>
            <div className="flex rounded-lg overflow-hidden border border-[var(--color-border)]">
              {(['customer', 'carrier'] as const).map(s => (
                <button key={s} onClick={() => resetTarget(s)}
                  className={`focus-ring px-3 py-1.5 text-xs transition-colors ${
                    scope === s ? 'bg-brand-600 text-white' : 'bg-[var(--color-surface)] text-[var(--color-text-2)] hover:text-[var(--color-text)]'
                  }`}>
                  {s === 'customer' ? 'Sub-cliente' : 'Carrier'}
                </button>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-1 min-w-56">
            <label htmlFor="recalc-target" className={lbl}>{scope === 'customer' ? 'Sub-cliente' : 'Carrier'}</label>
            <select id="recalc-target" value={targetId} onChange={e => { setTargetId(e.target.value); setPreview(null); setApplied(null) }}
              className={`w-full ${input} cursor-pointer`}>
              <option value="">Seleccionar…</option>
              {targets.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </div>

          <div className="w-px self-stretch bg-[var(--color-border)] hidden sm:block" />

          <div className="flex flex-col gap-1">
            <span className={lbl}>Período</span>
            <div className="flex items-center gap-2">
              <div className="flex rounded-lg overflow-hidden border border-[var(--color-border)]">
                {(['month', 'range'] as const).map(t => (
                  <button key={t} onClick={() => { setPeriodTab(t); setPreview(null); setApplied(null) }}
                    className={`focus-ring px-3 py-1.5 text-xs transition-colors ${
                      periodTab === t ? 'bg-brand-600 text-white' : 'bg-[var(--color-surface)] text-[var(--color-text-2)] hover:text-[var(--color-text)]'
                    }`}>
                    {t === 'month' ? 'Mes' : 'Rango de fechas'}
                  </button>
                ))}
              </div>
              {periodTab === 'month' ? (
                <input type="month" aria-label="Mes" value={monthSel} max={thisMonth}
                  onChange={e => { setMonthSel(e.target.value); setPreview(null); setApplied(null) }}
                  className={input} />
              ) : (
                <div className="flex items-center gap-2">
                  <input type="date" aria-label="Desde" value={dateFrom} max={today}
                    onChange={e => { setDateFrom(e.target.value); setPreview(null); setApplied(null) }}
                    className={input} />
                  <span className="text-xs text-[var(--color-muted)]">→</span>
                  <input type="date" aria-label="Hasta" value={dateTo} max={today}
                    onChange={e => { setDateTo(e.target.value); setPreview(null); setApplied(null) }}
                    className={input} />
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button onClick={runPreview} disabled={!targetId || previewing}
            className="focus-ring flex items-center gap-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm px-4 py-2 rounded-lg transition-colors">
            <RefreshCcw size={14} className={previewing ? 'animate-spin' : ''} />
            {previewing ? 'Calculando…' : 'Vista previa'}
          </button>
          {previewing && progress?.total != null && (
            <span className="text-xs text-[var(--color-text-2)] font-mono">
              {progress.scanned?.toLocaleString('es-PE')} / {progress.total.toLocaleString('es-PE')} CDRs
            </span>
          )}
        </div>
      </div>

      {applied && (
        <div className="bg-success/10 border border-success/30 rounded-xl p-5 flex items-start gap-3">
          <CheckCircle2 size={18} className="text-success flex-shrink-0 mt-0.5" />
          <div className="text-sm text-[var(--color-text)]">
            <p className="font-medium">Recálculo aplicado — {applied.affected_cdrs} CDR(s) en {applied.customers.length} sub-cliente(s).</p>
            <p className="text-[var(--color-text-2)] mt-1">El balance ya quedó ajustado y los reportes del período refrescados.</p>
          </div>
        </div>
      )}

      {preview && preview.blocked_invoices.length > 0 && (
        <div className="bg-danger/10 border border-danger/30 rounded-xl p-5">
          <div className="flex items-start gap-2.5">
            <AlertTriangle size={16} className="text-danger flex-shrink-0 mt-0.5" />
            <div className="text-sm text-danger">
              <p className="font-medium">El rango pisa facturas ya emitidas/pagadas — no se puede aplicar hasta resolverlas.</p>
              <ul className="mt-2 space-y-1 text-[var(--color-text-2)]">
                {preview.blocked_invoices.map(b => (
                  <li key={b.id}>
                    Factura #{b.id} — {b.customer_name} ({b.period_start} a {b.period_end}, <span className="uppercase">{b.status}</span>)
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      {preview && (
        <div className={`${card} overflow-x-auto`}>
          <div className="px-5 py-3 border-b border-[var(--color-border)] flex items-center justify-between flex-wrap gap-3">
            <div>
              <h2 className="font-semibold text-sm">Vista previa</h2>
              <p className="text-xs text-[var(--color-muted)] mt-0.5">
                {preview.total_scanned.toLocaleString('es-PE')} CDR(s) evaluados — {preview.affected_cdrs.toLocaleString('es-PE')} con diferencia real
              </p>
            </div>
            {preview.customers.length > 0 && (
              <div className="flex items-center gap-3">
                <button onClick={runApply} disabled={!preview.can_apply || applying}
                  className="focus-ring flex items-center gap-2 bg-danger/90 hover:bg-danger disabled:opacity-50 text-white text-sm px-4 py-2 rounded-lg transition-colors">
                  {applying ? 'Aplicando…' : 'Aplicar recálculo'}
                </button>
                {applying && (
                  <span className="text-xs text-[var(--color-text-2)] font-mono">
                    {progress?.total_to_apply != null
                      ? `${progress.applying?.toLocaleString('es-PE')} / ${progress.total_to_apply.toLocaleString('es-PE')} aplicados`
                      : progress?.total != null
                        ? `${progress.scanned?.toLocaleString('es-PE')} / ${progress.total.toLocaleString('es-PE')} CDRs`
                        : 'Escaneando…'}
                  </span>
                )}
              </div>
            )}
          </div>
          {preview.customers.length === 0 ? (
            <p className="px-5 py-8 text-center text-[var(--color-muted)] text-sm">Sin diferencias — las tarifas actuales coinciden con lo ya facturado en ese rango.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[var(--color-text-2)] text-xs uppercase border-b border-[var(--color-border)]">
                  <th className="px-5 py-3 text-left">Sub-cliente</th>
                  <th className="px-5 py-3 text-right">CDRs</th>
                  <th className="px-5 py-3 text-right">Venta antes</th>
                  <th className="px-5 py-3 text-right">Venta ahora</th>
                  <th className="px-5 py-3 text-right">Delta venta</th>
                  <th className="px-5 py-3 text-right">Delta compra</th>
                </tr>
              </thead>
              <tbody>
                {preview.customers.map(c => (
                  <tr key={c.customer_id} className="border-b border-[var(--color-border)]/50">
                    <td className="px-5 py-2.5 font-medium">{c.customer_name}</td>
                    <td className="px-5 py-2.5 text-right font-mono tabular-nums">{c.n_cdrs}</td>
                    <td className="px-5 py-2.5 text-right font-mono tabular-nums text-[var(--color-text-2)]">{fmt(c.old_sessionbill)}</td>
                    <td className="px-5 py-2.5 text-right font-mono tabular-nums text-[var(--color-text-2)]">{fmt(c.new_sessionbill)}</td>
                    <td className={`px-5 py-2.5 text-right font-mono tabular-nums ${c.delta_sessionbill >= 0 ? 'text-success' : 'text-danger'}`}>
                      {c.delta_sessionbill >= 0 ? '+' : ''}{fmt(c.delta_sessionbill)}
                    </td>
                    <td className={`px-5 py-2.5 text-right font-mono tabular-nums ${c.delta_buycost <= 0 ? 'text-success' : 'text-danger'}`}>
                      {c.delta_buycost >= 0 ? '+' : ''}{fmt(c.delta_buycost)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}
