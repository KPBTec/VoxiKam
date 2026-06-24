'use client'
import { useEffect, useState } from 'react'
import { apiGet } from '@/lib/api'

function currentMonth() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}
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

export default function MyReportsPage() {
  const [month, setMonth]   = useState(currentMonth())
  const [data, setData]     = useState<Report | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]   = useState('')

  async function load(m: string) {
    setLoading(true); setError('')
    try {
      const d = await apiGet(`/my/report?month=${m}`)
      setData(d)
    } catch (e: any) {
      setError(e.message || 'Error al cargar reporte')
    } finally { setLoading(false) }
  }

  useEffect(() => { load(month) }, [])

  function handleMonth(val: string) {
    setMonth(val)
    load(val)
  }

  const card = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'
  const th   = 'px-4 py-2.5 text-xs text-[var(--color-text-2)] uppercase tracking-wider font-medium'
  const td   = 'px-4 py-3 text-sm font-mono'

  const mon = data?.monthly

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Reportes</h1>
        <input
          type="month"
          value={month}
          onChange={e => handleMonth(e.target.value)}
          className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg
                     px-3 py-1.5 text-sm focus:outline-none focus:border-brand-500"
        />
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
                { label: 'Costo',     value: money(mon?.costo),     color: 'text-blue-400' },
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
              <div className={`${card} overflow-hidden`}>
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
                        <td className={`${td} text-right text-blue-400`}>{money(r.costo)}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="border-t-2 border-[var(--color-border)] bg-[var(--color-surface)]">
                      <td className="px-4 py-2.5 text-sm font-semibold">Total</td>
                      <td className={`${td} text-right font-semibold text-white`}>{fmt(mon?.llamadas, 0)}</td>
                      <td className={`${td} text-right font-semibold`}>{fmt(mon?.segundos, 0)}</td>
                      <td className={`${td} text-right font-semibold`}>{fmt(mon?.minutos, 2)}</td>
                      <td className={`${td} text-right font-semibold text-blue-400`}>{money(mon?.costo)}</td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
