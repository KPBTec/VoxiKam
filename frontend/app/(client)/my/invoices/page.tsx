'use client'
import { ErrorBanner } from '@/components/ErrorBanner'
import { StatusBadge, invoiceStatusVariant } from '@/components/StatusBadge'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { apiGet } from '@/lib/api'
import { getUser } from '@/lib/auth'

interface Invoice {
  id: number; period_start: string; period_end: string
  nbcall: number; total_minutes: number
  subtotal: number; tax_amount: number; total: number
  currency: string; status: string; created_at: string
}

export default function MyInvoices() {
  const router = useRouter()
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState('')

  useEffect(() => {
    const user = getUser()
    if (user?.role === 'client' && user?.permissions?.invoices === false) {
      router.replace('/my/overview')
      return
    }
    apiGet('/my/invoices').then(setInvoices).catch((e: any) => setError(e.message || 'Error cargando facturas')).finally(() => setLoading(false))
  }, [])

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-[var(--color-text)]">Mis facturas</h1>

      {error && <ErrorBanner>{error}</ErrorBanner>}

      <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl overflow-x-auto">
        {loading ? (
          <p className="p-8 text-center text-[var(--color-text-2)] text-sm">Cargando…</p>
        ) : invoices.length === 0 ? (
          <p className="p-10 text-center text-[var(--color-muted)] text-sm">Sin facturas por ahora</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-[var(--color-text-2)] uppercase border-b border-[var(--color-border)]">
                <th className="px-6 py-3 text-left">#</th>
                <th className="px-6 py-3 text-left">Período</th>
                <th className="px-6 py-3 text-right">Llamadas</th>
                <th className="px-6 py-3 text-right">Minutos</th>
                <th className="px-6 py-3 text-right">Subtotal</th>
                <th className="px-6 py-3 text-right">Total</th>
                <th className="px-6 py-3 text-left">Estado</th>
                <th className="px-6 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              {invoices.map(inv => (
                <tr key={inv.id} className="hover:bg-white/2">
                  <td className="px-6 py-3 text-[var(--color-text-2)] font-mono">#{inv.id}</td>
                  <td className="px-6 py-3 text-[var(--color-text-2)] text-xs font-mono">
                    {inv.period_start} → {inv.period_end}
                  </td>
                  <td className="px-6 py-3 text-right font-mono">{inv.nbcall}</td>
                  <td className="px-6 py-3 text-right font-mono text-[var(--color-text-2)]">
                    {parseFloat(String(inv.total_minutes)).toFixed(0)} min
                  </td>
                  <td className="px-6 py-3 text-right font-mono text-[var(--color-text-2)]">
                    S/ {(+inv.subtotal).toFixed(2)}
                  </td>
                  <td className="px-6 py-3 text-right font-mono text-[var(--color-text)] font-semibold">
                    S/ {(+inv.total).toFixed(2)}
                  </td>
                  <td className="px-6 py-3">
                    <StatusBadge variant={invoiceStatusVariant(inv.status)}>{inv.status}</StatusBadge>
                  </td>
                  <td className="px-6 py-3 text-right">
                    <button onClick={() => window.open(`/api/admin/invoices/${inv.id}/pdf`, '_blank')}
                      className="text-xs text-brand-400 hover:text-brand-300 focus-ring">
                      Descargar PDF
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
