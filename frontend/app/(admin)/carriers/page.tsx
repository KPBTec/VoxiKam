'use client'
import { useEffect, useState } from 'react'
import { apiGet, apiPost, apiFetch } from '@/lib/api'
import Link from 'next/link'

interface Carrier {
  id: number; name: string; host: string; port: number
  priority: number; status: string; outbound_prefix: string; notes: string
}

const EMPTY = { name: '', host: '', port: 5060, priority: 10, outbound_prefix: '', remove_prefix: '', status: 'active', notes: '' }

export default function CarriersPage() {
  const [carriers, setCarriers] = useState<Carrier[]>([])
  const [form, setForm] = useState<any>(EMPTY)
  const [editing, setEditing] = useState<number | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const load = () => apiGet('/admin/carriers').then(setCarriers)
  useEffect(() => { load() }, [])

  function edit(c: Carrier) {
    setForm({ ...c }); setEditing(c.id); setShowForm(true); setError('')
  }

  async function save() {
    if (!form.name || !form.host) { setError('Nombre y Host son requeridos'); return }
    setSaving(true); setError('')
    try {
      if (editing) {
        await apiFetch(`/admin/carriers/${editing}`, { method: 'PUT', body: JSON.stringify(form) })
      } else {
        await apiPost('/admin/carriers', form)
      }
      setShowForm(false); setForm(EMPTY); setEditing(null); load()
    } catch (e: any) { setError(e.message) }
    finally { setSaving(false) }
  }

  async function del(id: number) {
    if (!confirm('¿Eliminar carrier?')) return
    await apiFetch(`/admin/carriers/${id}`, { method: 'DELETE' })
    load()
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-white">Carriers / Proveedores</h1>
        <button onClick={() => { setShowForm(true); setForm(EMPTY); setEditing(null) }}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded-lg">
          + Nuevo carrier
        </button>
      </div>

      {showForm && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 space-y-4">
          <h2 className="font-medium text-white">{editing ? 'Editar carrier' : 'Nuevo carrier'}</h2>
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <div className="grid grid-cols-2 gap-4">
            {[['Nombre', 'name', 'text'], ['Host / IP', 'host', 'text'], ['Puerto', 'port', 'number'], ['Prefijo saliente', 'outbound_prefix', 'text'], ['Prioridad', 'priority', 'number']].map(([label, key, type]) => (
              <div key={key}>
                <label className="block text-xs text-zinc-400 mb-1">{label}</label>
                <input type={type} value={form[key] ?? ''} onChange={e => setForm((f: any) => ({ ...f, [key]: type === 'number' ? +e.target.value : e.target.value }))}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm text-white" />
              </div>
            ))}
            <div>
              <label className="block text-xs text-zinc-400 mb-1">Estado</label>
              <select value={form.status} onChange={e => setForm((f: any) => ({ ...f, status: e.target.value }))}
                className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm text-white">
                <option value="active">Activo</option>
                <option value="inactive">Inactivo</option>
              </select>
            </div>
          </div>
          <div>
            <label className="block text-xs text-zinc-400 mb-1">Notas</label>
            <input value={form.notes ?? ''} onChange={e => setForm((f: any) => ({ ...f, notes: e.target.value }))}
              className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm text-white" />
          </div>
          <div className="flex gap-3">
            <button onClick={save} disabled={saving}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm rounded">
              {saving ? 'Guardando…' : 'Guardar'}
            </button>
            <button onClick={() => { setShowForm(false); setEditing(null) }}
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
              <th className="px-6 py-3 text-left">Nombre</th>
              <th className="px-6 py-3 text-left">Host</th>
              <th className="px-6 py-3 text-left">Puerto</th>
              <th className="px-6 py-3 text-left">Prefijo</th>
              <th className="px-6 py-3 text-left">Prioridad</th>
              <th className="px-6 py-3 text-left">Estado</th>
              <th className="px-6 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800">
            {carriers.map(c => (
              <tr key={c.id} className="hover:bg-zinc-800/50">
                <td className="px-6 py-3 text-white font-medium">{c.name}</td>
                <td className="px-6 py-3 font-mono text-xs text-zinc-300">{c.host}</td>
                <td className="px-6 py-3 font-mono text-xs text-zinc-400">{c.port}</td>
                <td className="px-6 py-3 font-mono text-xs text-zinc-400">{c.outbound_prefix || '—'}</td>
                <td className="px-6 py-3 text-zinc-400">{c.priority}</td>
                <td className="px-6 py-3">
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${c.status === 'active' ? 'bg-green-500/15 text-green-400' : 'bg-zinc-700 text-zinc-400'}`}>
                    {c.status}
                  </span>
                </td>
                <td className="px-6 py-3 text-right space-x-3">
                  <Link href={`/carriers/${c.id}`} className="text-xs text-brand-400 hover:text-brand-300">Tarifas →</Link>
                  <button onClick={() => edit(c)} className="text-xs text-blue-400 hover:text-blue-300">Editar</button>
                  <button onClick={() => del(c.id)} className="text-xs text-red-400 hover:text-red-300">Eliminar</button>
                </td>
              </tr>
            ))}
            {carriers.length === 0 && (
              <tr><td colSpan={7} className="px-6 py-10 text-center text-zinc-500 text-sm">Sin carriers configurados</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
