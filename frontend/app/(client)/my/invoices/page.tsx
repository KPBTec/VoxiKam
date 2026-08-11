'use client'
import { ErrorBanner } from '@/components/ErrorBanner'
import { StatusBadge, invoiceStatusVariant } from '@/components/StatusBadge'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { apiGet, apiFetch } from '@/lib/api'
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

  // Antes: window.open(`/api/admin/invoices/${id}/pdf`) — dos problemas reales
  // (auditoría UX): el endpoint era admin-only (un cliente nunca podía bajar su
  // propia factura), y aunque el endpoint hubiese sido el correcto, window.open
  // no manda el header Authorization — esta app autentica con Bearer token en
  // localStorage, no con cookies, así que la descarga habría fallado con 401
  // igual. Mismo patrón que ya usa el panel admin: apiFetch (manda el token) +
  // blob + <a download>, no window.open.
  async function downloadPdf(id: number) {
    try {
      const res = await apiFetch(`/my/invoices/${id}/pdf`)
      if (!res.ok) { setError('PDF no disponible o aún no generado'); return }
      const blob = await res.blob()
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href     = url
      a.download = `factura-${id}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      setError('Error al descargar el PDF')
    }
  }

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
                <th className="px-6 py-3 text-right">IGV</th>
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
                    {inv.currency} {(+inv.subtotal).toFixed(2)}
                  </td>
                  <td className="px-6 py-3 text-right font-mono text-[var(--color-text-2)]">
                    {inv.currency} {(+inv.tax_amount).toFixed(2)}
                  </td>
                  <td className="px-6 py-3 text-right font-mono text-[var(--color-text)] font-semibold">
                    {inv.currency} {(+inv.total).toFixed(2)}
                  </td>
                  <td className="px-6 py-3">
                    <StatusBadge variant={invoiceStatusVariant(inv.status)}>{inv.status}</StatusBadge>
                  </td>
                  <td className="px-6 py-3 text-right">
                    <button onClick={() => downloadPdf(inv.id)}
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
