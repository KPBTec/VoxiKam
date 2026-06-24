'use client'
import { useEffect, useState } from 'react'
import { apiGet, apiPost, apiFetch } from '@/lib/api'

interface Invoice {
  id: number; customer_name: string; period_start: string; period_end: string
  nbcall: number; total_minutes: number; subtotal: number; tax_amount: number
  total: number; currency: string; status: string; created_at: string
  pdf_path: string | null
}

interface Customer { id: number; name: string }

const STATUS: Record<string, string> = {
  draft:   'bg-zinc-700 text-zinc-300',
  sent:    'bg-blue-500/15 text-blue-400',
  paid:    'bg-green-500/15 text-green-400',
  overdue: 'bg-red-500/15 text-red-400',
}

export default function InvoicesPage() {
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [customers, setCustomers] = useState<Customer[]>([])
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ customer_id: '', period_start: '', period_end: '' })
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState('')

  const today = new Date().toISOString().slice(0, 10)
  const firstOfMonth = today.slice(0, 8) + '01'

  const load = () => apiGet('/admin/invoices').then(setInvoices)
  useEffect(() => {
    load()
    apiGet('/admin/customers').then(setCustomers)
    setForm(f => ({ ...f, period_start: firstOfMonth, period_end: today }))
  }, [])

  async function generate() {
    if (!form.customer_id || !form.period_start || !form.period_end) {
      setError('Completa todos los campos'); return
    }
    setGenerating(true); setError('')
    try {
      const p = new URLSearchParams(form)
      await apiPost(`/admin/invoices/generate?${p}`, {})
      setShowForm(false); load()
    } catch (e: any) { setError(e.message) }
    finally { setGenerating(false) }
  }

  async function markPaid(id: number) {
    await apiPost(`/admin/invoices/${id}/mark-paid`, {})
    load()
  }

  async function regenPdf(id: number) {
    try {
      await apiPost(`/admin/invoices/${id}/regen-pdf`, {})
      load()
    } catch (e: any) { alert(e.message) }
  }

  async function downloadPdf(id: number) {
    try {
      const res = await apiFetch(`/admin/invoices/${id}/pdf`)
      if (!res.ok) { alert('PDF no disponible o aún no generado'); return }
      const blob = await res.blob()
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href     = url
      a.download = `factura-${id}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      alert('Error al descargar PDF')
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-white">Facturas</h1>
        <button onClick={() => { setShowForm(true); setError('') }}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded-lg">
          + Generar factura
        </button>
      </div>

      {showForm && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 space-y-4">
          <h2 className="font-medium text-white">Nueva factura</h2>
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-xs text-zinc-400 mb-1">Cliente</label>
              <select value={form.customer_id} onChange={e => setForm(f => ({...f, customer_id: e.target.value}))}
                className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm text-white">
                <option value="">Seleccionar…</option>
                {customers.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs text-zinc-400 mb-1">Período desde</label>
              <input type="date" value={form.period_start} onChange={e => setForm(f => ({...f, period_start: e.target.value}))}
                className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm text-white" />
            </div>
            <div>
              <label className="block text-xs text-zinc-400 mb-1">Período hasta</label>
              <input type="date" value={form.period_end} onChange={e => setForm(f => ({...f, period_end: e.target.value}))}
                className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm text-white" />
            </div>
          </div>
          <div className="flex gap-3">
            <button onClick={generate} disabled={generating}
              className="px-4 py-2 bg-green-700 hover:bg-green-600 disabled:opacity-50 text-white text-sm rounded">
              {generating ? 'Generando PDF…' : 'Generar'}
            </button>
            <button onClick={() => setShowForm(false)}
              className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 text-white text-sm rounded">
              Cancelar
            </button>
          </div>
        </div>
      )}

      <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-zinc-400 uppercase border-b border-zinc-800">
              <th className="px-6 py-3 text-left">#</th>
              <th className="px-6 py-3 text-left">Cliente</th>
              <th className="px-6 py-3 text-left">Período</th>
              <th className="px-6 py-3 text-right">Llamadas</th>
              <th className="px-6 py-3 text-right">Subtotal</th>
              <th className="px-6 py-3 text-right">IGV</th>
              <th className="px-6 py-3 text-right">Total</th>
              <th className="px-6 py-3 text-left">Estado</th>
              <th className="px-6 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800">
            {invoices.map(inv => (
              <tr key={inv.id} className="hover:bg-zinc-800/50">
                <td className="px-6 py-3 text-zinc-400 font-mono">#{inv.id}</td>
                <td className="px-6 py-3 text-white">{inv.customer_name}</td>
                <td className="px-6 py-3 text-zinc-400 text-xs font-mono">{inv.period_start} → {inv.period_end}</td>
                <td className="px-6 py-3 text-right font-mono">{inv.nbcall}</td>
                <td className="px-6 py-3 text-right font-mono text-zinc-300">S/ {(+inv.subtotal).toFixed(2)}</td>
                <td className="px-6 py-3 text-right font-mono text-zinc-400">S/ {(+inv.tax_amount).toFixed(2)}</td>
                <td className="px-6 py-3 text-right font-mono text-white font-semibold">S/ {(+inv.total).toFixed(2)}</td>
                <td className="px-6 py-3">
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS[inv.status] ?? STATUS.draft}`}>
                    {inv.status}
                  </span>
                </td>
                <td className="px-6 py-3 text-right space-x-3">
                  {inv.pdf_path
                    ? <button onClick={() => downloadPdf(inv.id)} className="text-xs text-blue-400 hover:text-blue-300">PDF</button>
                    : <button onClick={() => regenPdf(inv.id)} className="text-xs text-orange-400 hover:text-orange-300">Generar PDF</button>
                  }
                  {inv.status !== 'paid' && (
                    <button onClick={() => markPaid(inv.id)} className="text-xs text-green-400 hover:text-green-300">Pagada</button>
                  )}
                </td>
              </tr>
            ))}
            {invoices.length === 0 && (
              <tr><td colSpan={9} className="px-6 py-10 text-center text-zinc-500 text-sm">Sin facturas generadas</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
