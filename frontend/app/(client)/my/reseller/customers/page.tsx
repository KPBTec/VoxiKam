'use client'
import { ErrorBanner } from '@/components/ErrorBanner'
import { StatusBadge, customerStatusVariant } from '@/components/StatusBadge'
import { Balance } from '@/components/Balance'
import { useEffect, useState } from 'react'
import { apiGet, apiPost, apiPut, apiDelete } from '@/lib/api'
import { ArrowLeft, Plus, Trash2 } from 'lucide-react'
import Link from 'next/link'
import { ClickableRow } from '@/components/ClickableRow'

interface SubCustomer {
  id: number; name: string; company: string | null; email: string; phone: string | null
  techprefix: string; currency: string; billing_type: string; balance: string
  status: string; rate_plan_id: number | null; rate_plan_name: string | null
  notes: string | null
  routing_group_id: number | null
}
interface RatePlan { id: number; name: string; currency: string }
interface SubCustomerPrefix { id: number; techprefix: string; label: string; routing_group_id: number | null }
interface EnabledGroup { group_id: number; display_label: string; name: string; algorithm: 'priority' | 'round_robin' | 'percent' }

const EMPTY_FORM = {
  name: '', company: '', email: '', phone: '', rate_plan_id: '' as string | number,
  techprefix: '', currency: 'PEN', billing_type: 'prepago', notes: '',
}

const cardCls  = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'
const inputCls = 'w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm text-[var(--color-text)] focus:outline-none focus:border-brand-500'
const labelCls = 'block text-xs text-[var(--color-text-2)] uppercase tracking-wider mb-1'

export default function ResellerSubCustomers() {
  const [rows, setRows]     = useState<SubCustomer[]>([])
  const [plans, setPlans]   = useState<RatePlan[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError]   = useState('')

  const [showCreate, setShowCreate] = useState(false)
  const [createForm, setCreateForm] = useState(EMPTY_FORM)
  const [creating, setCreating]     = useState(false)
  const [showDeleted, setShowDeleted] = useState(false)

  const [selected, setSelected] = useState<SubCustomer | null>(null)
  const [tab, setTab] = useState<'general' | 'red'>('general')
  const [editForm, setEditForm] = useState(EMPTY_FORM)
  const [saving, setSaving]     = useState(false)
  const [balanceAmt, setBalanceAmt] = useState('')
  const [adjustingBalance, setAdjustingBalance] = useState(false)

  const [prefixes, setPrefixes] = useState<SubCustomerPrefix[]>([])
  const [newPrefixLabel, setNewPrefixLabel] = useState('')
  const [addingPrefix, setAddingPrefix] = useState(false)

  // Grupos HABILITADOS para el sub-cliente seleccionado (con display_label/name/algorithm) —
  // viene de GET /reseller/sub-customers/{cid} (campo "groups", ver reseller.py::get_sub_customer).
  // Habilitar/deshabilitar grupos se gestiona desde /my/reseller/carrier-groups — acá solo
  // se lee la lista para el selector de abajo.
  const [enabledGroups, setEnabledGroups] = useState<EnabledGroup[]>([])
  const [routingBusy, setRoutingBusy] = useState<string | null>(null)

  async function load() {
    setLoading(true); setError('')
    try {
      const [subs, myPlans] = await Promise.all([
        apiGet(`/reseller/sub-customers${showDeleted ? '?include_deleted=true' : ''}`),
        apiGet('/reseller/rate-plans'),
      ])
      setRows(subs); setPlans(myPlans)
    } catch (e: any) { setError(e.message) }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [showDeleted])

  async function create(e: React.FormEvent) {
    e.preventDefault(); setError('')
    if (!createForm.rate_plan_id) { setError('Seleccioná un plan de tarifas'); return }
    setCreating(true)
    try {
      await apiPost('/reseller/sub-customers', {
        ...createForm,
        rate_plan_id: Number(createForm.rate_plan_id),
      })
      setCreateForm(EMPTY_FORM); setShowCreate(false)
      load()
    } catch (e: any) { setError(e.message) }
    finally { setCreating(false) }
  }

  async function openEdit(row: SubCustomer) {
    setSelected(row)
    setTab('general')
    setEditForm({
      name: row.name, company: row.company ?? '', email: row.email, phone: row.phone ?? '',
      rate_plan_id: row.rate_plan_id ?? '', techprefix: row.techprefix, currency: row.currency,
      billing_type: row.billing_type, notes: row.notes ?? '',
    })
    setBalanceAmt('')
    setNewPrefixLabel('')
    setEnabledGroups([])
    loadPrefixes(row.id)
    try {
      const detail = await apiGet(`/reseller/sub-customers/${row.id}`)
      setEnabledGroups(detail.groups ?? [])
    } catch (e: any) { setError(e.message) }
  }

  async function loadPrefixes(cid: number) {
    try {
      const p: SubCustomerPrefix[] = await apiGet(`/reseller/sub-customers/${cid}/techprefixes`)
      setPrefixes(p)
    } catch (e: any) { setError(e.message) }
  }

  async function addPrefix(e: React.FormEvent) {
    e.preventDefault(); if (!selected) return
    setAddingPrefix(true); setError('')
    try {
      const r = await apiPost(`/reseller/sub-customers/${selected.id}/techprefixes`, { label: newPrefixLabel })
      setNewPrefixLabel('')
      await loadPrefixes(selected.id)
      alert(`Prefijo asignado: ${r.techprefix}`)
    } catch (e: any) { setError(e.message) }
    finally { setAddingPrefix(false) }
  }

  async function deletePrefix(prefixId: number) {
    if (!selected) return
    try {
      await apiDelete(`/reseller/sub-customers/${selected.id}/techprefixes/${prefixId}`)
      await loadPrefixes(selected.id)
    } catch (e: any) { alert(e.message) }
  }

  async function setMainRoutingGroup(groupId: string) {
    if (!selected) return
    setRoutingBusy('main')
    try {
      await apiPut(`/reseller/sub-customers/${selected.id}/routing-group`, { group_id: groupId ? +groupId : null })
      const fresh = await apiGet('/reseller/sub-customers')
      setRows(fresh)
      const updated = fresh.find((r: SubCustomer) => r.id === selected.id)
      if (updated) setSelected(updated)
    } catch (e: any) { setError(e.message) }
    finally { setRoutingBusy(null) }
  }

  async function cutMainRouting() {
    if (!selected) return
    if (!confirm(`¿Cortar el ruteo de "${selected.name}"? El sub-cliente va a DEJAR DE RUTEAR LLAMADAS por completo hasta que se le asigne un grupo de nuevo.`)) return
    await setMainRoutingGroup('')
  }

  async function setPrefixRoutingGroup(prefixId: number, groupId: string) {
    if (!selected) return
    setRoutingBusy(String(prefixId))
    try {
      await apiPut(`/reseller/sub-customers/${selected.id}/prefixes/${prefixId}/routing-group`, { group_id: groupId ? +groupId : null })
      await loadPrefixes(selected.id)
    } catch (e: any) { setError(e.message) }
    finally { setRoutingBusy(null) }
  }

  async function saveEdit(e: React.FormEvent) {
    e.preventDefault(); if (!selected) return
    setError('')
    if (!editForm.rate_plan_id) { setError('Seleccioná un plan de tarifas'); return }
    setSaving(true)
    try {
      await apiPut(`/reseller/sub-customers/${selected.id}`, {
        ...editForm,
        rate_plan_id: Number(editForm.rate_plan_id),
      })
      await load()
      setSelected(null)
    } catch (e: any) { setError(e.message) }
    finally { setSaving(false) }
  }

  async function adjustBalance(e: React.FormEvent) {
    e.preventDefault(); if (!selected || !balanceAmt) return
    setAdjustingBalance(true); setError('')
    try {
      await apiPost(`/reseller/sub-customers/${selected.id}/balance`, { amount: Number(balanceAmt) })
      setBalanceAmt('')
      const fresh = await apiGet('/reseller/sub-customers')
      setRows(fresh)
      const updated = fresh.find((r: SubCustomer) => r.id === selected.id)
      if (updated) setSelected(updated)
    } catch (e: any) { setError(e.message) }
    finally { setAdjustingBalance(false) }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-[var(--color-text)]">Sub-clientes</h1>
          <p className="text-sm text-[var(--color-text-2)] mt-0.5">Tus propios clientes — facturados con tus tarifas</p>
        </div>
        {!selected && (
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 text-sm text-[var(--color-text-2)] cursor-pointer select-none">
              <input type="checkbox" checked={showDeleted} onChange={e => setShowDeleted(e.target.checked)} />
              Mostrar desactivados
            </label>
            <button onClick={() => setShowCreate(v => !v)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-brand-600 hover:bg-brand-500 text-white text-sm rounded-lg">
              <Plus size={15} /> Nuevo sub-cliente
            </button>
          </div>
        )}
      </div>

      {error && <ErrorBanner>{error}</ErrorBanner>}

      {showCreate && !selected && (
        <form onSubmit={create} className={`${cardCls} p-5 space-y-3`}>
          <div className="grid grid-cols-2 gap-3">
            <div><label className={labelCls}>Nombre</label>
              <input required className={inputCls} value={createForm.name} onChange={e => setCreateForm(f => ({...f, name: e.target.value}))} /></div>
            <div><label className={labelCls}>Email</label>
              <input required type="email" className={inputCls} value={createForm.email} onChange={e => setCreateForm(f => ({...f, email: e.target.value}))} /></div>
            <div><label className={labelCls}>Empresa</label>
              <input className={inputCls} value={createForm.company} onChange={e => setCreateForm(f => ({...f, company: e.target.value}))} /></div>
            <div><label className={labelCls}>Teléfono</label>
              <input className={inputCls} value={createForm.phone} onChange={e => setCreateForm(f => ({...f, phone: e.target.value}))} /></div>
            <div><label className={labelCls}>Plan de tarifas</label>
              <select required className={inputCls} value={createForm.rate_plan_id} onChange={e => setCreateForm(f => ({...f, rate_plan_id: e.target.value}))}>
                <option value="">Seleccionar plan...</option>
                {plans.map(p => <option key={p.id} value={p.id}>{p.name} ({p.currency})</option>)}
              </select></div>
            <div><label className={labelCls}>Moneda</label>
              <input className={inputCls} value={createForm.currency} onChange={e => setCreateForm(f => ({...f, currency: e.target.value}))} /></div>
            <div><label className={labelCls}>Facturación</label>
              <select className={inputCls} value={createForm.billing_type} onChange={e => setCreateForm(f => ({...f, billing_type: e.target.value}))}>
                <option value="prepago">Prepago</option>
                <option value="postpago">Postpago</option>
              </select></div>
          </div>
          <p className="text-xs text-[var(--color-muted)]">El prefijo técnico se asigna automáticamente al crear — no es editable.</p>
          <div className="flex gap-3">
            <button type="submit" disabled={creating}
              className="px-4 py-1.5 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm rounded-lg">
              {creating ? 'Creando…' : 'Crear sub-cliente'}
            </button>
            <button type="button" onClick={() => setShowCreate(false)}
              className="px-4 py-1.5 text-[var(--color-text-2)] hover:text-[var(--color-text)] text-sm">Cancelar</button>
          </div>
        </form>
      )}

      <div className={`${cardCls} overflow-x-auto`}>
        {selected ? (
          <div>
            <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--color-border)]">
              <button onClick={() => setSelected(null)} className="flex items-center gap-1.5 text-sm text-[var(--color-text-2)] hover:text-[var(--color-text)]">
                <ArrowLeft size={15} /> Volver a sub-clientes
              </button>
              <StatusBadge variant={customerStatusVariant(selected.status)}>{selected.status}</StatusBadge>
            </div>

            {/* Tabs */}
            <div className="px-5 pt-4">
              <div className="flex rounded-lg overflow-hidden border border-[var(--color-border)] w-fit">
                <button
                  onClick={() => setTab('general')}
                  className={`px-4 py-1.5 text-sm font-medium transition-colors ${tab === 'general' ? 'bg-brand-600 text-white' : 'bg-[var(--color-surface)] text-[var(--color-text-2)] hover:text-[var(--color-text)]'}`}
                >
                  General
                </button>
                <button
                  onClick={() => setTab('red')}
                  className={`px-4 py-1.5 text-sm font-medium transition-colors ${tab === 'red' ? 'bg-brand-600 text-white' : 'bg-[var(--color-surface)] text-[var(--color-text-2)] hover:text-[var(--color-text)]'}`}
                >
                  Red y Ruteo
                </button>
              </div>
            </div>

            {/* ── TAB: GENERAL ──────────────────────────────────────────── */}
            {tab === 'general' && (
            <div className="p-5 grid grid-cols-2 gap-6">
              <form onSubmit={saveEdit} className="space-y-3">
                <h2 className="font-semibold text-[var(--color-text)]">Información</h2>
                <div><label className={labelCls}>Nombre</label>
                  <input required className={inputCls} value={editForm.name} onChange={e => setEditForm(f => ({...f, name: e.target.value}))} /></div>
                <div><label className={labelCls}>Email</label>
                  <input required type="email" className={inputCls} value={editForm.email} onChange={e => setEditForm(f => ({...f, email: e.target.value}))} /></div>
                <div><label className={labelCls}>Empresa</label>
                  <input className={inputCls} value={editForm.company} onChange={e => setEditForm(f => ({...f, company: e.target.value}))} /></div>
                <div><label className={labelCls}>Teléfono</label>
                  <input className={inputCls} value={editForm.phone} onChange={e => setEditForm(f => ({...f, phone: e.target.value}))} /></div>
                <div><label className={labelCls}>Prefijo técnico</label>
                  <input disabled readOnly className={`${inputCls} opacity-60 cursor-not-allowed`} value={editForm.techprefix} title="Autogenerado al crear, no editable" /></div>
                <div><label className={labelCls}>Plan de tarifas</label>
                  <select required className={inputCls} value={editForm.rate_plan_id} onChange={e => setEditForm(f => ({...f, rate_plan_id: e.target.value}))}>
                    <option value="">Seleccionar plan...</option>
                    {plans.map(p => <option key={p.id} value={p.id}>{p.name} ({p.currency})</option>)}
                  </select></div>
                <div><label className={labelCls}>Facturación</label>
                  <select className={inputCls} value={editForm.billing_type} onChange={e => setEditForm(f => ({...f, billing_type: e.target.value}))}>
                    <option value="prepago">Prepago</option>
                    <option value="postpago">Postpago</option>
                  </select></div>
                <div><label className={labelCls}>Notas</label>
                  <textarea rows={2} className={inputCls} value={editForm.notes} onChange={e => setEditForm(f => ({...f, notes: e.target.value}))} /></div>
                <button type="submit" disabled={saving}
                  className="px-4 py-1.5 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm rounded-lg">
                  {saving ? 'Guardando…' : 'Guardar cambios'}
                </button>
              </form>

              <div className="space-y-3">
                <h2 className="font-semibold text-[var(--color-text)]">Balance</h2>
                <p className="text-2xl font-bold"><Balance amount={selected.balance} /></p>
                {selected.billing_type === 'prepago' && Number(selected.balance) <= 0 && (
                  <p className="text-xs bg-danger/10 border border-danger/30 text-danger rounded-lg px-3 py-2">
                    Sin saldo — este sub-cliente no puede iniciar llamadas nuevas hasta recargar. No corta llamadas ya en curso.
                  </p>
                )}
                {selected.status === 'deleted' ? (
                  <p className="text-xs text-[var(--color-muted)]">Este sub-cliente está desactivado — pedile al administrador que lo reactive para poder ajustar su balance.</p>
                ) : (
                  <form onSubmit={adjustBalance} className="flex gap-2 items-end">
                    <div className="flex-1">
                      <label className={labelCls}>Monto (+crédito / −débito)</label>
                      <input type="number" step="0.01" placeholder="ej: 50.00 o -10.00" required
                        value={balanceAmt} onChange={e => setBalanceAmt(e.target.value)} className={inputCls} />
                    </div>
                    <button type="submit" disabled={adjustingBalance}
                      className="px-4 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm rounded-lg">
                      {adjustingBalance ? 'Aplicando…' : 'Aplicar'}
                    </button>
                  </form>
                )}
              </div>
            </div>
            )}

            {/* ── TAB: RED Y RUTEO ──────────────────────────────────────── */}
            {tab === 'red' && (
            <div className="p-5 space-y-6">
              <div className="space-y-3">
                <h2 className="font-semibold text-[var(--color-text)]">Grupo de ruteo</h2>
                <p className="text-xs text-[var(--color-muted)]">
                  Este sub-cliente rutea todas sus llamadas a través de UN solo grupo de carriers
                  por vez. Habilitar grupos y asignarles carriers se gestiona desde{' '}
                  <Link href="/my/reseller/carrier-groups" className="underline hover:text-brand-400">Grupos de ruteo</Link>.
                </p>
                <div>
                  <label className={labelCls}>Grupo del prefijo principal ({selected.techprefix})</label>
                  {enabledGroups.length === 0 ? (
                    <p className="text-sm text-yellow-400">
                      Este sub-cliente todavía no tiene ningún grupo habilitado —{' '}
                      <Link href="/my/reseller/carrier-groups" className="underline hover:text-yellow-300">gestionalo desde Grupos de ruteo</Link>.
                    </p>
                  ) : (
                    <>
                      <select
                        disabled={routingBusy === 'main'}
                        value={selected.routing_group_id ?? ''}
                        onChange={e => { if (e.target.value) setMainRoutingGroup(e.target.value) }}
                        className={inputCls}>
                        {!selected.routing_group_id && (
                          <option value="" disabled>⚠ Sin ruteo — el sub-cliente no puede llamar</option>
                        )}
                        {enabledGroups.map(g => (
                          <option key={g.group_id} value={g.group_id}>{g.name}</option>
                        ))}
                      </select>
                      {selected.routing_group_id !== null && (
                        <button type="button" onClick={cutMainRouting} disabled={routingBusy === 'main'}
                          className="mt-1 text-xs text-red-400 hover:text-red-300 disabled:opacity-50">
                          Cortar ruteo del sub-cliente (deja de rutear llamadas)
                        </button>
                      )}
                    </>
                  )}
                </div>
              </div>

              <div className="space-y-3">
                <h2 className="font-semibold text-[var(--color-text)]">Prefijos de campaña</h2>
                <p className="text-xs text-[var(--color-muted)]">
                  Además del principal ({selected.techprefix}), podés agregar un prefijo por campaña de
                  su marcador — factura al mismo balance, pero se ve desglosado en su panel. El prefijo
                  (4 dígitos) se asigna solo, para evitar colisiones — solo elegí una etiqueta.
                </p>
                {selected.status !== 'deleted' && (
                  <form onSubmit={addPrefix} className="flex gap-2 items-end">
                    <input type="text" placeholder="Etiqueta — ej: Campaña Cobranzas"
                      value={newPrefixLabel} onChange={e => setNewPrefixLabel(e.target.value)}
                      className={`${inputCls} flex-1`} />
                    <button type="submit" disabled={addingPrefix}
                      className="px-3 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm rounded-lg">
                      {addingPrefix ? 'Agregando…' : 'Agregar'}
                    </button>
                  </form>
                )}
                <div className="divide-y divide-[var(--color-border)] rounded-lg border border-[var(--color-border)] overflow-hidden">
                  {prefixes.map(p => (
                    <div key={p.id} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
                      <span className="text-[var(--color-text)]">
                        <span className="font-mono text-brand-400">{p.techprefix}</span>
                        {p.label && <span className="ml-2 text-[var(--color-text-2)]">{p.label}</span>}
                      </span>
                      <div className="flex items-center gap-2">
                        <select
                          disabled={routingBusy === String(p.id)}
                          value={p.routing_group_id ?? ''}
                          onChange={e => setPrefixRoutingGroup(p.id, e.target.value)}
                          className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-2 py-1 text-xs focus:outline-none focus:border-brand-500">
                          <option value="">
                            Hereda del sub-cliente{enabledGroups.find(g => g.group_id === selected.routing_group_id)
                              ? ` (${enabledGroups.find(g => g.group_id === selected.routing_group_id)!.name})`
                              : ''}
                          </option>
                          {enabledGroups.map(g => (
                            <option key={g.group_id} value={g.group_id}>{g.name}</option>
                          ))}
                        </select>
                        <button onClick={() => deletePrefix(p.id)} aria-label="Eliminar prefijo" className="text-[var(--color-muted)] hover:text-red-400">
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                  ))}
                  {prefixes.length === 0 && (
                    <p className="px-3 py-4 text-center text-[var(--color-muted)] text-xs">Sin prefijos de campaña — solo rutea por el principal.</p>
                  )}
                </div>
              </div>
            </div>
            )}
          </div>
        ) : loading ? (
          <p className="p-8 text-center text-[var(--color-text-2)] text-sm">Cargando…</p>
        ) : rows.length === 0 ? (
          <p className="p-10 text-center text-[var(--color-muted)] text-sm">Sin sub-clientes todavía — creá el primero arriba.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-[var(--color-text-2)] uppercase border-b border-[var(--color-border)]">
                <th className="px-6 py-3 text-left">Nombre</th>
                <th className="px-6 py-3 text-left">Email</th>
                <th className="px-6 py-3 text-center">Prefijo</th>
                <th className="px-6 py-3 text-left">Plan</th>
                <th className="px-6 py-3 text-right">Balance</th>
                <th className="px-6 py-3 text-center">Estado</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              {rows.map(r => (
                <ClickableRow key={r.id} onActivate={() => openEdit(r)} className={`hover:bg-white/2 cursor-pointer ${r.status === 'deleted' ? 'opacity-50' : ''}`}>
                  <td className="px-6 py-3 font-medium text-[var(--color-text)]">{r.name}</td>
                  <td className="px-6 py-3 text-[var(--color-text)]">{r.email}</td>
                  <td className="px-6 py-3 text-center font-mono text-brand-400">{r.techprefix}</td>
                  <td className="px-6 py-3 text-[var(--color-text)]">{r.rate_plan_name ?? '—'}</td>
                  <td className="px-6 py-3 text-right"><Balance amount={r.balance} /></td>
                  <td className="px-6 py-3 text-center">
                    <StatusBadge variant={customerStatusVariant(r.status)}>{r.status}</StatusBadge>
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
