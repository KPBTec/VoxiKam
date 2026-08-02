'use client'
import { useEffect, useState } from 'react'
import { apiGet, apiPost, apiPut, apiDelete } from '@/lib/api'
import { Plus, Pencil, Trash2, Check, X, MapPin } from 'lucide-react'
import { ErrorBanner } from '@/components/ErrorBanner'

interface Area {
  id: number
  name: string
  description: string | null
  country_code: string
  country_name: string | null
  prefix_count: number
}

interface Country { code: string; name: string }

const card = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'

export default function AreaGroupsPage() {
  const [areas, setAreas] = useState<Area[]>([])
  const [loading, setLoading] = useState(true)
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [newCountry, setNewCountry] = useState('PE')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const [countries, setCountries] = useState<Country[]>([])

  const [editingId, setEditingId] = useState<number | null>(null)
  const [editName, setEditName] = useState('')
  const [editDesc, setEditDesc] = useState('')
  const [editCountry, setEditCountry] = useState('PE')

  async function loadAreas() {
    setLoading(true)
    try { setAreas(await apiGet('/admin/areas')); setError('') }
    catch (err) { setError(err instanceof Error ? err.message : 'Error cargando grupos de prefijos') }
    finally { setLoading(false) }
  }

  useEffect(() => {
    loadAreas()
    apiGet('/admin/areas/countries').then(setCountries).catch(() => {})
  }, [])

  async function createArea(e: React.FormEvent) {
    e.preventDefault()
    setError(''); setCreating(true)
    try {
      await apiPost('/admin/areas', { name: newName, description: newDesc || null, country_code: newCountry })
      setNewName(''); setNewDesc(''); setNewCountry('PE')
      await loadAreas()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al crear el grupo de prefijos')
    } finally { setCreating(false) }
  }

  function startEdit(a: Area) {
    setEditingId(a.id); setEditName(a.name); setEditDesc(a.description ?? ''); setEditCountry(a.country_code ?? 'PE')
  }

  async function saveEdit(id: number) {
    setError('')
    try {
      await apiPut(`/admin/areas/${id}`, { name: editName, description: editDesc || null, country_code: editCountry })
      setEditingId(null)
      await loadAreas()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al guardar')
    }
  }

  async function removeArea(a: Area) {
    if (a.prefix_count > 0) return
    if (!confirm(`¿Eliminar el grupo de prefijos "${a.name}"?`)) return
    await apiDelete(`/admin/areas/${a.id}`)
    await loadAreas()
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Grupos de prefijos</h1>
        <p className="text-sm text-[var(--color-text-2)] mt-1">
          Los grupos de prefijos agrupan prefijos de destino para tarifar y reportar en bloque.
          Renombrar un grupo acá actualiza el grupo en todos sus prefijos. Los prefijos en sí se
          asignan a un grupo desde <a href="/prefixes" className="underline">Tarifas → Prefijos</a>.
          El reporte de consumo por grupo/país/prefijo está en{' '}
          <a href="/areas" className="underline">Reportes → Por destino</a>.
        </p>
      </div>

      {error && <ErrorBanner>{error}</ErrorBanner>}

      <div className={`${card} p-5`}>
        <h2 className="font-semibold text-sm mb-4 flex items-center gap-2"><MapPin size={15} /> Nuevo grupo</h2>
        <form onSubmit={createArea} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_2fr_auto] gap-3 items-end">
          <div>
            <label className="block text-xs text-[var(--color-text-2)] mb-1">País</label>
            <select value={newCountry} onChange={e => setNewCountry(e.target.value)}
              className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm cursor-pointer">
              {countries.map(c => <option key={c.code} value={c.code}>{c.name}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs text-[var(--color-text-2)] mb-1">Nombre</label>
            <input required value={newName} onChange={e => setNewName(e.target.value)}
              placeholder="USA/CANADA"
              className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-xs text-[var(--color-text-2)] mb-1">Descripción (opcional)</label>
            <input value={newDesc} onChange={e => setNewDesc(e.target.value)}
              placeholder="Destinos fijos y móviles de USA y Canadá"
              className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm" />
          </div>
          <button type="submit" disabled={creating}
            className="flex items-center gap-1.5 px-3 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-xs font-medium rounded-lg">
            <Plus size={13} /> Crear
          </button>
        </form>
      </div>

      <div className={`${card} overflow-x-auto`}>
        <div className="px-5 py-3 border-b border-[var(--color-border)]">
          <h2 className="font-semibold text-sm">Grupos de prefijos registrados</h2>
        </div>
        {loading ? (
          <div className="text-[var(--color-muted)] p-8 text-center text-sm">Cargando...</div>
        ) : areas.length === 0 ? (
          <div className="text-[var(--color-muted)] p-8 text-center text-sm">Sin grupos de prefijos todavía</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[var(--color-text-2)] text-xs uppercase border-b border-[var(--color-border)]">
                <th className="px-5 py-3 text-left">País</th>
                <th className="px-5 py-3 text-left">Nombre</th>
                <th className="px-5 py-3 text-left">Descripción</th>
                <th className="px-5 py-3 text-right">Prefijos</th>
                <th className="px-5 py-3 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {areas.map(a => (
                <tr key={a.id} className="border-b border-[var(--color-border)]/50">
                  {editingId === a.id ? (
                    <>
                      <td className="px-5 py-2">
                        <select value={editCountry} onChange={e => setEditCountry(e.target.value)}
                          className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-2 py-1 text-sm cursor-pointer">
                          {countries.map(c => <option key={c.code} value={c.code}>{c.name}</option>)}
                        </select>
                      </td>
                      <td className="px-5 py-2">
                        <input value={editName} onChange={e => setEditName(e.target.value)}
                          className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-2 py-1 text-sm" />
                      </td>
                      <td className="px-5 py-2">
                        <input value={editDesc} onChange={e => setEditDesc(e.target.value)}
                          className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-2 py-1 text-sm" />
                      </td>
                      <td className="px-5 py-2 text-right text-[var(--color-muted)]">{a.prefix_count}</td>
                      <td className="px-5 py-2">
                        <div className="flex justify-end gap-2">
                          <button onClick={() => saveEdit(a.id)} className="text-green-400 hover:text-green-300"><Check size={15} /></button>
                          <button onClick={() => setEditingId(null)} className="text-[var(--color-muted)] hover:text-white"><X size={15} /></button>
                        </div>
                      </td>
                    </>
                  ) : (
                    <>
                      <td className="px-5 py-2.5 text-[var(--color-text-2)]">{a.country_name ?? a.country_code}</td>
                      <td className="px-5 py-2.5 font-medium">{a.name}</td>
                      <td className="px-5 py-2.5 text-[var(--color-text-2)]">{a.description ?? '—'}</td>
                      <td className="px-5 py-2.5 text-right">{a.prefix_count}</td>
                      <td className="px-5 py-2.5">
                        <div className="flex justify-end gap-3">
                          <button onClick={() => startEdit(a)} className="text-[var(--color-muted)] hover:text-white"><Pencil size={14} /></button>
                          <button
                            onClick={() => removeArea(a)}
                            disabled={a.prefix_count > 0}
                            title={a.prefix_count > 0 ? 'Reasigna sus prefijos antes de eliminarla' : 'Eliminar'}
                            className="text-[var(--color-muted)] hover:text-red-400 disabled:opacity-30 disabled:hover:text-[var(--color-muted)]"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
