'use client'
import { useEffect, useState } from 'react'
import { apiGet, apiPost, apiPut, apiDelete } from '@/lib/api'
import { Plus, Trash2, PhoneOff } from 'lucide-react'

interface Policy {
  id: number
  label: string
  code_column: string
  threshold_pct: string
  min_calls: number
  active: boolean
}

interface Column { value: string; label: string }

interface AlertRow {
  id: number
  ts_hour: string
  pct: string
  total_calls: number
  created_at: string
  policy_label: string
  customer_name: string
}

const card = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'

export default function DisconnectPoliciesPage() {
  const [policies, setPolicies] = useState<Policy[]>([])
  const [columns, setColumns] = useState<Column[]>([])
  const [alerts, setAlerts] = useState<AlertRow[]>([])
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState({ label: '', code_column: '', threshold_pct: '', min_calls: '20' })
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')

  async function load() {
    setLoading(true); setError('')
    try {
      const [p, c, a] = await Promise.all([
        apiGet('/admin/disconnect-policies'),
        apiGet('/admin/disconnect-policies/columns'),
        apiGet('/admin/disconnect-policies/alerts'),
      ])
      setPolicies(p)
      setColumns(c)
      setForm(f => ({ ...f, code_column: f.code_column || c[0]?.value || '' }))
      setAlerts(a)
    } catch (e: any) { setError(e.message || 'Error cargando políticas') }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  async function create(e: React.FormEvent) {
    e.preventDefault(); setCreating(true)
    try {
      await apiPost('/admin/disconnect-policies', {
        label: form.label, code_column: form.code_column,
        threshold_pct: parseFloat(form.threshold_pct), min_calls: parseInt(form.min_calls) || 20,
      })
      setForm(f => ({ ...f, label: '', threshold_pct: '' }))
      await load()
    } finally { setCreating(false) }
  }

  async function toggle(p: Policy) {
    await apiPut(`/admin/disconnect-policies/${p.id}`, { active: !p.active })
    load()
  }

  async function remove(p: Policy) {
    if (!confirm(`¿Eliminar la política "${p.label}"?`)) return
    await apiDelete(`/admin/disconnect-policies/${p.id}`)
    load()
  }

  const colLabel = (v: string) => columns.find(c => c.value === v)?.label ?? v

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Disconnect Policies</h1>
        <p className="text-sm text-[var(--color-text-2)] mt-1">
          Avisa cuando un cliente cruza un % de un tipo de corte (503, 486, 404...) dentro de una hora —
          usa los mismos datos de <a href="/quality" className="underline">Calidad ASR</a>. Solo informa, nunca suspende ni bloquea.
        </p>
      </div>

      {error && <div className="bg-red-900/30 border border-red-700 text-red-300 text-sm rounded-lg px-4 py-3">{error}</div>}

      <form onSubmit={create} className={`${card} p-5 space-y-3`}>
        <h2 className="font-semibold text-sm flex items-center gap-2"><PhoneOff size={15} /> Nueva política</h2>
        <div className="grid grid-cols-[2fr_2fr_1fr_1fr_auto] gap-3 items-end">
          <div>
            <label className="block text-xs text-[var(--color-text-2)] mb-1">Nombre</label>
            <input required value={form.label} onChange={e => setForm(f => ({ ...f, label: e.target.value }))}
              placeholder="Congestión alta"
              className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-xs text-[var(--color-text-2)] mb-1">Tipo de corte</label>
            <select value={form.code_column} onChange={e => setForm(f => ({ ...f, code_column: e.target.value }))}
              className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm">
              {columns.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs text-[var(--color-text-2)] mb-1">% umbral</label>
            <input required type="number" step="0.1" value={form.threshold_pct}
              onChange={e => setForm(f => ({ ...f, threshold_pct: e.target.value }))}
              className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-xs text-[var(--color-text-2)] mb-1">Mín. llamadas</label>
            <input type="number" value={form.min_calls} onChange={e => setForm(f => ({ ...f, min_calls: e.target.value }))}
              className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm" />
          </div>
          <button type="submit" disabled={creating}
            className="flex items-center gap-1.5 px-3 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-xs font-medium rounded-lg">
            <Plus size={13} /> Crear
          </button>
        </div>
      </form>

      <div className={`${card} overflow-x-auto`}>
        {loading ? (
          <div className="text-[var(--color-muted)] p-8 text-center text-sm">Cargando...</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[var(--color-text-2)] text-xs uppercase border-b border-[var(--color-border)]">
                <th className="px-5 py-3 text-left">Política</th>
                <th className="px-5 py-3 text-left">Tipo de corte</th>
                <th className="px-5 py-3 text-right">Umbral</th>
                <th className="px-5 py-3 text-right">Mín. llamadas</th>
                <th className="px-5 py-3 text-center">Activa</th>
                <th className="px-5 py-3 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {policies.map(p => (
                <tr key={p.id} className="border-b border-[var(--color-border)]/50">
                  <td className="px-5 py-2.5">{p.label}</td>
                  <td className="px-5 py-2.5 text-xs text-orange-400">{colLabel(p.code_column)}</td>
                  <td className="px-5 py-2.5 text-right font-mono">{p.threshold_pct}%</td>
                  <td className="px-5 py-2.5 text-right">{p.min_calls}</td>
                  <td className="px-5 py-2.5 text-center">
                    <button onClick={() => toggle(p)}
                      className={`relative w-9 h-5 rounded-full transition-colors ${p.active ? 'bg-brand-600' : 'bg-zinc-700'}`}>
                      <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${p.active ? 'translate-x-4' : 'translate-x-0.5'}`} />
                    </button>
                  </td>
                  <td className="px-5 py-2.5 text-right">
                    <button onClick={() => remove(p)} aria-label="Eliminar política" className="text-[var(--color-muted)] hover:text-red-400">
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
              {policies.length === 0 && (
                <tr><td colSpan={6} className="px-5 py-8 text-center text-[var(--color-muted)] text-sm">Sin políticas todavía</td></tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      <div className={`${card} overflow-x-auto`}>
        <div className="px-5 py-3 border-b border-[var(--color-border)]">
          <h2 className="font-semibold text-sm">Últimas alertas</h2>
        </div>
        {alerts.length === 0 ? (
          <div className="text-[var(--color-muted)] p-8 text-center text-sm">Sin alertas todavía</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[var(--color-text-2)] text-xs uppercase border-b border-[var(--color-border)]">
                <th className="px-5 py-3 text-left">Cliente</th>
                <th className="px-5 py-3 text-left">Política</th>
                <th className="px-5 py-3 text-left">Hora</th>
                <th className="px-5 py-3 text-right">%</th>
                <th className="px-5 py-3 text-right">Llamadas</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map(a => (
                <tr key={a.id} className="border-b border-[var(--color-border)]/50">
                  <td className="px-5 py-2.5">{a.customer_name}</td>
                  <td className="px-5 py-2.5 text-xs text-orange-400">{a.policy_label}</td>
                  <td className="px-5 py-2.5 text-xs text-[var(--color-muted)]">{new Date(a.ts_hour).toLocaleString('es-PE')}</td>
                  <td className="px-5 py-2.5 text-right font-mono">{a.pct}%</td>
                  <td className="px-5 py-2.5 text-right">{a.total_calls}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
