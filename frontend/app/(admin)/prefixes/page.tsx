'use client'
import { useEffect, useState } from 'react'
import { apiGet, apiPost, apiPut, apiDelete } from '@/lib/api'
import { Plus, Trash2, Pencil, Check, X, Hash } from 'lucide-react'
import { ErrorBanner } from '@/components/ErrorBanner'

interface Prefix { id: number; prefix: string; destination: string; group_name: string; country: string }
interface Group  { group_name: string; prefix_count: number }
interface Area   { id: number; name: string; country_code: string }
interface Country { code: string; name: string }

const card  = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'
const input = 'bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-500'
const lbl   = 'block text-xs text-[var(--color-text-2)] uppercase tracking-wider mb-1'

const GROUP_COLORS: Record<string, string> = {
  'FIJO LIMA':      'bg-info-900/50 text-info-300',
  'FIJO PROVINCIA': 'bg-purple-900/30 text-purple-300',
  'MOVILES':        'bg-amber-900/30 text-amber-300',
}
function groupBadge(g: string) {
  return <span className={`px-2 py-0.5 rounded text-xs font-medium ${GROUP_COLORS[g] ?? 'bg-zinc-700 text-zinc-300'}`}>{g || '—'}</span>
}

export default function PrefixesPage() {
  const [prefixes, setPrefixes] = useState<Prefix[]>([])
  const [groups, setGroups]     = useState<Group[]>([])
  const [areas, setAreas]       = useState<Area[]>([])
  const [countries, setCountries] = useState<Country[]>([])
  const [error, setError]       = useState('')
  const [loading, setLoading]   = useState(true)

  // Editar prefijo
  const [editPfxId, setEditPfxId] = useState<number | null>(null)
  const [editPfxForm, setEditPfxForm] = useState({ prefix: '', destination: '', group_name: '', country: '' })
  const [editPfxSaving, setEditPfxSaving] = useState(false)

  // Nuevo prefijo
  const [pfxForm, setPfxForm] = useState({ prefix: '', destination: '', group_name: '', country: 'PE' })
  const [pfxSaving, setPfxSaving] = useState(false)

  const loadPfx    = () => apiGet('/admin/rates/prefixes').then(setPrefixes).catch((e: any) => setError(e.message)).finally(() => setLoading(false))
  const loadGroups = () => apiGet('/admin/rates/groups').then(setGroups).catch((e: any) => setError(e.message))
  const loadAreas  = () => apiGet('/admin/areas').then(setAreas).catch((e: any) => setError(e.message))
  const loadCountries = () => apiGet('/admin/areas/countries').then(setCountries).catch((e: any) => setError(e.message))

  useEffect(() => { loadPfx(); loadGroups(); loadAreas(); loadCountries() }, [])

  async function addPrefix(e: React.FormEvent) {
    e.preventDefault(); setPfxSaving(true)
    try {
      await apiPost('/admin/rates/prefixes', pfxForm)
      setPfxForm({ prefix: '', destination: '', group_name: '', country: 'PE' })
      loadPfx(); loadGroups()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al crear el prefijo')
    } finally { setPfxSaving(false) }
  }

  async function delPrefix(id: number) {
    if (!confirm('¿Eliminar este prefijo?')) return
    try {
      await apiDelete(`/admin/rates/prefixes/${id}`); loadPfx(); loadGroups()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al eliminar')
    }
  }

  function startEditPfx(p: Prefix) {
    setEditPfxId(p.id)
    setEditPfxForm({ prefix: p.prefix, destination: p.destination, group_name: p.group_name, country: p.country || 'PE' })
  }

  async function saveEditPfx(id: number) {
    setEditPfxSaving(true)
    try {
      await apiPut(`/admin/rates/prefixes/${id}`, editPfxForm)
      setEditPfxId(null)
      await Promise.all([loadPfx(), loadGroups()])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al guardar')
    } finally { setEditPfxSaving(false) }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><Hash size={22} className="text-brand-500" /> Prefijos de destino</h1>
        <p className="text-sm text-[var(--color-muted)] mt-1">
          Catálogo global de prefijos E.164 → destino, con longest-prefix-match activo. Es el
          insumo que usan los planes de venta en <span className="text-[var(--color-text-2)]">Tarifas</span> para
          asignar precio por destino o por grupo.
        </p>
      </div>

      {error && <ErrorBanner>{error}</ErrorBanner>}

      <div className={`${card} p-5 space-y-4`}>
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">Nuevo prefijo</h2>
          <span className="text-xs text-[var(--color-muted)]">{prefixes.length} prefijos — {groups.length} grupos</span>
        </div>

        <form onSubmit={addPrefix} className="flex gap-3 flex-wrap items-end">
          <div>
            <label className={lbl}>Prefijo E.164</label>
            <input required placeholder="ej: 5154" value={pfxForm.prefix}
              onChange={e => setPfxForm(f => ({...f, prefix: e.target.value}))}
              className={`w-28 ${input} font-mono`} />
          </div>
          <div className="flex-1 min-w-40">
            <label className={lbl}>Descripción</label>
            <input required placeholder="ej: Fijo Arequipa"
              value={pfxForm.destination}
              onChange={e => setPfxForm(f => ({...f, destination: e.target.value}))}
              className={`w-full ${input}`} />
          </div>
          <div className="w-40">
            <label className={lbl}>País</label>
            {/* Elegir país primero filtra qué áreas se ofrecen abajo — antes el
                selector de área mezclaba áreas de todos los países sin distinción. */}
            <select value={pfxForm.country}
              onChange={e => setPfxForm(f => ({
                ...f, country: e.target.value,
                group_name: areas.some(a => a.name === f.group_name && a.country_code === e.target.value) ? f.group_name : '',
              }))}
              className={`w-full ${input}`}>
              {countries.map(c => <option key={c.code} value={c.code}>{c.name}</option>)}
            </select>
          </div>
          <div className="w-48">
            <label className={lbl}>Grupo de prefijos</label>
            {/* Sale de /admin/areas (el registro formal), no de /admin/rates/groups
                — ese último solo lista grupos que YA tienen algún prefijo, así que
                un área recién creada (0 prefijos) nunca aparecería como opción. */}
            <select value={pfxForm.group_name}
              onChange={e => setPfxForm(f => ({...f, group_name: e.target.value}))}
              className={`w-full ${input}`}>
              <option value="">Sin grupo</option>
              {areas.filter(a => a.country_code === pfxForm.country).map(a => <option key={a.id} value={a.name}>{a.name}</option>)}
            </select>
          </div>
          <button type="submit" disabled={pfxSaving}
            className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm px-4 py-2 rounded-lg transition-colors">
            <Plus size={15}/> {pfxSaving ? 'Agregando…' : 'Agregar'}
          </button>
        </form>

        <div className="overflow-x-auto rounded-lg border border-[var(--color-border)]">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-[var(--color-text-2)] uppercase border-b border-[var(--color-border)] bg-[var(--color-surface)]">
                <th className="px-4 py-2 text-left">Prefijo</th>
                <th className="px-4 py-2 text-left">Destino</th>
                <th className="px-4 py-2 text-left">Grupo</th>
                <th className="px-4 py-2 text-center">País</th>
                <th className="px-4 py-2"/>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              {prefixes.map(p => editPfxId === p.id ? (
                <tr key={p.id} className="bg-white/2">
                  <td className="px-4 py-2">
                    <input value={editPfxForm.prefix} onChange={e => setEditPfxForm(f => ({...f, prefix: e.target.value}))}
                      className={`w-24 ${input} font-mono`} />
                  </td>
                  <td className="px-4 py-2">
                    <input value={editPfxForm.destination} onChange={e => setEditPfxForm(f => ({...f, destination: e.target.value}))}
                      className={`w-full ${input}`} />
                  </td>
                  <td className="px-4 py-2">
                    <select value={editPfxForm.group_name} onChange={e => setEditPfxForm(f => ({...f, group_name: e.target.value}))}
                      className={`w-full ${input}`}>
                      <option value="">Sin grupo</option>
                      {areas.filter(a => a.country_code === editPfxForm.country).map(a => <option key={a.id} value={a.name}>{a.name}</option>)}
                    </select>
                  </td>
                  <td className="px-4 py-2 text-center">
                    <select value={editPfxForm.country}
                      onChange={e => setEditPfxForm(f => ({
                        ...f, country: e.target.value,
                        group_name: areas.some(a => a.name === f.group_name && a.country_code === e.target.value) ? f.group_name : '',
                      }))}
                      className={`w-20 ${input} text-center`}>
                      {countries.map(c => <option key={c.code} value={c.code}>{c.code}</option>)}
                    </select>
                  </td>
                  <td className="px-4 py-2 text-right">
                    <div className="flex justify-end gap-2">
                      <button onClick={() => saveEditPfx(p.id)} disabled={editPfxSaving} className="text-green-400 hover:text-green-300"><Check size={15}/></button>
                      <button onClick={() => setEditPfxId(null)} className="text-[var(--color-muted)] hover:text-[var(--color-text)]"><X size={15}/></button>
                    </div>
                  </td>
                </tr>
              ) : (
                <tr key={p.id} className="hover:bg-white/2">
                  <td className="px-4 py-2 font-mono text-brand-400">{p.prefix}</td>
                  <td className="px-4 py-2">{p.destination}</td>
                  <td className="px-4 py-2">{groupBadge(p.group_name)}</td>
                  <td className="px-4 py-2 text-center text-[var(--color-muted)]">{p.country}</td>
                  <td className="px-4 py-2 text-right">
                    <div className="flex justify-end gap-1">
                      <button onClick={() => startEditPfx(p)}
                        className="p-1 text-[var(--color-muted)] hover:text-brand-400 transition-colors">
                        <Pencil size={14}/>
                      </button>
                      <button onClick={() => delPrefix(p.id)}
                        className="p-1 text-[var(--color-muted)] hover:text-red-400 transition-colors">
                        <Trash2 size={14}/>
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {loading && prefixes.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-6 text-center text-[var(--color-muted)] text-sm">Cargando...</td></tr>
              )}
              {!loading && prefixes.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-6 text-center text-[var(--color-muted)] text-sm">Sin prefijos</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
