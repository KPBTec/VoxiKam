'use client'
import { ErrorBanner } from '@/components/ErrorBanner'
import { useEffect, useState } from 'react'
import { apiGet, apiPost, apiPut, apiDelete } from '@/lib/api'
import { Plus, Trash2, Pencil, Check, X, Hash } from 'lucide-react'

interface Prefix { id: number; prefix: string; destination: string; group_name: string; country: string | null; owner_customer_id: number | null; is_own: boolean | number }

const cardCls  = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'
const inputCls = 'bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm text-[var(--color-text)] focus-ring'
const labelCls = 'block text-xs text-[var(--color-text-2)] uppercase tracking-wider mb-1'
const emptyPfxForm = { prefix: '', destination: '', group_name: '', country: '' }

export default function ResellerPrefixesPage() {
  const [prefixes, setPrefixes] = useState<Prefix[]>([])
  const [error, setError]       = useState('')

  const [pfxForm, setPfxForm] = useState(emptyPfxForm)
  const [pfxSaving, setPfxSaving] = useState(false)
  const [pfxError, setPfxError] = useState('')
  const [editPfxId, setEditPfxId] = useState<number | null>(null)
  const [editPfxForm, setEditPfxForm] = useState(emptyPfxForm)

  async function loadPrefixes() {
    try { setPrefixes(await apiGet('/reseller/prefixes')) }
    catch (e: any) { setError(e.message) }
  }
  useEffect(() => { loadPrefixes() }, [])
  useEffect(() => { document.title = 'Mis prefijos · VoxiKam' }, [])

  async function createPrefix(e: React.FormEvent) {
    e.preventDefault(); setPfxError(''); setPfxSaving(true)
    try {
      await apiPost('/reseller/prefixes', { ...pfxForm, country: pfxForm.country || null })
      setPfxForm(emptyPfxForm)
      await loadPrefixes()
    } catch (e: any) { setPfxError(e.message) }
    finally { setPfxSaving(false) }
  }

  function startEditPfx(p: Prefix) {
    setEditPfxId(p.id)
    setEditPfxForm({ prefix: p.prefix, destination: p.destination, group_name: p.group_name, country: p.country ?? '' })
  }

  async function saveEditPfx(id: number) {
    setPfxError('')
    try {
      await apiPut(`/reseller/prefixes/${id}`, { ...editPfxForm, country: editPfxForm.country || null })
      setEditPfxId(null)
      await loadPrefixes()
    } catch (e: any) { setPfxError(e.message) }
  }

  async function delPrefix(id: number) {
    if (!confirm('¿Eliminar este prefijo?')) return
    setError('')
    try {
      await apiDelete(`/reseller/prefixes/${id}`)
      await loadPrefixes()
    } catch (e: any) { setError(e.message) }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-[var(--color-text)] flex items-center gap-2">
          <Hash size={20} className="text-brand-500" /> Mis prefijos
        </h1>
        <p className="text-sm text-[var(--color-text-2)] mt-0.5">
          {prefixes.filter(p => p.is_own).length} propios — {prefixes.length} disponibles en total (incluye los de la plataforma)
        </p>
      </div>

      {error && <ErrorBanner>{error}</ErrorBanner>}

      <div className={`${cardCls} p-5 space-y-4`}>
        <p className="text-xs text-[var(--color-muted)]">
          Podés crear tus propios destinos (como mini-admin) además de usar los que ya existen en la plataforma.
          Solo podés editar o borrar los que vos creaste.
        </p>
        <form onSubmit={createPrefix} className="flex gap-3 flex-wrap items-end">
          <div>
            <label htmlFor="rp-prefix" className={labelCls}>Prefijo</label>
            <input id="rp-prefix" required placeholder="ej: 5154" value={pfxForm.prefix}
              onChange={e => setPfxForm(f => ({...f, prefix: e.target.value}))}
              className={`w-28 ${inputCls} font-mono`} />
          </div>
          <div className="flex-1 min-w-40">
            <label htmlFor="rp-destination" className={labelCls}>Destino</label>
            <input id="rp-destination" required placeholder="ej: Fijo Arequipa" value={pfxForm.destination}
              onChange={e => setPfxForm(f => ({...f, destination: e.target.value}))}
              className={`w-full ${inputCls}`} />
          </div>
          <div className="w-40">
            <label htmlFor="rp-group" className={labelCls}>Grupo</label>
            <input id="rp-group" placeholder="ej: FIJO PROVINCIA" value={pfxForm.group_name}
              onChange={e => setPfxForm(f => ({...f, group_name: e.target.value}))}
              className={`w-full ${inputCls}`} />
          </div>
          <div>
            <label htmlFor="rp-country" className={labelCls}>País</label>
            <input id="rp-country" placeholder="PE" value={pfxForm.country}
              onChange={e => setPfxForm(f => ({...f, country: e.target.value.toUpperCase()}))}
              className={`w-16 ${inputCls} text-center`} maxLength={2} />
          </div>
          <button type="submit" disabled={pfxSaving}
            className="focus-ring flex items-center gap-1.5 px-4 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm rounded-lg">
            <Plus size={14}/> {pfxSaving ? 'Agregando…' : 'Agregar'}
          </button>
        </form>
        {pfxError && <p className="text-xs text-danger">{pfxError}</p>}

        <div className="overflow-x-auto rounded-lg border border-[var(--color-border)] max-h-[32rem] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-[var(--color-card)]">
              <tr className="text-xs text-[var(--color-text-2)] uppercase border-b border-[var(--color-border)]">
                <th className="px-4 py-2 text-left">Prefijo</th>
                <th className="px-4 py-2 text-left">Destino</th>
                <th className="px-4 py-2 text-left">Grupo</th>
                <th className="px-4 py-2 text-center">País</th>
                <th className="px-4 py-2"/>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              {prefixes.slice().sort((a, b) => a.prefix.localeCompare(b.prefix)).map(p => editPfxId === p.id ? (
                <tr key={p.id} className="bg-[var(--color-surface)]">
                  <td className="px-4 py-2">
                    <input aria-label="Prefijo" value={editPfxForm.prefix} onChange={e => setEditPfxForm(f => ({...f, prefix: e.target.value}))}
                      className={`w-24 ${inputCls} font-mono`} />
                  </td>
                  <td className="px-4 py-2">
                    <input aria-label="Destino" value={editPfxForm.destination} onChange={e => setEditPfxForm(f => ({...f, destination: e.target.value}))}
                      className={`w-full ${inputCls}`} />
                  </td>
                  <td className="px-4 py-2">
                    <input aria-label="Grupo" value={editPfxForm.group_name} onChange={e => setEditPfxForm(f => ({...f, group_name: e.target.value}))}
                      className={`w-full ${inputCls}`} />
                  </td>
                  <td className="px-4 py-2 text-center">
                    <input aria-label="País" value={editPfxForm.country} onChange={e => setEditPfxForm(f => ({...f, country: e.target.value.toUpperCase()}))}
                      className={`w-16 ${inputCls} text-center`} maxLength={2} />
                  </td>
                  <td className="px-4 py-2 text-right">
                    <div className="flex justify-end gap-2">
                      <button onClick={() => saveEditPfx(p.id)} aria-label="Guardar" className="focus-ring text-success hover:opacity-80"><Check size={15}/></button>
                      <button onClick={() => setEditPfxId(null)} aria-label="Cancelar edición" className="focus-ring text-[var(--color-muted)] hover:text-[var(--color-text)]"><X size={15}/></button>
                    </div>
                  </td>
                </tr>
              ) : (
                <tr key={p.id} className="hover:bg-white/2">
                  <td className="px-4 py-2 font-mono text-brand-400">{p.prefix}</td>
                  <td className="px-4 py-2 text-[var(--color-text)]">{p.destination}</td>
                  <td className="px-4 py-2 text-[var(--color-text-2)]">
                    {p.group_name || '—'}
                    {!!p.is_own && <span className="ml-2 px-1.5 py-0.5 rounded text-[10px] bg-brand-600/20 text-brand-400">tuyo</span>}
                  </td>
                  <td className="px-4 py-2 text-center text-[var(--color-muted)]">{p.country ?? '—'}</td>
                  <td className="px-4 py-2 text-right">
                    {!!p.is_own && (
                      <div className="flex justify-end gap-1">
                        <button onClick={() => startEditPfx(p)} aria-label="Editar" className="focus-ring p-1 text-[var(--color-muted)] hover:text-brand-400"><Pencil size={13}/></button>
                        <button onClick={() => delPrefix(p.id)} aria-label="Eliminar prefijo" className="focus-ring p-1 text-[var(--color-muted)] hover:text-danger"><Trash2 size={13}/></button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
              {prefixes.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-6 text-center text-[var(--color-muted)] text-sm">Sin prefijos</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
