'use client'
import { ErrorBanner } from '@/components/ErrorBanner'
import { useEffect, useState } from 'react'
import { apiGet, apiPost, apiPut, apiDelete } from '@/lib/api'
import { Plus, Trash2, ArrowLeft, Shuffle } from 'lucide-react'
import { ClickableRow } from '@/components/ClickableRow'

interface CarrierGroup {
  id: number; name: string; algorithm: 'priority' | 'round_robin' | 'percent'
  owner_customer_id: number | null; created_at: string; updated_at: string
  member_count: number
}
interface GroupMember {
  carrier_id: number; priority: number; weight: number | null
  name: string; host: string; status: string
}
interface UsedByEntry { customer_id: number; customer_name: string; ref: 'principal' | 'campaña'; label: string | null }
interface GroupDetail extends CarrierGroup { members: GroupMember[]; used_by: UsedByEntry[] }
interface AssignableCarrier { id: number; name: string; status: string; is_own: boolean | number; rate_count: number }
interface SubCustomerOpt { id: number; name: string; techprefix: string }

const cardCls  = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'
const inputCls = 'w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm text-[var(--color-text)] focus:outline-none focus:border-brand-500'
const labelCls = 'block text-xs text-[var(--color-text-2)] uppercase tracking-wider mb-1'

const ALGO_LABELS: Record<string, string> = {
  priority: 'Prioridad (failover)',
  round_robin: 'Round robin',
  percent: 'Porcentaje (%)',
}

const EMPTY_FORM = { name: '', algorithm: 'priority' as CarrierGroup['algorithm'] }

export default function ResellerCarrierGroupsPage() {
  const [groups, setGroups]     = useState<CarrierGroup[]>([])
  const [carriers, setCarriers] = useState<AssignableCarrier[]>([])
  const [subCustomers, setSubCustomers] = useState<SubCustomerOpt[]>([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState('')

  const [showCreate, setShowCreate] = useState(false)
  const [createForm, setCreateForm] = useState(EMPTY_FORM)
  const [creating, setCreating]     = useState(false)

  const [selected, setSelected] = useState<GroupDetail | null>(null)
  const [editForm, setEditForm] = useState(EMPTY_FORM)
  const [saving, setSaving]     = useState(false)

  const [newCarrierId, setNewCarrierId] = useState('')
  const [newPriority, setNewPriority]   = useState('10')
  const [newWeight, setNewWeight]       = useState('')
  const [addingMember, setAddingMember] = useState(false)

  // Habilitar el grupo para un sub-cliente — reemplaza lo que antes hacía el
  // bloque "Grupos habilitados" del lado del sub-cliente.
  const [subCustomerToEnable, setSubCustomerToEnable] = useState('')
  const [enablingForSubCustomer, setEnablingForSubCustomer] = useState(false)
  const [enableMsg, setEnableMsg] = useState('')

  const load = () =>
    apiGet('/reseller/carrier-groups').then(setGroups).catch((e: any) => setError(e.message)).finally(() => setLoading(false))

  useEffect(() => {
    load()
    apiGet('/reseller/carriers/assignable').then(setCarriers).catch(() => {})
    apiGet('/reseller/sub-customers').then(setSubCustomers).catch(() => {})
  }, [])

  async function openDetail(id: number) {
    setError('')
    try {
      const d = await apiGet(`/reseller/carrier-groups/${id}`)
      setSelected(d)
      setEditForm({ name: d.name, algorithm: d.algorithm })
      setNewCarrierId(''); setNewPriority('10'); setNewWeight('')
      setSubCustomerToEnable(''); setEnableMsg('')
    } catch (e: any) { setError(e.message) }
  }

  async function reloadDetail() {
    if (!selected) return
    try { setSelected(await apiGet(`/reseller/carrier-groups/${selected.id}`)) }
    catch (e: any) { setError(e.message) }
  }

  async function createGroup(e: React.FormEvent) {
    e.preventDefault(); setCreating(true); setError('')
    try {
      await apiPost('/reseller/carrier-groups', createForm)
      setCreateForm(EMPTY_FORM); setShowCreate(false)
      load()
    } catch (e: any) { setError(e.message) }
    finally { setCreating(false) }
  }

  async function saveEdit(e: React.FormEvent) {
    e.preventDefault(); if (!selected) return
    setSaving(true); setError('')
    try {
      await apiPut(`/reseller/carrier-groups/${selected.id}`, editForm)
      await load(); await reloadDetail()
    } catch (e: any) { setError(e.message) }
    finally { setSaving(false) }
  }

  async function deleteGroup(id: number) {
    if (!confirm('¿Eliminar este grupo de ruteo?')) return
    try {
      await apiDelete(`/reseller/carrier-groups/${id}`)
      if (selected?.id === id) setSelected(null)
      load()
    } catch (e: any) { alert(e.message) }
  }

  async function addMember(e: React.FormEvent) {
    e.preventDefault(); if (!selected || !newCarrierId) return
    setAddingMember(true); setError('')
    try {
      await apiPost(`/reseller/carrier-groups/${selected.id}/members`, {
        carrier_id: +newCarrierId, priority: +newPriority,
        weight: newWeight ? +newWeight : null,
      })
      setNewCarrierId(''); setNewWeight('')
      await reloadDetail(); await load()
    } catch (e: any) { setError(e.message) }
    finally { setAddingMember(false) }
  }

  async function removeMember(carrierId: number) {
    if (!selected) return
    try {
      await apiDelete(`/reseller/carrier-groups/${selected.id}/members/${carrierId}`)
      await reloadDetail(); await load()
    } catch (e: any) { alert(e.message) }
  }

  async function enableForSubCustomer(e: React.FormEvent) {
    e.preventDefault(); if (!selected || !subCustomerToEnable) return
    setEnablingForSubCustomer(true); setError(''); setEnableMsg('')
    try {
      await apiPost(`/reseller/sub-customers/${subCustomerToEnable}/carrier-groups`, { group_id: selected.id })
      const cust = subCustomers.find(c => c.id === +subCustomerToEnable)
      setEnableMsg(`Habilitado para ${cust?.name ?? 'el sub-cliente'} — andá a su ficha para seleccionarlo como grupo activo si corresponde.`)
      setSubCustomerToEnable('')
      await reloadDetail()
    } catch (e: any) { setError(e.message) }
    finally { setEnablingForSubCustomer(false) }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-[var(--color-text)] flex items-center gap-2">
            <Shuffle size={20} className="text-brand-500" /> Grupos de ruteo
          </h1>
          <p className="text-sm text-[var(--color-text-2)] mt-0.5">
            Tus propios grupos de carriers — cada prefijo de tus sub-clientes elige a qué grupo rutea.
          </p>
        </div>
        {!selected && (
          <button onClick={() => { setShowCreate(v => !v); setCreateForm(EMPTY_FORM); setError('') }}
            className="flex items-center gap-1.5 px-4 py-2 bg-brand-600 hover:bg-brand-500 text-white text-sm rounded-lg">
            <Plus size={15} /> Nuevo grupo
          </button>
        )}
      </div>

      {error && <ErrorBanner>{error}</ErrorBanner>}

      {showCreate && !selected && (
        <form onSubmit={createGroup} className={`${cardCls} p-6 space-y-4`}>
          <h2 className="font-medium text-[var(--color-text)]">Nuevo grupo</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className={labelCls}>Nombre</label>
              <input required className={inputCls} placeholder="ej: Fallback Movistar/Claro"
                value={createForm.name} onChange={e => setCreateForm(f => ({ ...f, name: e.target.value }))} />
            </div>
            <div>
              <label className={labelCls}>Algoritmo</label>
              <select className={inputCls} value={createForm.algorithm}
                onChange={e => setCreateForm(f => ({ ...f, algorithm: e.target.value as CarrierGroup['algorithm'] }))}>
                {Object.entries(ALGO_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>
          </div>
          <div className="flex gap-3">
            <button type="submit" disabled={creating}
              className="px-4 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm rounded-lg">
              {creating ? 'Creando…' : 'Crear grupo'}
            </button>
            <button type="button" onClick={() => setShowCreate(false)}
              className="px-4 py-2 text-sm text-[var(--color-muted)] hover:text-[var(--color-text)]">Cancelar</button>
          </div>
        </form>
      )}

      <div className={`${cardCls} overflow-x-auto`}>
        {selected ? (
          <div>
            <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--color-border)]">
              <button onClick={() => setSelected(null)} className="flex items-center gap-1.5 text-sm text-[var(--color-text-2)] hover:text-[var(--color-text)]">
                <ArrowLeft size={15} /> Volver a grupos
              </button>
              <span className="px-3 py-1 rounded-full text-xs font-medium bg-brand-600/20 text-brand-400 border border-brand-700/40">
                {ALGO_LABELS[selected.algorithm]}
              </span>
            </div>

            <div className="p-5 grid grid-cols-1 lg:grid-cols-2 gap-6">
              <form onSubmit={saveEdit} className="space-y-3">
                <p className="text-xs text-[var(--color-muted)] uppercase tracking-wider">Configuración</p>
                <div>
                  <label className={labelCls}>Nombre</label>
                  <input required className={inputCls} value={editForm.name}
                    onChange={e => setEditForm(f => ({ ...f, name: e.target.value }))} />
                </div>
                <div>
                  <label className={labelCls}>Algoritmo</label>
                  <select className={inputCls} value={editForm.algorithm}
                    onChange={e => setEditForm(f => ({ ...f, algorithm: e.target.value as CarrierGroup['algorithm'] }))}>
                    {Object.entries(ALGO_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                </div>
                <div className="flex gap-3">
                  <button type="submit" disabled={saving}
                    className="px-4 py-1.5 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm rounded-lg">
                    {saving ? 'Guardando…' : 'Guardar cambios'}
                  </button>
                  <button type="button" onClick={() => deleteGroup(selected.id)}
                    className="px-4 py-1.5 text-sm text-red-400 hover:text-red-300">Eliminar grupo</button>
                </div>
              </form>

              <div className="space-y-3">
                <p className="text-xs text-[var(--color-muted)] uppercase tracking-wider">Carriers miembros</p>
                {selected.algorithm === 'percent' && (
                  <p className="text-xs text-[var(--color-muted)]">
                    El tráfico se reparte entre los miembros según su %. Un carrier sin % asignado se reparte parejo (peso 1).
                  </p>
                )}
                <form onSubmit={addMember} className="flex gap-2 items-end flex-wrap">
                  <div className="flex-1 min-w-40">
                    <select required value={newCarrierId} onChange={e => setNewCarrierId(e.target.value)} className={inputCls}>
                      <option value="">Seleccionar carrier…</option>
                      {carriers.filter(c => !selected.members.some(m => m.carrier_id === c.id)).map(c => (
                        <option key={c.id} value={c.id}>
                          {c.name} {c.is_own ? '(tuyo)' : '(plataforma)'}{c.rate_count === 0 ? ' ⚠ sin tarifas' : ''}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <input type="number" min={1} max={100} value={newPriority}
                      onChange={e => setNewPriority(e.target.value)}
                      placeholder="Prio" title="Prioridad (1=mayor)"
                      className="w-20 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm text-center focus:outline-none focus:border-brand-500" />
                  </div>
                  {selected.algorithm === 'percent' && (
                    <div>
                      <input type="number" min={1} max={100} value={newWeight}
                        onChange={e => setNewWeight(e.target.value)}
                        placeholder="%" title="Peso relativo (%)"
                        className="w-20 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm text-center focus:outline-none focus:border-brand-500" />
                    </div>
                  )}
                  <button type="submit" disabled={addingMember || !newCarrierId}
                    className="px-3 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm rounded-lg">
                    {addingMember ? 'Agregando…' : 'Agregar'}
                  </button>
                </form>

                <div className="divide-y divide-[var(--color-border)] rounded-lg border border-[var(--color-border)] overflow-hidden">
                  {selected.members
                    .slice()
                    .sort((a, b) => a.priority - b.priority)
                    .map(m => (
                    <div key={m.carrier_id} className="flex items-center justify-between px-3 py-2 text-sm">
                      <span className="text-[var(--color-text)]">
                        {m.name}
                        <span className="ml-2 font-mono text-xs text-[var(--color-text-2)]">{m.host}</span>
                        <span className="ml-2 text-[var(--color-muted)] text-xs">
                          {selected.algorithm === 'percent' ? `${m.weight ?? 1}%` : `prio ${m.priority}`}
                        </span>
                        {m.status !== 'active' && (
                          <span className="ml-2 px-1.5 py-0.5 rounded text-[10px] bg-zinc-700 text-zinc-400">inactivo</span>
                        )}
                      </span>
                      <button onClick={() => removeMember(m.carrier_id)} aria-label="Quitar del grupo" className="text-[var(--color-muted)] hover:text-red-400">
                        <Trash2 size={13} />
                      </button>
                    </div>
                  ))}
                  {selected.members.length === 0 && (
                    <p className="px-3 py-4 text-center text-[var(--color-muted)] text-xs">Sin miembros — este grupo no enrutará llamadas.</p>
                  )}
                </div>
              </div>
            </div>

            {/* Usado por — quién depende de este grupo hoy, para saber si se puede borrar sin romper nada */}
            <div className="px-5 pb-5">
              <div className="rounded-lg border border-[var(--color-border)] p-4 space-y-3">
                <p className="text-xs text-[var(--color-muted)] uppercase tracking-wider">Usado por</p>
                {selected.used_by.length === 0 ? (
                  <p className="text-sm text-[var(--color-text-2)]">
                    Ningún cliente lo está usando todavía — se puede borrar sin romper nada.
                  </p>
                ) : (
                  <ul className="space-y-1.5">
                    {selected.used_by.map((u, i) => (
                      <li key={`${u.customer_id}-${i}`} className="text-sm text-[var(--color-text)] flex items-center gap-2">
                        <span className="w-1.5 h-1.5 rounded-full bg-brand-500 flex-shrink-0" />
                        {u.customer_name}
                        <span className="text-[var(--color-muted)]">
                          — {u.ref === 'principal' ? 'prefijo principal' : `campaña${u.label ? ` ${u.label}` : ''}`}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>

            {/* Habilitar para un sub-cliente — reemplaza el bloque "Grupos habilitados" que
                antes vivía en la ficha del sub-cliente. El sub-cliente solo selecciona entre
                sus grupos ya habilitados; habilitar/deshabilitar se gestiona acá. */}
            <div className="px-5 pb-5">
              <div className="rounded-lg border border-[var(--color-border)] p-4 space-y-3">
                <div>
                  <p className="text-xs text-[var(--color-muted)] uppercase tracking-wider">Habilitar para un sub-cliente</p>
                  <p className="text-xs text-[var(--color-muted)] mt-0.5">
                    Le da acceso a este grupo a uno de tus sub-clientes — después, desde su ficha,
                    elegís si lo usa como grupo activo del prefijo principal o de algún prefijo de campaña.
                  </p>
                </div>
                {enableMsg && <p className="text-xs text-green-400">{enableMsg}</p>}
                <form onSubmit={enableForSubCustomer} className="flex gap-2 items-end flex-wrap">
                  <div className="flex-1 min-w-48">
                    <select required value={subCustomerToEnable} onChange={e => setSubCustomerToEnable(e.target.value)} className={inputCls}>
                      <option value="">Seleccionar sub-cliente…</option>
                      {subCustomers
                        .filter(c => !selected.used_by.some(u => u.customer_id === c.id))
                        .map(c => <option key={c.id} value={c.id}>{c.name} — {c.techprefix}</option>)}
                    </select>
                  </div>
                  <button type="submit" disabled={enablingForSubCustomer || !subCustomerToEnable}
                    className="px-3 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm rounded-lg">
                    {enablingForSubCustomer ? 'Habilitando…' : 'Habilitar'}
                  </button>
                </form>
              </div>
            </div>
          </div>
        ) : loading ? (
          <p className="p-8 text-center text-[var(--color-text-2)] text-sm">Cargando…</p>
        ) : groups.length === 0 ? (
          <p className="p-10 text-center text-[var(--color-muted)] text-sm">Sin grupos de ruteo todavía — creá el primero arriba.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-[var(--color-text-2)] uppercase border-b border-[var(--color-border)]">
                <th className="px-6 py-3 text-left">Nombre</th>
                <th className="px-6 py-3 text-left">Algoritmo</th>
                <th className="px-6 py-3 text-center">Miembros</th>
                <th className="px-6 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              {groups.map(g => (
                <ClickableRow key={g.id} onActivate={() => openDetail(g.id)} className="hover:bg-white/2 cursor-pointer">
                  <td className="px-6 py-3 font-medium text-[var(--color-text)]">{g.name}</td>
                  <td className="px-6 py-3 text-[var(--color-text-2)]">{ALGO_LABELS[g.algorithm]}</td>
                  <td className="px-6 py-3 text-center">{g.member_count}</td>
                  <td className="px-6 py-3 text-right">
                    <button onClick={e => { e.stopPropagation(); deleteGroup(g.id) }}
                      className="text-xs text-red-400 hover:text-red-300">Eliminar</button>
                  </td>
                </ClickableRow>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
