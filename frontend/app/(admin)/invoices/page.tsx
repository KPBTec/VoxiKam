'use client'
import { useEffect, useState } from 'react'
import { apiGet, apiPost, apiPut, apiFetch } from '@/lib/api'
import { StatusBadge, invoiceStatusVariant } from '@/components/StatusBadge'
import { ErrorBanner } from '@/components/ErrorBanner'
import { Button } from '@/components/Button'
import { Card } from '@/components/Card'

interface Invoice {
  id: number; customer_name: string; period_start: string; period_end: string
  nbcall: number; total_minutes: number; subtotal: number; tax_amount: number
  total: number; currency: string; status: string; created_at: string
  pdf_path: string | null; emailed_at: string | null
}

interface Customer { id: number; name: string }

export default function InvoicesPage() {
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [customers, setCustomers] = useState<Customer[]>([])
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ customer_id: '', period_start: '', period_end: '' })
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState('')
  const [autoEmail, setAutoEmail] = useState(false)
  const [sendingId, setSendingId] = useState<number | null>(null)

  const today = new Date().toISOString().slice(0, 10)
  const firstOfMonth = today.slice(0, 8) + '01'

  const load = () => apiGet('/admin/invoices').then(setInvoices).catch((e: any) => setError(e.message))
  useEffect(() => { document.title = 'Facturas · VoxiKam' }, [])
  useEffect(() => {
    load()
    apiGet('/admin/customers').then(setCustomers).catch((e: any) => setError(e.message))
    apiGet('/admin/invoices/settings/auto-email').then(r => setAutoEmail(r.enabled)).catch(() => {})
    setForm(f => ({ ...f, period_start: firstOfMonth, period_end: today }))
  }, [])

  async function toggleAutoEmail() {
    const next = !autoEmail
    setAutoEmail(next)
    await apiPut('/admin/invoices/settings/auto-email', { enabled: next })
  }

  async function sendEmail(id: number) {
    setSendingId(id)
    try {
      await apiPost(`/admin/invoices/${id}/send-email`, {})
      load()
    } catch (e: any) {
      alert(e.message)
    } finally { setSendingId(null) }
  }

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
        <h1 className="text-xl font-semibold text-[var(--color-text)]">Facturas</h1>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-[var(--color-text-2)] cursor-pointer">
            <button type="button" onClick={toggleAutoEmail}
              className={`relative w-9 h-5 rounded-full transition-colors focus-ring ${autoEmail ? 'bg-brand-600' : 'bg-[var(--color-border-2)]'}`}>
              <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${autoEmail ? 'translate-x-4' : 'translate-x-0.5'}`} />
            </button>
            Enviar por correo automáticamente al generar
          </label>
          <Button onClick={() => { setShowForm(true); setError('') }}>
            + Generar factura
          </Button>
        </div>
      </div>

      {error && !showForm && <ErrorBanner>{error}</ErrorBanner>}

      {showForm && (
        <Card className="p-6 space-y-4">
          <h2 className="font-medium text-[var(--color-text)]">Nueva factura</h2>
          {error && <ErrorBanner>{error}</ErrorBanner>}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label htmlFor="inv-customer" className="block text-xs text-[var(--color-text-2)] mb-1">Cliente</label>
              <select id="inv-customer" value={form.customer_id} onChange={e => setForm(f => ({...f, customer_id: e.target.value}))}
                className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-3 py-2 text-sm text-[var(--color-text)] focus-ring">
                <option value="">Seleccionar…</option>
                {customers.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="inv-period-start" className="block text-xs text-[var(--color-text-2)] mb-1">Período desde</label>
              <input id="inv-period-start" type="date" value={form.period_start} onChange={e => setForm(f => ({...f, period_start: e.target.value}))}
                className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-3 py-2 text-sm text-[var(--color-text)] focus-ring" />
            </div>
            <div>
              <label htmlFor="inv-period-end" className="block text-xs text-[var(--color-text-2)] mb-1">Período hasta</label>
              <input id="inv-period-end" type="date" value={form.period_end} onChange={e => setForm(f => ({...f, period_end: e.target.value}))}
                className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-3 py-2 text-sm text-[var(--color-text)] focus-ring" />
            </div>
          </div>
          <div className="flex gap-3">
            <button onClick={generate} disabled={generating}
              className="px-4 py-2 bg-success/80 hover:bg-success disabled:opacity-50 text-white text-sm rounded focus-ring">
              {generating ? 'Generando PDF…' : 'Generar'}
            </button>
            <button onClick={() => setShowForm(false)}
              className="px-4 py-2 bg-[var(--color-border-2)] hover:bg-[var(--color-muted)] text-[var(--color-text)] text-sm rounded focus-ring">
              Cancelar
            </button>
          </div>
        </Card>
      )}

      <Card className="overflow-x-auto">
        <table className="w-full text-sm tabular-nums">
          <thead>
            <tr className="text-xs text-[var(--color-text-2)] uppercase border-b border-[var(--color-border)]">
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
          <tbody className="divide-y divide-[var(--color-border)]">
            {invoices.map(inv => (
              <tr key={inv.id} className="hover:bg-white/2">
                <td className="px-6 py-3 text-[var(--color-text-2)] font-mono">#{inv.id}</td>
                <td className="px-6 py-3 text-[var(--color-text)]">{inv.customer_name}</td>
                <td className="px-6 py-3 text-[var(--color-text-2)] text-xs font-mono">{inv.period_start} → {inv.period_end}</td>
                <td className="px-6 py-3 text-right font-mono">{inv.nbcall}</td>
                <td className="px-6 py-3 text-right font-mono text-[var(--color-text-2)]">{inv.currency} {(+inv.subtotal).toFixed(2)}</td>
                <td className="px-6 py-3 text-right font-mono text-[var(--color-text-2)]">{inv.currency} {(+inv.tax_amount).toFixed(2)}</td>
                <td className="px-6 py-3 text-right font-mono text-[var(--color-text)] font-semibold">{inv.currency} {(+inv.total).toFixed(2)}</td>
                <td className="px-6 py-3">
                  <StatusBadge variant={invoiceStatusVariant(inv.status)}>{inv.status}</StatusBadge>
                  {inv.emailed_at && (
                    <span className="block text-[10px] text-[var(--color-muted)] mt-1" title={new Date(inv.emailed_at).toLocaleString('es-PE')}>
                      enviada por correo
                    </span>
                  )}
                </td>
                <td className="px-6 py-3 text-right space-x-3">
                  {inv.pdf_path
                    ? <button onClick={() => downloadPdf(inv.id)} className="text-xs text-brand-400 hover:text-brand-300 focus-ring">PDF</button>
                    : <button onClick={() => regenPdf(inv.id)} className="text-xs text-warning hover:text-warning/80 focus-ring">Generar PDF</button>
                  }
                  {inv.pdf_path && (
                    <button onClick={() => sendEmail(inv.id)} disabled={sendingId === inv.id}
                      className="text-xs text-info-400 hover:text-info-300 disabled:opacity-50 focus-ring">
                      {sendingId === inv.id ? 'Enviando…' : inv.emailed_at ? 'Reenviar' : 'Enviar'}
                    </button>
                  )}
                  {inv.status !== 'paid' && (
                    <button onClick={() => markPaid(inv.id)} className="text-xs text-success hover:text-success/80 focus-ring">Pagada</button>
                  )}
                </td>
              </tr>
            ))}
            {invoices.length === 0 && (
              <tr><td colSpan={9} className="px-6 py-10 text-center text-[var(--color-muted)] text-sm">Sin facturas generadas</td></tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
