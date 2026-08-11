'use client'
import { useEffect, useState } from 'react'
import { apiGet, apiPost, apiPut, apiDelete } from '@/lib/api'
import { Plus, Trash2, ArrowLeft, Shuffle, AlertTriangle } from 'lucide-react'
import { StatusBadge } from '@/components/StatusBadge'
import { ErrorBanner } from '@/components/ErrorBanner'
import { ClickableRow } from '@/components/ClickableRow'
import { Button } from '@/components/Button'
import { Card } from '@/components/Card'

interface CarrierGroup {
  id: number; name: string; algorithm: 'priority' | 'round_robin' | 'percent'
  owner_customer_id: number | null; created_at: string; updated_at: string
  member_count: number; used_by_count: number
}
interface GroupMember {
  carrier_id: number; priority: number; weight: number | null
  name: string; host: string; status: string
}
interface UsedByEntry { customer_id: number; customer_name: string; ref: 'principal' | 'campaña'; label: string | null }
interface EnabledForEntry { customer_id: number; customer_name: string; display_label: string }
interface GroupDetail extends CarrierGroup { members: GroupMember[]; used_by: UsedByEntry[]; enabled_for: EnabledForEntry[] }
interface CarrierOpt { id: number; name: string; host: string; status: string }
interface CustomerOpt { id: number; name: string; techprefix: string }

const inputCls = 'w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm text-[var(--color-text)] focus:outline-none focus:border-brand-500'
const labelCls = 'block text-xs text-[var(--color-text-2)] uppercase tracking-wider mb-1'

const ALGO_LABELS: Record<string, string> = {
  priority: 'Prioridad (failover)',
  round_robin: 'Round robin',
  percent: 'Porcentaje (%)',
}

const EMPTY_FORM = { name: '', algorithm: 'priority' as CarrierGroup['algorithm'] }

export default function CarrierGroupsPage() {
  useEffect(() => { document.title = 'Grupos de ruteo · VoxiKam' }, [])

  const [groups, setGroups]     = useState<CarrierGroup[]>([])
  const [carriers, setCarriers] = useState<CarrierOpt[]>([])
  const [customers, setCustomers] = useState<CustomerOpt[]>([])
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

  // Habilitar el grupo para un cliente — reemplaza lo que antes hacía el
  // bloque "Grupos habilitados" del lado del cliente (ver customers/[id]/page.tsx).
  const [customerToEnable, setCustomerToEnable] = useState('')
  const [enablingForCustomer, setEnablingForCustomer] = useState(false)
  const [enableMsg, setEnableMsg] = useState('')

  const load = () =>
    apiGet('/admin/carrier-groups').then(setGroups).catch((e: any) => setError(e.message)).finally(() => setLoading(false))

  useEffect(() => {
    load()
    apiGet('/admin/carriers').then(setCarriers).catch(() => {})
    apiGet('/admin/customers?exclude_resellers=true').then(setCustomers).catch(() => {})
  }, [])

  async function openDetail(id: number) {
    setError('')
    try {
      const d = await apiGet(`/admin/carrier-groups/${id}`)
      setSelected(d)
      setEditForm({ name: d.name, algorithm: d.algorithm })
      setNewCarrierId(''); setNewPriority('10'); setNewWeight('')
      setCustomerToEnable(''); setEnableMsg('')
    } catch (e: any) { setError(e.message) }
  }

  async function reloadDetail() {
    if (!selected) return
    try { setSelected(await apiGet(`/admin/carrier-groups/${selected.id}`)) }
    catch (e: any) { setError(e.message) }
  }

  async function createGroup(e: React.FormEvent) {
    e.preventDefault(); setCreating(true); setError('')
    try {
      await apiPost('/admin/carrier-groups', createForm)
      setCreateForm(EMPTY_FORM); setShowCreate(false)
      load()
    } catch (e: any) { setError(e.message) }
    finally { setCreating(false) }
  }

  async function saveEdit(e: React.FormEvent) {
    e.preventDefault(); if (!selected) return
    setSaving(true); setError('')
    try {
      await apiPut(`/admin/carrier-groups/${selected.id}`, editForm)
      await load(); await reloadDetail()
    } catch (e: any) { setError(e.message) }
    finally { setSaving(false) }
  }

  async function deleteGroup(id: number) {
    if (!confirm('¿Eliminar este grupo de ruteo?')) return
    try {
      await apiDelete(`/admin/carrier-groups/${id}`)
      if (selected?.id === id) setSelected(null)
      load()
    } catch (e: any) { setError(e.message) }
  }

  async function addMember(e: React.FormEvent) {
    e.preventDefault(); if (!selected || !newCarrierId) return
    setAddingMember(true); setError('')
    try {
      await apiPost(`/admin/carrier-groups/${selected.id}/members`, {
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
      await apiDelete(`/admin/carrier-groups/${selected.id}/members/${carrierId}`)
      await reloadDetail(); await load()
    } catch (e: any) { setError(e.message) }
  }

  async function enableForCustomer(e: React.FormEvent) {
    e.preventDefault(); if (!selected || !customerToEnable) return
    setEnablingForCustomer(true); setError(''); setEnableMsg('')
    try {
      await apiPost(`/admin/customers/${customerToEnable}/carrier-groups`, { group_id: selected.id })
      const cust = customers.find(c => c.id === +customerToEnable)
      setEnableMsg(`Habilitado para ${cust?.name ?? 'el cliente'} — andá a su ficha para seleccionarlo como grupo activo si corresponde.`)
      setCustomerToEnable('')
      await reloadDetail()
    } catch (e: any) { setError(e.message) }
    finally { setEnablingForCustomer(false) }
  }

  async function removeAccess(customerId: number) {
    if (!selected) return
    try {
      await apiDelete(`/admin/customers/${customerId}/carrier-groups/${selected.id}`)
      await reloadDetail()
    } catch (e: any) { setError(e.message) }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-[var(--color-text)] flex items-center gap-2">
            <Shuffle size={20} className="text-brand-500" /> Grupos de ruteo
          </h1>
          <p className="text-sm text-[var(--color-text-2)] mt-0.5">
            Conjuntos de carriers con un algoritmo de reparto (prioridad, round robin o porcentaje) —
            cada prefijo de un cliente elige a qué grupo rutea.
          </p>
        </div>
        {!selected && (
          <Button onClick={() => { setShowCreate(v => !v); setCreateForm(EMPTY_FORM); setError('') }} icon={<Plus size={15} />}>
            Nuevo grupo
          </Button>
        )}
      </div>

      {error && <ErrorBanner>{error}</ErrorBanner>}

      {showCreate && !selected && (
        <form onSubmit={createGroup} className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-6 space-y-4">
          <h2 className="font-medium text-[var(--color-text)]">Nuevo grupo</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label htmlFor="cg-new-name" className={labelCls}>Nombre</label>
              <input id="cg-new-name" required className={inputCls} placeholder="ej: Fallback Movistar/Claro"
                value={createForm.name} onChange={e => setCreateForm(f => ({ ...f, name: e.target.value }))} />
            </div>
            <div>
              <label htmlFor="cg-new-algorithm" className={labelCls}>Algoritmo</label>
              <select id="cg-new-algorithm" className={inputCls} value={createForm.algorithm}
                onChange={e => setCreateForm(f => ({ ...f, algorithm: e.target.value as CarrierGroup['algorithm'] }))}>
                {Object.entries(ALGO_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>
          </div>
          <div className="flex gap-3">
            <Button type="submit" disabled={creating}>
              {creating ? 'Creando…' : 'Crear grupo'}
            </Button>
            <Button type="button" variant="ghost" onClick={() => setShowCreate(false)}>Cancelar</Button>
          </div>
        </form>
      )}

      <Card className="overflow-x-auto">
        {selected ? (
          <div>
            <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--color-border)]">
              <button onClick={() => setSelected(null)} className="focus-ring flex items-center gap-1.5 text-sm text-[var(--color-text-2)] hover:text-[var(--color-text)]">
                <ArrowLeft size={15} /> Volver a grupos
              </button>
              <StatusBadge variant="brand" bordered>{ALGO_LABELS[selected.algorithm]}</StatusBadge>
            </div>

            <div className="p-5 grid grid-cols-1 lg:grid-cols-2 gap-6">
              <form onSubmit={saveEdit} className="space-y-3">
                <p className="text-xs text-[var(--color-muted)] uppercase tracking-wider">Configuración</p>
                <div>
                  <label htmlFor="cg-edit-name" className={labelCls}>Nombre</label>
                  <input id="cg-edit-name" required className={inputCls} value={editForm.name}
                    onChange={e => setEditForm(f => ({ ...f, name: e.target.value }))} />
                </div>
                <div>
                  <label htmlFor="cg-edit-algorithm" className={labelCls}>Algoritmo</label>
                  <select id="cg-edit-algorithm" className={inputCls} value={editForm.algorithm}
                    onChange={e => setEditForm(f => ({ ...f, algorithm: e.target.value as CarrierGroup['algorithm'] }))}>
                    {Object.entries(ALGO_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                </div>
                <div className="flex gap-3">
                  <Button type="submit" disabled={saving}>
                    {saving ? 'Guardando…' : 'Guardar cambios'}
                  </Button>
                  <button type="button" onClick={() => deleteGroup(selected.id)}
                    className="focus-ring px-4 py-1.5 text-sm text-danger hover:text-danger/80">Eliminar grupo</button>
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
                    <select required aria-label="Carrier a agregar" value={newCarrierId} onChange={e => setNewCarrierId(e.target.value)} className={inputCls}>
                      <option value="">Seleccionar carrier…</option>
                      {carriers.filter(c => !selected.members.some(m => m.carrier_id === c.id)).map(c => (
                        <option key={c.id} value={c.id}>{c.name} — {c.host}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <input type="number" min={1} max={100} value={newPriority}
                      onChange={e => setNewPriority(e.target.value)}
                      placeholder="Prio" title="Prioridad (1=mayor)" aria-label="Prioridad (1=mayor)"
                      className="w-20 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm text-center focus:outline-none focus:border-brand-500" />
                  </div>
                  {selected.algorithm === 'percent' && (
                    <div>
                      <input type="number" min={1} max={100} value={newWeight}
                        onChange={e => setNewWeight(e.target.value)}
                        placeholder="%" title="Peso relativo (%)" aria-label="Peso relativo (%)"
                        className="w-20 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm text-center focus:outline-none focus:border-brand-500" />
                    </div>
                  )}
                  <Button type="submit" disabled={addingMember || !newCarrierId} size="sm">
                    {addingMember ? 'Agregando…' : 'Agregar'}
                  </Button>
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
                          <StatusBadge variant="muted" rounded="md" tight className="ml-2">inactivo</StatusBadge>
                        )}
                      </span>
                      <button onClick={() => removeMember(m.carrier_id)} aria-label="Quitar del grupo" className="focus-ring text-[var(--color-muted)] hover:text-danger">
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

            {/* Habilitado para — a quién le dimos acceso (customer_carrier_groups), separado
                de "Usado por" de arriba: tener acceso no implica estar ruteando con él ahora.
                Sin esto, "Usado por: ninguno" se leía como "nadie tiene acceso todavía". */}
            <div className="px-5 pb-5">
              <div className="rounded-lg border border-[var(--color-border)] p-4 space-y-3">
                <p className="text-xs text-[var(--color-muted)] uppercase tracking-wider">Habilitado para</p>
                {selected.enabled_for.length === 0 ? (
                  <p className="text-sm text-[var(--color-text-2)]">
                    Ningún cliente tiene acceso a este grupo todavía — habilitalo abajo.
                  </p>
                ) : (
                  <ul className="space-y-1.5">
                    {selected.enabled_for.map(ef => (
                      <li key={ef.customer_id} className="text-sm text-[var(--color-text)] flex items-center justify-between gap-2">
                        <span className="flex items-center gap-2">
                          <span className="w-1.5 h-1.5 rounded-full bg-brand-500 flex-shrink-0" />
                          {ef.customer_name}
                          <span className="text-[var(--color-muted)]">— {ef.display_label}</span>
                        </span>
                        <button onClick={() => removeAccess(ef.customer_id)}
                          title="Quitar acceso a este grupo"
                          aria-label="Quitar acceso a este grupo"
                          className="focus-ring text-[var(--color-muted)] hover:text-danger">
                          <Trash2 size={14} />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>

            {/* Habilitar para un cliente — reemplaza el bloque "Grupos habilitados" que
                antes vivía en la ficha del cliente. El cliente solo selecciona entre sus
                grupos ya habilitados; habilitar/deshabilitar se gestiona acá. */}
            <div className="px-5 pb-5">
              <div className="rounded-lg border border-[var(--color-border)] p-4 space-y-3">
                <div>
                  <p className="text-xs text-[var(--color-muted)] uppercase tracking-wider">Habilitar para un cliente</p>
                  <p className="text-xs text-[var(--color-muted)] mt-0.5">
                    Le da acceso a este grupo a un cliente — después, desde su ficha, elige si lo
                    usa como grupo activo del prefijo principal o de algún prefijo de campaña.
                  </p>
                </div>
                {enableMsg && <p className="text-xs text-success">{enableMsg}</p>}
                <form onSubmit={enableForCustomer} className="flex gap-2 items-end flex-wrap">
                  <div className="flex-1 min-w-48">
                    <select required aria-label="Cliente a habilitar" value={customerToEnable} onChange={e => setCustomerToEnable(e.target.value)} className={inputCls}>
                      <option value="">Seleccionar cliente…</option>
                      {customers
                        .filter(c => !selected.enabled_for.some(ef => ef.customer_id === c.id))
                        .map(c => <option key={c.id} value={c.id}>{c.name} — {c.techprefix}</option>)}
                    </select>
                  </div>
                  <Button type="submit" disabled={enablingForCustomer || !customerToEnable} size="sm">
                    {enablingForCustomer ? 'Habilitando…' : 'Habilitar'}
                  </Button>
                </form>
              </div>
            </div>
          </div>
        ) : loading ? (
          <p className="p-8 text-center text-[var(--color-text-2)] text-sm">Cargando…</p>
        ) : groups.length === 0 ? (
          <p className="p-10 text-center text-[var(--color-muted)] text-sm">Sin grupos de ruteo todavía — creá el primero arriba.</p>
        ) : (
          <table className="w-full text-sm tabular-nums">
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
                  <td className="px-6 py-3 text-center">
                    <span className="inline-flex items-center gap-1.5">
                      <span className="font-mono">{g.member_count}</span>
                      {g.member_count === 0 && g.used_by_count > 0 && (
                        <StatusBadge variant="danger" title={`En uso por ${g.used_by_count} cliente(s)/prefijo(s) sin ningún carrier — routing roto`}>
                          <AlertTriangle size={11} /> sin carriers, en uso
                        </StatusBadge>
                      )}
                    </span>
                  </td>
                  <td className="px-6 py-3 text-right">
                    <button onClick={e => { e.stopPropagation(); deleteGroup(g.id) }}
                      className="focus-ring text-xs text-danger hover:text-danger/80">Eliminar</button>
                  </td>
                </ClickableRow>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  )
}
