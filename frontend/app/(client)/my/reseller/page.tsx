'use client'
import { useEffect, useState } from 'react'
import { apiGet } from '@/lib/api'

interface MarginRow {
  customer_id: number
  customer_name: string
  calls: number
  revenue: number
  cost: number
  margin: number
}
interface Dashboard {
  month: string
  by_customer: MarginRow[]
  total_margin: number
}

function money(n: number) { return `S/ ${Number(n).toFixed(4)}` }

export default function ResellerDashboard() {
  const [data, setData]       = useState<Dashboard | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState('')

  useEffect(() => {
    apiGet('/reseller/dashboard').then(setData).catch((e: any) => setError(e.message || 'Error cargando el resumen')).finally(() => setLoading(false))
  }, [])
  useEffect(() => { document.title = 'Reseller — Resumen · VoxiKam' }, [])

  if (loading) return <div className="p-8 text-center text-[var(--color-text-2)] text-sm">Cargando…</div>
  if (error) return <div className="p-8 text-center text-danger text-sm">{error}</div>

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-[var(--color-text)]">Reseller — Resumen</h1>
        <p className="text-sm text-[var(--color-text-2)] mt-0.5">Margen del mes {data?.month} por sub-cliente</p>
      </div>

      <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-5">
        <p className="text-xs text-[var(--color-text-2)] uppercase tracking-wider">Margen total del mes</p>
        <p className="text-3xl font-bold font-mono tabular-nums text-success mt-1">{money(data?.total_margin ?? 0)}</p>
      </div>

      <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl overflow-x-auto">
        <div className="px-6 py-3 border-b border-[var(--color-border)]">
          <h2 className="text-sm font-medium text-[var(--color-text)]">Por sub-cliente</h2>
        </div>
        {!data?.by_customer.length ? (
          <p className="p-8 text-center text-[var(--color-muted)] text-sm">Sin llamadas de sub-clientes este mes todavía.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-[var(--color-text-2)] uppercase border-b border-[var(--color-border)]">
                <th className="px-6 py-3 text-left">Sub-cliente</th>
                <th className="px-6 py-3 text-right">Llamadas</th>
                <th className="px-6 py-3 text-right">Facturado</th>
                <th className="px-6 py-3 text-right">Costo</th>
                <th className="px-6 py-3 text-right">Margen</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              {data.by_customer.map(r => (
                <tr key={r.customer_id} className="hover:bg-white/2">
                  <td className="px-6 py-3 text-[var(--color-text)]">{r.customer_name}</td>
                  <td className="px-6 py-3 text-right font-mono tabular-nums text-[var(--color-text)]">{r.calls}</td>
                  <td className="px-6 py-3 text-right font-mono tabular-nums text-[var(--color-text)]">{money(r.revenue)}</td>
                  <td className="px-6 py-3 text-right font-mono tabular-nums text-danger">{money(r.cost)}</td>
                  <td className="px-6 py-3 text-right font-mono tabular-nums text-success">{money(r.margin)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
