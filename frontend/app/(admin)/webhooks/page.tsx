'use client'
import { Fragment, useEffect, useState } from 'react'
import { apiGet, apiPost, apiPut, apiDelete } from '@/lib/api'
import { Plus, Trash2, RefreshCw, Webhook } from 'lucide-react'
import { Toggle } from '@/components/Toggle'

interface WebhookRow {
  id: number
  url: string
  event: string
  enabled: boolean
  created_at: string
}

interface Delivery {
  id: number
  event: string
  status_code: number | null
  attempt: number
  success: boolean
  error: string | null
  created_at: string
}

const card = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'

export default function WebhooksPage() {
  const [events, setEvents] = useState<string[]>([])
  const [hooks, setHooks] = useState<WebhookRow[]>([])
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState({ url: '', event: '' })
  const [creating, setCreating] = useState(false)
  const [newSecret, setNewSecret] = useState<string | null>(null)

  const [openId, setOpenId] = useState<number | null>(null)
  const [deliveries, setDeliveries] = useState<Delivery[]>([])
  const [error, setError] = useState('')

  async function load() {
    setLoading(true); setError('')
    try {
      const [e, h] = await Promise.all([
        apiGet('/admin/webhooks/events'),
        apiGet('/admin/webhooks'),
      ])
      setEvents(e)
      setForm(f => ({ ...f, event: f.event || e[0] || '' }))
      setHooks(h)
    } catch (e: any) { setError(e.message || 'Error cargando webhooks') }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  async function create(e: React.FormEvent) {
    e.preventDefault(); setCreating(true); setNewSecret(null)
    try {
      const r = await apiPost('/admin/webhooks', { ...form, enabled: true })
      setNewSecret(r.secret)
      setForm(f => ({ ...f, url: '' }))
      await load()
    } finally { setCreating(false) }
  }

  // Optimista — antes recargaba TODA la lista con un setLoading(true) de
  // por medio, reemplazando la página entera por "Cargando..." en cada click.
  async function toggle(h: WebhookRow) {
    setHooks(hs => hs.map(x => x.id === h.id ? { ...x, enabled: !x.enabled } : x))
    try {
      await apiPut(`/admin/webhooks/${h.id}`, { url: h.url, event: h.event, enabled: !h.enabled })
    } catch (e: any) {
      setHooks(hs => hs.map(x => x.id === h.id ? { ...x, enabled: h.enabled } : x))
      setError(e.message || 'Error actualizando el webhook')
    }
  }

  async function remove(h: WebhookRow) {
    if (!confirm(`¿Eliminar el webhook hacia ${h.url}?`)) return
    await apiDelete(`/admin/webhooks/${h.id}`)
    if (openId === h.id) setOpenId(null)
    load()
  }

  async function rotate(h: WebhookRow) {
    if (!confirm('Esto invalida el secret anterior — cualquier verificación de firma que use el viejo dejará de funcionar. ¿Continuar?')) return
    const r = await apiPost(`/admin/webhooks/${h.id}/rotate-secret`, {})
    setNewSecret(r.secret)
  }

  async function viewDeliveries(h: WebhookRow) {
    if (openId === h.id) { setOpenId(null); return }
    setOpenId(h.id)
    setDeliveries(await apiGet(`/admin/webhooks/${h.id}/deliveries`))
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Webhooks</h1>
        <p className="text-sm text-[var(--color-text-2)] mt-1">
          Notifica a un sistema externo por HTTP POST cuando ocurre un evento — firmado con HMAC-SHA256
          en el header <code className="text-xs">X-VoxiKam-Signature</code>. Un reintento inmediato si falla, sin colas.
        </p>
      </div>

      {error && <div className="bg-red-900/30 border border-red-700 text-red-300 text-sm rounded-lg px-4 py-3">{error}</div>}

      <form onSubmit={create} className={`${card} p-5 space-y-3`}>
        <h2 className="font-semibold text-sm flex items-center gap-2"><Webhook size={15} /> Nuevo webhook</h2>
        <div className="grid grid-cols-[2fr_1fr_auto] gap-3 items-end">
          <div>
            <label className="block text-xs text-[var(--color-text-2)] mb-1">URL destino</label>
            <input required type="url" value={form.url} onChange={e => setForm(f => ({ ...f, url: e.target.value }))}
              placeholder="https://tu-sistema.com/webhooks/voxikam"
              className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-xs text-[var(--color-text-2)] mb-1">Evento</label>
            <select value={form.event} onChange={e => setForm(f => ({ ...f, event: e.target.value }))}
              className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm">
              {events.map(ev => <option key={ev} value={ev}>{ev}</option>)}
            </select>
          </div>
          <button type="submit" disabled={creating}
            className="flex items-center gap-1.5 px-3 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-xs font-medium rounded-lg">
            <Plus size={13} /> Crear
          </button>
        </div>
        {newSecret && (
          <div className="bg-[var(--color-surface)] border border-brand-500/40 rounded-lg p-3">
            <p className="text-xs text-[var(--color-text-2)] mb-1">
              Secret — se muestra <strong>una sola vez</strong>, guardalo ahora:
            </p>
            <code className="text-xs text-brand-400 break-all">{newSecret}</code>
          </div>
        )}
      </form>

      <div className={`${card} overflow-x-auto`}>
        {loading ? (
          <div className="text-[var(--color-muted)] p-8 text-center text-sm">Cargando...</div>
        ) : hooks.length === 0 ? (
          <div className="text-[var(--color-muted)] p-8 text-center text-sm">Sin webhooks todavía</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[var(--color-text-2)] text-xs uppercase border-b border-[var(--color-border)]">
                <th className="px-5 py-3 text-left">URL</th>
                <th className="px-5 py-3 text-left">Evento</th>
                <th className="px-5 py-3 text-center">Activo</th>
                <th className="px-5 py-3 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {hooks.map(h => (
                <Fragment key={h.id}>
                  <tr className="border-b border-[var(--color-border)]/50">
                    <td className="px-5 py-2.5 font-mono text-xs truncate max-w-[280px]">{h.url}</td>
                    <td className="px-5 py-2.5 text-xs text-orange-400">{h.event}</td>
                    <td className="px-5 py-2.5 text-center">
                      <Toggle checked={h.enabled} onChange={() => toggle(h)} label={`Activar webhook ${h.url}`} />
                    </td>
                    <td className="px-5 py-2.5">
                      <div className="flex justify-end gap-3">
                        <button onClick={() => viewDeliveries(h)} className="text-xs text-[var(--color-muted)] hover:text-white">
                          {openId === h.id ? 'Ocultar' : 'Historial'}
                        </button>
                        <button onClick={() => rotate(h)} title="Rotar secret" aria-label="Rotar secret" className="text-[var(--color-muted)] hover:text-white">
                          <RefreshCw size={14} />
                        </button>
                        <button onClick={() => remove(h)} aria-label="Eliminar webhook" className="text-[var(--color-muted)] hover:text-red-400">
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                  {openId === h.id && (
                    <tr className="bg-black/20">
                      <td colSpan={4} className="px-5 py-3">
                        {deliveries.length === 0 ? (
                          <p className="text-xs text-[var(--color-muted)]">Sin entregas todavía</p>
                        ) : (
                          <table className="w-full text-xs">
                            <thead>
                              <tr className="text-[var(--color-text-2)] uppercase">
                                <th className="text-left pb-1">Fecha</th>
                                <th className="text-left pb-1">Intento</th>
                                <th className="text-left pb-1">HTTP</th>
                                <th className="text-left pb-1">Resultado</th>
                              </tr>
                            </thead>
                            <tbody>
                              {deliveries.map(d => (
                                <tr key={d.id} className="border-t border-[var(--color-border)]/30">
                                  <td className="py-1.5 text-[var(--color-muted)]">{new Date(d.created_at).toLocaleString('es-PE')}</td>
                                  <td className="py-1.5">{d.attempt}</td>
                                  <td className="py-1.5">{d.status_code ?? '—'}</td>
                                  <td className={`py-1.5 ${d.success ? 'text-green-400' : 'text-red-400'}`}>
                                    {d.success ? 'OK' : (d.error ?? 'error')}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
