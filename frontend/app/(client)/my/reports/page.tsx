'use client'
import { useEffect, useState } from 'react'
import { apiGet } from '@/lib/api'

function currentMonth() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}
const MONTH_NAMES = [
  'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
]
function fmt(n: any, dec = 2) { return parseFloat(n || 0).toLocaleString('es-PE', { minimumFractionDigits: dec, maximumFractionDigits: dec }) }
function money(n: any) { return `S/ ${fmt(n, 4)}` }

interface Monthly {
  mes: string; llamadas: number; segundos: number
  minutos: number; costo: number; asr: number
}
interface DayRow {
  fecha: string; llamadas: number; segundos: number
  minutos: number; costo: number; asr: number
}
interface Report { month: string; monthly: Monthly; daily: DayRow[] }
interface CampaignRow { techprefix: string | null; label: string; llamadas: number; minutos: number; costo: number }
interface AreaRow {
  area: string; nbcall: number; sessiontime: number
  sessionbill: string; asr: number | null; acd: number | null; pdd_ms: number | null
}

export default function MyReportsPage() {
  const [month, setMonth]   = useState(currentMonth())
  const [data, setData]     = useState<Report | null>(null)
  const [campaigns, setCampaigns] = useState<CampaignRow[] | null>(null)
  const [areas, setAreas]   = useState<AreaRow[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]   = useState('')
  // null mientras carga — hasta entonces el selector no debe ofrecer años/meses
  // sin datos reales (ver /my/report/range, evita mostrar ej. 2024 en un
  // cliente dado de alta en 2026).
  const [range, setRange]   = useState<{ min_month: string | null; current_month: string } | null>(null)

  useEffect(() => {
    apiGet('/my/report/range').then(setRange).catch(() => setRange({ min_month: null, current_month: currentMonth() }))
  }, [])

  async function load(m: string) {
    setLoading(true); setError('')
    try {
      const d = await apiGet(`/my/report?month=${m}`)
      setData(d)
    } catch (e: any) {
      setError(e.message || 'Error al cargar reporte')
    } finally { setLoading(false) }

    // Aparte del try/catch principal — si esto falla no debe tapar el
    // reporte mensual, que es el dato central de esta página.
    try {
      const [y, mn] = m.split('-').map(Number)
      const lastDay = new Date(y, mn, 0).getDate()
      const c = await apiGet(`/my/campaigns?date_from=${m}-01&date_to=${m}-${String(lastDay).padStart(2, '0')}`)
      setCampaigns(c.rows || [])
    } catch {
      setCampaigns(null)
    }

    try {
      const a = await apiGet(`/my/report/by-area?month=${m}`)
      setAreas(a.areas || [])
    } catch {
      setAreas(null)
    }
  }

  useEffect(() => { load(month) }, [])

  function handleMonth(val: string) {
    setMonth(val)
    load(val)
  }

  const [year, monthNum] = month.split('-').map(Number)

  // Acota el selector a lo que realmente hay en cdr_summary_month — sin range
  // todavía cargado, solo se ofrece el mes actual (nunca "todos los años").
  const minMonth = range?.min_month ?? range?.current_month ?? currentMonth()
  const maxMonth = range?.current_month ?? currentMonth()
  const [minYear] = minMonth.split('-').map(Number)
  const [maxYear] = maxMonth.split('-').map(Number)
  const YEARS = Array.from({ length: maxYear - minYear + 1 }, (_, i) => maxYear - i)
  const MONTHS_FOR_YEAR = MONTH_NAMES
    .map((name, i) => ({ name, num: i + 1, key: `${year}-${String(i + 1).padStart(2, '0')}` }))
    .filter(({ key }) => key >= minMonth && key <= maxMonth)

  function handleMonthNum(m: number) {
    handleMonth(`${year}-${String(m).padStart(2, '0')}`)
  }
  function handleYear(y: number) {
    // Si el año elegido no tiene el mes actualmente seleccionado disponible
    // (ej. pasar de 2026 a 2024 estando en diciembre), cae al último mes
    // válido de ese año en vez de pedir un mes sin datos.
    const candidates = MONTH_NAMES
      .map((_, i) => `${y}-${String(i + 1).padStart(2, '0')}`)
      .filter(key => key >= minMonth && key <= maxMonth)
    const target = candidates.includes(`${y}-${String(monthNum).padStart(2, '0')}`)
      ? `${y}-${String(monthNum).padStart(2, '0')}`
      : candidates[candidates.length - 1]
    handleMonth(target)
  }

  const selectCls = 'bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg ' +
                     'px-3 py-1.5 text-sm focus:outline-none focus:border-brand-500 cursor-pointer'

  const card = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'
  const th   = 'px-4 py-2.5 text-xs text-[var(--color-text-2)] uppercase tracking-wider font-medium'
  const td   = 'px-4 py-3 text-sm font-mono'

  const mon = data?.monthly

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Reportes</h1>
        <div className="flex gap-2">
          <select value={monthNum} onChange={e => handleMonthNum(Number(e.target.value))} className={selectCls}>
            {MONTHS_FOR_YEAR.map(({ name, num }) => (
              <option key={num} value={num}>{name}</option>
            ))}
          </select>
          <select value={year} onChange={e => handleYear(Number(e.target.value))} className={selectCls}>
            {YEARS.map(y => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>
      </div>

      {loading && (
        <div className={`${card} p-10 text-center text-[var(--color-muted)] text-sm`}>Cargando…</div>
      )}

      {error && !loading && (
        <div className={`${card} p-6 text-center text-red-400 text-sm`}>{error}</div>
      )}

      {!loading && data && (
        <>
          {/* Resumen mensual */}
          <div>
            <h2 className="text-sm font-medium text-[var(--color-text-2)] mb-3 uppercase tracking-wider">
              Resumen mensual — {data.month}
            </h2>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { label: 'Llamadas',  value: fmt(mon?.llamadas, 0), color: 'text-white' },
                { label: 'Segundos',  value: fmt(mon?.segundos, 0), color: 'text-[var(--color-text-2)]' },
                { label: 'Minutos',   value: fmt(mon?.minutos,  2), color: 'text-[var(--color-text-2)]' },
                { label: 'Costo',     value: money(mon?.costo),     color: 'text-brand-400' },
              ].map(({ label, value, color }) => (
                <div key={label} className={`${card} p-4`}>
                  <p className="text-xs text-[var(--color-muted)] mb-1">{label}</p>
                  <p className={`text-xl font-semibold font-mono ${color}`}>{value}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Desglose diario */}
          <div>
            <h2 className="text-sm font-medium text-[var(--color-text-2)] mb-3 uppercase tracking-wider">
              Desglose diario
            </h2>
            {data.daily.length === 0 ? (
              <div className={`${card} p-10 text-center text-[var(--color-muted)] text-sm`}>
                Sin datos para {data.month}
              </div>
            ) : (
              <div className={`${card} overflow-x-auto`}>
                <table className="w-full">
                  <thead>
                    <tr className="text-left border-b border-[var(--color-border)] bg-[var(--color-surface)]">
                      <th className={`${th} text-left`}>Fecha</th>
                      <th className={`${th} text-right`}>Llamadas</th>
                      <th className={`${th} text-right`}>Segundos</th>
                      <th className={`${th} text-right`}>Minutos</th>
                      <th className={`${th} text-right`}>Costo</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--color-border)]/40">
                    {data.daily.map(r => (
                      <tr key={r.fecha} className="hover:bg-white/3 transition-colors">
                        <td className={`${td} text-[var(--color-text)]`}>{r.fecha}</td>
                        <td className={`${td} text-right text-white`}>{fmt(r.llamadas, 0)}</td>
                        <td className={`${td} text-right text-[var(--color-text-2)]`}>{fmt(r.segundos, 0)}</td>
                        <td className={`${td} text-right text-[var(--color-text-2)]`}>{fmt(r.minutos, 2)}</td>
                        <td className={`${td} text-right text-brand-400`}>{money(r.costo)}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="border-t-2 border-[var(--color-border)] bg-[var(--color-surface)]">
                      <td className="px-4 py-2.5 text-sm font-semibold">Total</td>
                      <td className={`${td} text-right font-semibold text-white`}>{fmt(mon?.llamadas, 0)}</td>
                      <td className={`${td} text-right font-semibold`}>{fmt(mon?.segundos, 0)}</td>
                      <td className={`${td} text-right font-semibold`}>{fmt(mon?.minutos, 2)}</td>
                      <td className={`${td} text-right font-semibold text-brand-400`}>{money(mon?.costo)}</td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}
          </div>

          {/* Por campaña — solo si el cliente tiene más de un prefijo en uso */}
          {campaigns && campaigns.length > 1 && (
            <div>
              <h2 className="text-sm font-medium text-[var(--color-text-2)] mb-3 uppercase tracking-wider">
                Por campaña
              </h2>
              <div className={`${card} overflow-x-auto`}>
                <table className="w-full">
                  <thead>
                    <tr className="text-left border-b border-[var(--color-border)] bg-[var(--color-surface)]">
                      <th className={`${th} text-left`}>Campaña</th>
                      <th className={`${th} text-right`}>Llamadas</th>
                      <th className={`${th} text-right`}>Minutos</th>
                      <th className={`${th} text-right`}>Costo</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--color-border)]/40">
                    {campaigns.map(c => (
                      <tr key={c.techprefix ?? 'sin-campana'} className="hover:bg-white/3 transition-colors">
                        <td className={`${td} text-[var(--color-text)]`}>{c.label}</td>
                        <td className={`${td} text-right text-white`}>{fmt(c.llamadas, 0)}</td>
                        <td className={`${td} text-right text-[var(--color-text-2)]`}>{fmt(c.minutos, 2)}</td>
                        <td className={`${td} text-right text-brand-400`}>{money(c.costo)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Por destino/área — a qué está llamando y cuánto le cuesta cada destino */}
          {areas && areas.length > 0 && (
            <div>
              <h2 className="text-sm font-medium text-[var(--color-text-2)] mb-3 uppercase tracking-wider">
                Por destino
              </h2>
              <div className={`${card} overflow-x-auto`}>
                <table className="w-full">
                  <thead>
                    <tr className="text-left border-b border-[var(--color-border)] bg-[var(--color-surface)]">
                      <th className={`${th} text-left`}>Destino</th>
                      <th className={`${th} text-right`}>Llamadas</th>
                      <th className={`${th} text-right`}>Minutos</th>
                      <th className={`${th} text-right`}>Costo</th>
                      <th className={`${th} text-right`}>ASR</th>
                      <th className={`${th} text-right`}>ACD</th>
                      <th className={`${th} text-right`}>PDD</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--color-border)]/40">
                    {areas.map(a => (
                      <tr key={a.area} className="hover:bg-white/3 transition-colors">
                        <td className={`${td} text-[var(--color-text)]`}>{a.area}</td>
                        <td className={`${td} text-right text-white`}>{fmt(a.nbcall, 0)}</td>
                        <td className={`${td} text-right text-[var(--color-text-2)]`}>{fmt(a.sessiontime / 60, 2)}</td>
                        <td className={`${td} text-right text-brand-400`}>{money(a.sessionbill)}</td>
                        <td className={`${td} text-right text-[var(--color-text-2)]`}>{a.asr != null ? `${a.asr}%` : '—'}</td>
                        <td className={`${td} text-right text-[var(--color-text-2)]`}>{a.acd != null ? `${a.acd.toFixed(0)}s` : '—'}</td>
                        <td className={`${td} text-right text-[var(--color-text-2)]`}>{a.pdd_ms != null ? `${a.pdd_ms.toFixed(0)}ms` : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
