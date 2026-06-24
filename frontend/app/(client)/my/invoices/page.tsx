'use client'
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

const STATUS: Record<string, string> = {
  draft:   'bg-zinc-700 text-zinc-300',
  sent:    'bg-blue-500/15 text-blue-400',
  paid:    'bg-green-500/15 text-green-400',
  overdue: 'bg-red-500/15 text-red-400',
}

export default function MyInvoices() {
  const router = useRouter()
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [loading, setLoading]   = useState(true)

  useEffect(() => {
    const user = getUser()
    if (user?.role === 'client' && user?.show_invoices === false) {
      router.replace('/my/overview')
      return
    }
    apiGet('/my/invoices').then(setInvoices).finally(() => setLoading(false))
  }, [])

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-white">Mis facturas</h1>

      <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
        {loading ? (
          <p className="p-8 text-center text-zinc-400 text-sm">Cargando…</p>
        ) : invoices.length === 0 ? (
          <p className="p-10 text-center text-zinc-500 text-sm">Sin facturas por ahora</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-zinc-400 uppercase border-b border-zinc-800">
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
            <tbody className="divide-y divide-zinc-800">
              {invoices.map(inv => (
                <tr key={inv.id} className="hover:bg-zinc-800/50">
                  <td className="px-6 py-3 text-zinc-400 font-mono">#{inv.id}</td>
                  <td className="px-6 py-3 text-zinc-300 text-xs font-mono">
                    {inv.period_start} → {inv.period_end}
                  </td>
                  <td className="px-6 py-3 text-right font-mono">{inv.nbcall}</td>
                  <td className="px-6 py-3 text-right font-mono text-zinc-400">
                    {parseFloat(String(inv.total_minutes)).toFixed(0)} min
                  </td>
                  <td className="px-6 py-3 text-right font-mono text-zinc-300">
                    S/ {(+inv.subtotal).toFixed(2)}
                  </td>
                  <td className="px-6 py-3 text-right font-mono text-white font-semibold">
                    S/ {(+inv.total).toFixed(2)}
                  </td>
                  <td className="px-6 py-3">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS[inv.status] ?? STATUS.draft}`}>
                      {inv.status}
                    </span>
                  </td>
                  <td className="px-6 py-3 text-right">
                    <button onClick={() => window.open(`/api/admin/invoices/${inv.id}/pdf`, '_blank')}
                      className="text-xs text-blue-400 hover:text-blue-300">
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
