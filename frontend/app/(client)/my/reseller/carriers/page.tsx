'use client'
import { useEffect, useState } from 'react'
import { apiGet, apiPost, apiPut, apiDelete } from '@/lib/api'
import Link from 'next/link'
import { Plus } from 'lucide-react'

interface Carrier {
  id: number; name: string; host: string; port: number
  priority: number; status: string; outbound_prefix: string; remove_prefix: string; notes: string | null
  rate_count: number; cps_limit: number | null
}

const card  = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'
const input = 'w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm text-[var(--color-text)] focus:outline-none focus:border-brand-500'
const lbl   = 'block text-xs text-[var(--color-text-2)] uppercase tracking-wider mb-1'

const EMPTY = { name: '', host: '', port: 5060, priority: 10, outbound_prefix: '', remove_prefix: '', status: 'active', cps_limit: null, notes: '' }

export default function ResellerCarriers() {
  const [carriers, setCarriers] = useState<Carrier[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [form, setForm] = useState<any>(EMPTY)
  const [editing, setEditing] = useState<number | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [saving, setSaving] = useState(false)

  const load = () => apiGet('/reseller/carriers').then(setCarriers).catch((e: any) => setError(e.message)).finally(() => setLoading(false))
  useEffect(() => { load() }, [])

  function edit(c: Carrier) {
    setForm({ ...c }); setEditing(c.id); setShowForm(true); setError('')
  }

  async function save(e: React.FormEvent) {
    e.preventDefault()
    if (!form.name || !form.host) { setError('Nombre y Host son requeridos'); return }
    setSaving(true); setError('')
    try {
      if (editing) {
        await apiPut(`/reseller/carriers/${editing}`, form)
      } else {
        await apiPost('/reseller/carriers', form)
      }
      setShowForm(false); setForm(EMPTY); setEditing(null); load()
    } catch (e: any) { setError(e.message) }
    finally { setSaving(false) }
  }

  async function del(id: number) {
    if (!confirm('¿Eliminar carrier?')) return
    try { await apiDelete(`/reseller/carriers/${id}`); load() }
    catch (e: any) { alert(e.message) }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-[var(--color-text)]">Carriers propios</h1>
          <p className="text-sm text-[var(--color-text-2)] mt-0.5">Tus troncales SIP — se asignan a tus sub-clientes junto o en vez de los de la plataforma</p>
        </div>
        <button onClick={() => { setShowForm(v => !v); setForm(EMPTY); setEditing(null); setError('') }}
          className="flex items-center gap-1.5 px-4 py-2 bg-brand-600 hover:bg-brand-500 text-white text-sm rounded-lg">
          <Plus size={15}/> Nuevo carrier
        </button>
      </div>

      {error && !showForm && <p className="text-red-400 text-sm">{error}</p>}

      {showForm && (
        <form onSubmit={save} className={`${card} p-6 space-y-4`}>
          <h2 className="font-medium text-[var(--color-text)]">{editing ? 'Editar carrier' : 'Nuevo carrier'}</h2>
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {[['Nombre', 'name', 'text'], ['Host / IP', 'host', 'text'], ['Puerto', 'port', 'number'],
              ['Prefijo saliente', 'outbound_prefix', 'text'], ['Prioridad', 'priority', 'number']].map(([label, key, type]) => (
              <div key={key}>
                <label className={lbl}>{label}</label>
                <input required={key === 'name' || key === 'host'} type={type} value={form[key] ?? ''}
                  onChange={e => setForm((f: any) => ({ ...f, [key]: type === 'number' ? +e.target.value : e.target.value }))}
                  className={input} />
              </div>
            ))}
            <div>
              <label className={lbl}>Estado</label>
              <select value={form.status} onChange={e => setForm((f: any) => ({ ...f, status: e.target.value }))} className={input}>
                <option value="active">Activo</option>
                <option value="inactive">Inactivo</option>
              </select>
            </div>
            <div>
              <label className={lbl}>Límite CPS (vacío = sin límite)</label>
              <input type="number" min={1} max={65535} value={form.cps_limit ?? ''}
                onChange={e => setForm((f: any) => ({ ...f, cps_limit: e.target.value === '' ? null : +e.target.value }))}
                className={input} />
            </div>
          </div>
          <div>
            <label className={lbl}>Notas</label>
            <input value={form.notes ?? ''} onChange={e => setForm((f: any) => ({ ...f, notes: e.target.value }))} className={input} />
          </div>
          <div className="flex gap-3">
            <button type="submit" disabled={saving}
              className="px-4 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm rounded-lg">
              {saving ? 'Guardando…' : 'Guardar'}
            </button>
            <button type="button" onClick={() => { setShowForm(false); setEditing(null) }}
              className="px-4 py-2 text-sm text-[var(--color-muted)] hover:text-[var(--color-text)]">
              Cancelar
            </button>
          </div>
        </form>
      )}

      <div className={`${card} overflow-x-auto`}>
        {loading ? (
          <p className="p-8 text-center text-[var(--color-text-2)] text-sm">Cargando…</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-[var(--color-text-2)] uppercase border-b border-[var(--color-border)]">
                <th className="px-6 py-3 text-left">Nombre</th>
                <th className="px-6 py-3 text-left">Host</th>
                <th className="px-6 py-3 text-left">Puerto</th>
                <th className="px-6 py-3 text-left">Prefijo</th>
                <th className="px-6 py-3 text-left">Prioridad</th>
                <th className="px-6 py-3 text-left">Estado</th>
                <th className="px-6 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              {carriers.map(c => (
                <tr key={c.id} className="hover:bg-white/2">
                  <td className="px-6 py-3 text-[var(--color-text)] font-medium">
                    {c.name}
                    {c.rate_count === 0 && (
                      <span className="ml-2 px-1.5 py-0.5 rounded text-[10px] font-medium bg-red-500/15 text-red-400 align-middle">
                        ⚠ sin tarifas
                      </span>
                    )}
                  </td>
                  <td className="px-6 py-3 font-mono text-xs text-[var(--color-text)]">{c.host}</td>
                  <td className="px-6 py-3 font-mono text-xs text-[var(--color-text-2)]">{c.port}</td>
                  <td className="px-6 py-3 font-mono text-xs text-[var(--color-text-2)]">{c.outbound_prefix || '—'}</td>
                  <td className="px-6 py-3 text-[var(--color-text-2)]">{c.priority}</td>
                  <td className="px-6 py-3">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${c.status === 'active' ? 'bg-green-500/15 text-green-400' : 'bg-zinc-700 text-zinc-400'}`}>
                      {c.status}
                    </span>
                  </td>
                  <td className="px-6 py-3 text-right space-x-3">
                    <Link href={`/my/reseller/carriers/${c.id}`}
                      className={`text-xs ${c.rate_count === 0 ? 'text-red-400 hover:text-red-300 font-medium' : 'text-brand-400 hover:text-brand-300'}`}>
                      {c.rate_count === 0 ? 'Ajustar tarifas →' : 'Tarifas →'}
                    </Link>
                    <button onClick={() => edit(c)} className="text-xs text-brand-400 hover:text-brand-300">Editar</button>
                    <button onClick={() => del(c.id)} className="text-xs text-red-400 hover:text-red-300">Eliminar</button>
                  </td>
                </tr>
              ))}
              {carriers.length === 0 && (
                <tr><td colSpan={7} className="px-6 py-10 text-center text-[var(--color-muted)] text-sm">Sin carriers propios todavía — creá el primero arriba.</td></tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
