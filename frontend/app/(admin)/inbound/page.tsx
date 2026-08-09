'use client'
import { useEffect, useState } from 'react'
import { apiGet, apiPost, apiDelete } from '@/lib/api'
import { Plus, Trash2, PhoneIncoming } from 'lucide-react'

interface LanPeer {
  id: number; host: string; port: number; description: string | null; created_at: string
}

const EMPTY_FORM = { host: '', port: '5060', description: '' }

const cardCls  = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'
const inputCls = 'w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm text-[var(--color-text)] focus:outline-none focus:border-brand-500'
const labelCls = 'block text-xs text-[var(--color-text-2)] uppercase tracking-wider mb-1'

export default function EntrantePage() {
  const [rows, setRows]       = useState<LanPeer[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState('')

  const [form, setForm]     = useState(EMPTY_FORM)
  const [adding, setAdding] = useState(false)

  const load = () =>
    apiGet('/admin/lan-peers').then(setRows).catch((e: any) => setError(e.message)).finally(() => setLoading(false))

  useEffect(() => { load() }, [])

  async function addPeer(e: React.FormEvent) {
    e.preventDefault(); setAdding(true); setError('')
    try {
      await apiPost('/admin/lan-peers', {
        host: form.host,
        port: form.port ? +form.port : 5060,
        description: form.description || null,
      })
      setForm(EMPTY_FORM)
      load()
    } catch (e: any) { setError(e.message) }
    finally { setAdding(false) }
  }

  async function deletePeer(id: number) {
    if (!confirm('¿Eliminar este peer de entrada? Los carriers que apuntaban a este host/puerto dejarán de poder registrar llamadas entrantes.')) return
    try {
      await apiDelete(`/admin/lan-peers/${id}`)
      load()
    } catch (e: any) { alert(e.message) }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-[var(--color-text)] flex items-center gap-2">
          <PhoneIncoming size={20} className="text-brand-500" /> Entrante
        </h1>
        <p className="text-sm text-[var(--color-text-2)] mt-0.5">
          IPs/hosts de Asterisk o tu marcador que reciben las llamadas entrantes desde los carriers —
          arman el Grupo 1 del dispatcher de Kamailio.
        </p>
      </div>

      {error && <div className="bg-red-900/30 border border-red-700 text-red-300 text-sm rounded-lg px-4 py-3">{error}</div>}

      <form onSubmit={addPeer} className={`${cardCls} p-5 space-y-4`}>
        <h2 className="font-medium text-[var(--color-text)]">Nuevo peer de entrada</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <label className={labelCls}>Host / IP</label>
            <input required className={inputCls} placeholder="ej: 10.0.0.20"
              value={form.host} onChange={e => setForm(f => ({ ...f, host: e.target.value }))} />
          </div>
          <div>
            <label className={labelCls}>Puerto</label>
            <input type="number" className={inputCls} placeholder="5060"
              value={form.port} onChange={e => setForm(f => ({ ...f, port: e.target.value }))} />
          </div>
          <div>
            <label className={labelCls}>Descripción (opcional)</label>
            <input className={inputCls} placeholder="ej: Asterisk ViciBox #1"
              value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
          </div>
        </div>
        <button type="submit" disabled={adding}
          className="flex items-center gap-2 px-4 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm rounded-lg transition-colors">
          <Plus size={16} /> {adding ? 'Agregando…' : 'Agregar peer'}
        </button>
      </form>

      <div className={`${cardCls} overflow-x-auto`}>
        {loading ? (
          <p className="p-8 text-center text-[var(--color-text-2)] text-sm">Cargando…</p>
        ) : rows.length === 0 ? (
          <p className="p-10 text-center text-[var(--color-muted)] text-sm">Sin peers configurados todavía — agregá el primero arriba.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-[var(--color-text-2)] uppercase border-b border-[var(--color-border)]">
                <th className="px-6 py-3 text-left">Host</th>
                <th className="px-6 py-3 text-left">Puerto</th>
                <th className="px-6 py-3 text-left">Descripción</th>
                <th className="px-6 py-3 text-left">Agregado</th>
                <th className="px-6 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              {rows.map(r => (
                <tr key={r.id} className="hover:bg-white/2">
                  <td className="px-6 py-3 font-mono text-brand-400">{r.host}</td>
                  <td className="px-6 py-3 font-mono text-[var(--color-text-2)]">{r.port}</td>
                  <td className="px-6 py-3 text-[var(--color-text-2)]">{r.description ?? '—'}</td>
                  <td className="px-6 py-3 text-[var(--color-text-2)] text-xs font-mono">
                    {r.created_at ? new Date(r.created_at).toLocaleDateString() : '—'}
                  </td>
                  <td className="px-6 py-3 text-right">
                    <button onClick={() => deletePeer(r.id)} aria-label="Eliminar peer"
                      className="text-[var(--color-muted)] hover:text-red-400 transition-colors">
                      <Trash2 size={14} />
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
