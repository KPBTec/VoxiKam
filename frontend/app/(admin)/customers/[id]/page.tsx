'use client'
import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { apiGet, apiPost, apiDelete, apiPut } from '@/lib/api'
import Link from 'next/link'
import { ArrowLeft, Plus, Trash2, Save, KeyRound, UserX, UserPlus, Power, PowerOff, Building2 } from 'lucide-react'
import { EntityComments } from '@/components/EntityComments'
import { StatusBadge, customerStatusVariant } from '@/components/StatusBadge'
import { Balance } from '@/components/Balance'
import { ErrorBanner } from '@/components/ErrorBanner'
import { PermissionTree, PermissionResource } from '@/components/PermissionTree'
import { Button } from '@/components/Button'
import { Card } from '@/components/Card'

interface CustomerIP { id: number; ip: string; description: string | null }
interface CustomerPrefix { id: number; techprefix: string; label: string; routing_group_id: number | null }
interface CustomerCarrier { id: number; name: string; host: string; priority: number }
interface PortalUser { id: number; name: string; email: string }
interface CustomerGroup { group_id: number; display_label: string; name: string; algorithm: 'priority' | 'round_robin' | 'percent' }
interface CustomerDetail {
  id: number; name: string; company: string | null; email: string; phone: string | null
  balance: string; credit_limit: string; rate_plan_id: number | null
  profile_id: number | null; profile_name: string | null
  calllimit: number; cpslimit: number; techprefix: string; currency: string
  // Permisos resueltos (COALESCE override propio/perfil/default) — ver
  // backend/auth.py::resolve_permissions(). En modo edición, el editor
  // SOLO tiene efecto real si profile_id es null (ver PermissionTree abajo).
  permissions: Record<string, boolean>
  status: string; billing_type: string; notes: string | null
  is_reseller: boolean
  routing_group_id: number | null
  ips: CustomerIP[]; prefixes: CustomerPrefix[]; carriers: CustomerCarrier[]
  groups: CustomerGroup[]
  portal_user: PortalUser | null
}
interface BalanceTx {
  id: number; type: 'cdr' | 'manual' | 'invoice_payment' | 'recalc'
  amount: string; balance_after: string; reference: string | null
  created_by: string | null; created_at: string
}
interface RatePlan { id: number; name: string; currency: string }
interface Profile { id: number; name: string }

// Resources "hoja" (sin hijos) para el resumen en badges — mismo criterio de
// árbol que components/PermissionTree.tsx, acá solo para el modo lectura.
function leafResources(all: PermissionResource[], reseller: boolean): PermissionResource[] {
  const scoped = all.filter(r => r.resource_key.startsWith('reseller_') === reseller)
  return scoped.filter(r => !scoped.some(x => x.parent_key === r.resource_key))
}

const STATUSES = ['active', 'suspended', 'expired']

export default function CustomerDetailPage() {
  const { id } = useParams<{ id: string }>()
  useEffect(() => { document.title = 'Cliente · VoxiKam' }, [])

  const [tab, setTab] = useState<'general' | 'red'>('general')

  const [customer, setCustomer]   = useState<CustomerDetail | null>(null)
  const [ratePlans, setRatePlans] = useState<RatePlan[]>([])
  const [profiles, setProfiles]   = useState<Profile[]>([])
  const [resources, setResources] = useState<PermissionResource[]>([])

  // Prefijos de campaña
  const [newPrefixLabel, setNewPrefixLabel] = useState('')
  const [addingPrefix, setAddingPrefix]   = useState(false)

  // Grupo de ruteo — el cliente solo SELECCIONA entre sus grupos ya habilitados
  // (habilitar/deshabilitar se gestiona desde /carrier-groups, ver problema 4 del pase de UI).
  const [routingBusy, setRoutingBusy]       = useState<string | null>(null)

  // Balance
  const [balanceAmt, setBalanceAmt]         = useState('')
  const [adjustingBalance, setAdjustingBalance] = useState(false)
  const [balanceTx, setBalanceTx]           = useState<BalanceTx[] | null>(null)
  const [balanceTxOffset, setBalanceTxOffset] = useState(0)
  const [balanceTxMore, setBalanceTxMore]   = useState(true)
  const [loadingBalanceTx, setLoadingBalanceTx] = useState(false)
  const BALANCE_TX_PAGE = 25

  // Edit info
  const [editMode, setEditMode] = useState(false)
  const [editForm, setEditForm] = useState<Partial<CustomerDetail>>({})
  const [saving, setSaving]     = useState(false)
  const [error, setError]       = useState('')

  // Portal user
  const [portalForm, setPortalForm] = useState({ name: '', email: '', password: '' })
  const [newPass, setNewPass]       = useState('')
  const [portalBusy, setPortalBusy] = useState(false)

  // Activación
  const [activationBusy, setActivationBusy] = useState(false)
  const [resellerBusy, setResellerBusy] = useState(false)

  // is_reseller viaja como 0/1 desde MySQL (TINYINT), no como boolean real —
  // sin este cast, `customer.is_reseller && (<div>...)` en el JSX de abajo
  // no se salta el render con 0 (solo con false/null/undefined), y React
  // pinta el "0" como texto suelto en la página para cualquier cliente que
  // no sea reseller.
  const load = () => apiGet(`/admin/customers/${id}`)
    .then(c => setCustomer({ ...c, is_reseller: !!c.is_reseller }))
    .catch((e: any) => setError(e.message))

  // Historial de balance (balance_transactions) — paginado 25 en 25, más
  // recientes primero. Es el ledger real que explica por qué el balance
  // llegó al número que muestra arriba (una fila por CDR facturado, ajuste
  // manual, pago de factura o recálculo) — sin esto no había forma de
  // auditar un balance que "no cuadra" a simple vista.
  async function loadBalanceTx(reset: boolean) {
    setLoadingBalanceTx(true)
    try {
      const off = reset ? 0 : balanceTxOffset
      const rows: BalanceTx[] = await apiGet(`/admin/customers/${id}/balance-transactions?limit=${BALANCE_TX_PAGE}&offset=${off}`)
      setBalanceTx(reset ? rows : [...(balanceTx ?? []), ...rows])
      setBalanceTxOffset(off + rows.length)
      setBalanceTxMore(rows.length === BALANCE_TX_PAGE)
    } catch (e: any) { setError(e.message) }
    finally { setLoadingBalanceTx(false) }
  }

  useEffect(() => {
    load()
    loadBalanceTx(true)
    apiGet('/admin/rates/plans').then(setRatePlans).catch((e: any) => setError(e.message))
    apiGet('/admin/profiles').then(setProfiles).catch((e: any) => setError(e.message))
    apiGet('/admin/profiles/resources').then(setResources).catch((e: any) => setError(e.message))
  }, [id]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (customer && !editMode) setEditForm(customer)
  }, [customer])

  async function saveInfo(e: React.FormEvent) {
    e.preventDefault(); setSaving(true); setError('')
    try {
      await apiPut(`/admin/customers/${id}`, {
        name:          editForm.name,
        company:       editForm.company ?? null,
        email:         editForm.email,
        phone:         editForm.phone ?? null,
        rate_plan_id:  editForm.rate_plan_id ?? null,
        calllimit:     editForm.calllimit,
        cpslimit:      editForm.cpslimit,
        techprefix:    editForm.techprefix,
        currency:      editForm.currency ?? 'PEN',
        profile_id:    editForm.profile_id ?? null,
        permissions:   editForm.permissions ?? {},
        status:        editForm.status ?? 'active',
        billing_type:  editForm.billing_type ?? 'prepago',
        notes:         editForm.notes ?? null,
      })
      setEditMode(false); load()
    } catch (e: any) { setError(e.message) }
    finally { setSaving(false) }
  }

  async function addPrefix(e: React.FormEvent) {
    e.preventDefault(); setAddingPrefix(true); setError('')
    try {
      const r = await apiPost(`/admin/customers/${id}/prefixes`, { label: newPrefixLabel })
      setNewPrefixLabel(''); load()
      alert(`Prefijo asignado: ${r.techprefix}`)
    } catch (e: any) { setError(e.message) }
    finally { setAddingPrefix(false) }
  }

  async function deletePrefix(prefixId: number) {
    await apiDelete(`/admin/customers/${id}/prefixes/${prefixId}`); load()
  }

  async function setMainRoutingGroup(groupId: string) {
    setRoutingBusy('main')
    try {
      await apiPut(`/admin/customers/${id}/routing-group`, { group_id: groupId ? +groupId : null })
      load()
    } catch (e: any) { setError(e.message) }
    finally { setRoutingBusy(null) }
  }

  async function cutMainRouting() {
    if (!confirm(`¿Cortar el ruteo de "${customer?.name}"? El cliente va a DEJAR DE RUTEAR LLAMADAS por completo hasta que se le asigne un grupo de nuevo.`)) return
    await setMainRoutingGroup('')
  }

  async function setPrefixRoutingGroup(prefixId: number, groupId: string) {
    setRoutingBusy(String(prefixId))
    try {
      await apiPut(`/admin/customers/${id}/prefixes/${prefixId}/routing-group`, { group_id: groupId ? +groupId : null })
      load()
    } catch (e: any) { setError(e.message) }
    finally { setRoutingBusy(null) }
  }

  async function createPortalUser(e: React.FormEvent) {
    e.preventDefault(); setPortalBusy(true); setError('')
    try {
      await apiPost(`/admin/customers/${id}/user`, portalForm)
      setPortalForm({ name: '', email: '', password: '' }); load()
    } catch (e: any) { setError(e.message) }
    finally { setPortalBusy(false) }
  }

  async function deletePortalUser() {
    if (!confirm('¿Eliminar el acceso al portal de este cliente?')) return
    setPortalBusy(true)
    try { await apiDelete(`/admin/customers/${id}/user`); load() }
    catch (e: any) { setError(e.message) }
    finally { setPortalBusy(false) }
  }

  async function resetPortalPassword(e: React.FormEvent) {
    e.preventDefault(); setPortalBusy(true); setError('')
    try {
      await apiPut(`/admin/customers/${id}/user/password`, { password: newPass })
      setNewPass('')
    } catch (e: any) { setError(e.message) }
    finally { setPortalBusy(false) }
  }

  async function deactivateCustomer() {
    if (!confirm(`¿Desactivar a "${customer?.name}"? Deja de poder registrar, hacer llamadas o entrar al portal. No se pierde su historial y se puede reactivar en cualquier momento.`)) return
    setActivationBusy(true); setError('')
    try { await apiDelete(`/admin/customers/${id}`); load() }
    catch (e: any) { setError(e.message) }
    finally { setActivationBusy(false) }
  }

  async function reactivateCustomer() {
    setActivationBusy(true); setError('')
    try { await apiPost(`/admin/customers/${id}/reactivate`, {}); load() }
    catch (e: any) { setError(e.message) }
    finally { setActivationBusy(false) }
  }

  async function makeReseller() {
    if (!confirm(`¿Convertir a "${customer?.name}" en reseller? Va a poder crear sus propios sub-clientes y tarifas.`)) return
    setResellerBusy(true); setError('')
    try { await apiPost(`/admin/customers/${id}/reseller`, {}); load() }
    catch (e: any) { setError(e.message) }
    finally { setResellerBusy(false) }
  }

  async function removeReseller() {
    if (!confirm(`¿Quitarle el rol de reseller a "${customer?.name}"?`)) return
    setResellerBusy(true); setError('')
    try { await apiDelete(`/admin/customers/${id}/reseller`); load() }
    catch (e: any) { setError(e.message) }
    finally { setResellerBusy(false) }
  }

  async function adjustBalance(e: React.FormEvent) {
    e.preventDefault(); setAdjustingBalance(true)
    try {
      await apiPost(`/admin/customers/${id}/balance`, { amount: Number(balanceAmt) })
      setBalanceAmt(''); load(); loadBalanceTx(true)
    } catch (e: any) { setError(e.message) }
    finally { setAdjustingBalance(false) }
  }

  const BALANCE_TX_LABEL: Record<BalanceTx['type'], string> = {
    cdr: 'Llamada', manual: 'Ajuste manual', invoice_payment: 'Pago de factura', recalc: 'Recálculo de tarifas',
  }

  if (!customer && error) return (
    <div className="p-6 text-danger">{error}</div>
  )

  if (!customer) return (
    <div className="p-6 text-[var(--color-text-2)]">Cargando...</div>
  )

  const inputCls = 'w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-500'
  const labelCls = 'block text-xs text-[var(--color-text-2)] uppercase tracking-wider mb-1'

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4 flex-wrap">
        <Link href="/customers" aria-label="Volver" className="focus-ring text-[var(--color-muted)] hover:text-[var(--color-text)] transition-colors">
          <ArrowLeft size={20} />
        </Link>
        <div className="flex-1 min-w-[10rem]">
          <h1 className="text-2xl font-bold">{customer.name}</h1>
          <p className="text-sm text-[var(--color-text-2)]">{customer.email}</p>
        </div>
        <StatusBadge variant={customerStatusVariant(customer.status)}>
          {customer.status}
        </StatusBadge>
        {customer.is_reseller && (
          <StatusBadge variant="brand" bordered>Reseller</StatusBadge>
        )}
        {customer.is_reseller ? (
          <button onClick={removeReseller} disabled={resellerBusy}
            className="focus-ring flex items-center gap-1.5 text-xs text-[var(--color-muted)] hover:text-danger disabled:opacity-50 border border-[var(--color-border)] hover:border-danger/50 rounded-lg px-3 py-1.5 transition-colors">
            <Building2 size={14} /> {resellerBusy ? 'Quitando...' : 'Quitar reseller'}
          </button>
        ) : (
          <button onClick={makeReseller} disabled={resellerBusy}
            className="focus-ring flex items-center gap-1.5 text-xs text-brand-400 hover:text-brand-300 disabled:opacity-50 border border-brand-900/50 hover:border-brand-700 rounded-lg px-3 py-1.5 transition-colors">
            <Building2 size={14} /> {resellerBusy ? 'Convirtiendo...' : 'Convertir en reseller'}
          </button>
        )}
        {customer.status === 'deleted' ? (
          <button onClick={reactivateCustomer} disabled={activationBusy}
            className="focus-ring flex items-center gap-1.5 text-xs text-success hover:text-success disabled:opacity-50 border border-success/30 hover:border-success/50 rounded-lg px-3 py-1.5 transition-colors">
            <Power size={14} /> {activationBusy ? 'Reactivando...' : 'Reactivar cliente'}
          </button>
        ) : (
          <button onClick={deactivateCustomer} disabled={activationBusy}
            className="focus-ring flex items-center gap-1.5 text-xs text-[var(--color-muted)] hover:text-danger disabled:opacity-50 border border-[var(--color-border)] hover:border-danger/50 rounded-lg px-3 py-1.5 transition-colors">
            <PowerOff size={14} /> {activationBusy ? 'Desactivando...' : 'Desactivar cliente'}
          </button>
        )}
      </div>

      {error && <ErrorBanner>{error}</ErrorBanner>}

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {([
          ['Prefijo', customer.techprefix, 'font-mono tabular-nums text-brand-400'],
          ['CPS límite', customer.cpslimit.toString(), 'font-mono tabular-nums'],
          ['Calls máx', customer.calllimit.toString(), 'font-mono tabular-nums'],
        ] as [string, string, string][]).map(([label, value, cls]) => (
          <Card key={label} className="p-5">
            <p className="text-xs text-[var(--color-text-2)] uppercase tracking-wider mb-1">{label}</p>
            <p className={`text-xl font-semibold ${cls}`}>{value}</p>
          </Card>
        ))}
        <Card className="p-5">
          <p className="text-xs text-[var(--color-text-2)] uppercase tracking-wider mb-1">Balance</p>
          <p className="text-xl font-semibold"><Balance amount={customer.balance} /></p>
          <p className="text-[10px] text-[var(--color-muted)] mt-1">Neto: consumo histórico menos pagos registrados</p>
        </Card>
      </div>

      {/* Tabs */}
      <div className="flex rounded-lg overflow-hidden border border-[var(--color-border)] w-fit">
        <button
          onClick={() => setTab('general')}
          className={`focus-ring px-4 py-1.5 text-sm font-medium transition-colors ${tab === 'general' ? 'bg-brand-600 text-white' : 'bg-[var(--color-surface)] text-[var(--color-text-2)] hover:text-[var(--color-text)]'}`}
        >
          General
        </button>
        <button
          onClick={() => setTab('red')}
          className={`focus-ring px-4 py-1.5 text-sm font-medium transition-colors ${tab === 'red' ? 'bg-brand-600 text-white' : 'bg-[var(--color-surface)] text-[var(--color-text-2)] hover:text-[var(--color-text)]'}`}
        >
          Red y Ruteo
        </button>
      </div>

      {/* ── TAB: GENERAL ──────────────────────────────────────────────────── */}
      {tab === 'general' && (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Info del cliente */}
        <Card className="p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">Información</h2>
            {!editMode ? (
              <button onClick={() => setEditMode(true)}
                className="focus-ring text-xs text-brand-400 hover:text-brand-300">Editar</button>
            ) : (
              <button onClick={() => { setEditForm(customer); setEditMode(false) }}
                className="focus-ring text-xs text-[var(--color-muted)] hover:text-[var(--color-text)]">Cancelar</button>
            )}
          </div>

          {!editMode ? (
            <dl className="space-y-2 text-sm">
              {([
                ['Nombre',   customer.name],
                ['Email',    customer.email],
                ['Empresa',  customer.company ?? '—'],
                ['Teléfono', customer.phone ?? '—'],
                ['Prefijo',  customer.techprefix],
                ['Plan tarifa', ratePlans.find(r => r.id === customer.rate_plan_id)?.name ?? '—'],
                ['Estado',   customer.status],
                ['Facturación', customer.billing_type ?? 'prepago'],
              ] as [string, string][]).map(([k, v]) => (
                <div key={k} className="flex justify-between">
                  <dt className="text-[var(--color-text-2)]">{k}</dt>
                  <dd className="font-medium">{v}</dd>
                </div>
              ))}
              <div className="pt-1">
                <dt className="text-xs text-[var(--color-text-2)] uppercase tracking-wider mb-2">
                  Módulos del portal
                  {customer.profile_name && (
                    <span className="ml-2 text-brand-400 normal-case font-normal">— perfil: {customer.profile_name}</span>
                  )}
                </dt>
                {/* Con perfil asignado, los módulos los define el perfil (ver
                    /profiles) — listar cada badge acá era redundante con esa
                    pantalla. Sin perfil (permisos manuales), sí hace falta
                    mostrarlos acá porque este cliente es la única fuente de verdad. */}
                {!customer.profile_name && (
                  <div className="flex flex-wrap gap-1.5">
                    {leafResources(resources, false).map(r => (
                      <StatusBadge key={r.resource_key} variant={customer.permissions?.[r.resource_key] ? 'success' : 'muted'}
                        className={customer.permissions?.[r.resource_key] ? '' : 'line-through'}>
                        {r.label}
                      </StatusBadge>
                    ))}
                  </div>
                )}
              </div>
              {customer.is_reseller && !customer.profile_name && (
                <div className="pt-1">
                  <dt className="text-xs text-[var(--color-text-2)] uppercase tracking-wider mb-2">
                    Módulos del portal reseller
                  </dt>
                  <div className="flex flex-wrap gap-1.5">
                    {leafResources(resources, true).map(r => (
                      <StatusBadge key={r.resource_key} variant={customer.permissions?.[r.resource_key] ? 'brand' : 'muted'}
                        className={customer.permissions?.[r.resource_key] ? '' : 'line-through'}>
                        {r.label}
                      </StatusBadge>
                    ))}
                  </div>
                </div>
              )}
            </dl>
          ) : (
            <form onSubmit={saveInfo} className="space-y-3">
              <div>
                <label htmlFor="edit-name" className={labelCls}>Nombre</label>
                <input id="edit-name" className={inputCls} value={editForm.name ?? ''} onChange={e => setEditForm(f => ({...f, name: e.target.value}))} required />
              </div>
              <div>
                <label htmlFor="edit-email" className={labelCls}>Email</label>
                <input id="edit-email" type="email" className={inputCls} value={editForm.email ?? ''} onChange={e => setEditForm(f => ({...f, email: e.target.value}))} required />
              </div>
              <div>
                <label htmlFor="edit-company" className={labelCls}>Empresa</label>
                <input id="edit-company" className={inputCls} value={editForm.company ?? ''} onChange={e => setEditForm(f => ({...f, company: e.target.value}))} />
              </div>
              <div>
                <label htmlFor="edit-phone" className={labelCls}>Teléfono</label>
                <input id="edit-phone" className={inputCls} value={editForm.phone ?? ''} onChange={e => setEditForm(f => ({...f, phone: e.target.value}))} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                {/* 2 columnas OK incluso en mobile — son 2 inputs numéricos cortos */}
                <div>
                  <label htmlFor="edit-cpslimit" className={labelCls}>CPS límite</label>
                  <input id="edit-cpslimit" type="number" className={inputCls} value={editForm.cpslimit ?? 2} onChange={e => setEditForm(f => ({...f, cpslimit: +e.target.value}))} />
                </div>
                <div>
                  <label htmlFor="edit-calllimit" className={labelCls}>Calls máx</label>
                  <input id="edit-calllimit" type="number" className={inputCls} value={editForm.calllimit ?? 10} onChange={e => setEditForm(f => ({...f, calllimit: +e.target.value}))} />
                </div>
              </div>
              <div>
                <label htmlFor="edit-rateplan" className={labelCls}>Plan de tarifas</label>
                <select id="edit-rateplan" required className={inputCls} value={editForm.rate_plan_id ?? ''} onChange={e => setEditForm(f => ({...f, rate_plan_id: e.target.value ? +e.target.value : null}))}>
                  <option value="">Seleccionar plan...</option>
                  {ratePlans.map(rp => <option key={rp.id} value={rp.id}>{rp.name} ({rp.currency})</option>)}
                </select>
              </div>
              <div>
                <label htmlFor="edit-status" className={labelCls}>Estado</label>
                <select id="edit-status" className={inputCls} value={editForm.status ?? 'active'} onChange={e => setEditForm(f => ({...f, status: e.target.value}))}>
                  {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div>
                <label htmlFor="edit-billing" className={labelCls}>Tipo de facturación</label>
                <select id="edit-billing" className={inputCls} value={editForm.billing_type ?? 'prepago'} onChange={e => setEditForm(f => ({...f, billing_type: e.target.value}))}>
                  <option value="prepago">Prepago</option>
                  <option value="postpago">Postpago</option>
                </select>
              </div>
              <div>
                <label htmlFor="edit-notes" className={labelCls}>Notas</label>
                <textarea id="edit-notes" className={inputCls} rows={2} value={editForm.notes ?? ''} onChange={e => setEditForm(f => ({...f, notes: e.target.value}))} />
              </div>
              <div className="space-y-2 pt-1">
                <p className="text-xs text-[var(--color-text-2)] uppercase tracking-wider">Módulos del portal</p>
                <div>
                  <label htmlFor="edit-profile" className={labelCls}>Perfil de módulos</label>
                  <select id="edit-profile" className={inputCls}
                    value={editForm.profile_id ?? ''}
                    onChange={e => setEditForm(f => ({...f, profile_id: e.target.value ? +e.target.value : null}))}>
                    <option value="">Personalizado (módulos manuales)</option>
                    {profiles.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                </div>
                {!editForm.profile_id ? (
                  <PermissionTree resources={resources} value={editForm.permissions ?? {}}
                    onChange={(key, val) => setEditForm(f => ({...f, permissions: {...(f.permissions ?? {}), [key]: val}}))}
                    sectionFilter={r => !r.resource_key.startsWith('reseller_')} />
                ) : (
                  <p className="text-xs text-[var(--color-text-2)]">
                    Los módulos habilitados los define el perfil — gestionalos desde{' '}
                    <Link href="/profiles" className="focus-ring underline hover:text-brand-400">Perfiles</Link>.
                  </p>
                )}
              </div>
              {customer.is_reseller && (
                <div className="space-y-2 pt-1">
                  <p className="text-xs text-[var(--color-text-2)] uppercase tracking-wider">Módulos del portal reseller</p>
                  {!editForm.profile_id ? (
                    <PermissionTree resources={resources} value={editForm.permissions ?? {}}
                      onChange={(key, val) => setEditForm(f => ({...f, permissions: {...(f.permissions ?? {}), [key]: val}}))}
                      sectionFilter={r => r.resource_key.startsWith('reseller_')} />
                  ) : (
                    <p className="text-xs text-[var(--color-text-2)]">
                      Los módulos habilitados los define el perfil — gestionalos desde{' '}
                      <Link href="/profiles" className="underline hover:text-brand-400">Perfiles</Link>.
                    </p>
                  )}
                </div>
              )}
              <div className="flex gap-3 pt-1">
                <Button type="submit" disabled={saving} icon={<Save size={14} />}>
                  {saving ? 'Guardando...' : 'Guardar'}
                </Button>
              </div>
            </form>
          )}
        </Card>

        {/* Balance */}
        <Card className="p-5 space-y-4">
          <h2 className="font-semibold">Ajustar balance</h2>
          <p className="text-sm text-[var(--color-text-2)]">
            Balance actual: <Balance amount={customer.balance} className="font-semibold" />
          </p>
          {(customer.billing_type ?? 'prepago') === 'prepago' && parseFloat(customer.balance) <= 0 && (
            <p className="text-xs bg-danger/10 border border-danger/30 text-danger rounded-lg px-3 py-2">
              Sin saldo — este cliente no puede iniciar llamadas nuevas hasta recargar. No corta llamadas ya en curso.
            </p>
          )}
          <form onSubmit={adjustBalance} className="flex gap-3 items-end flex-wrap">
            <div className="flex-1 min-w-[10rem]">
              <label htmlFor="balance-amt" className={labelCls}>Monto (+crédito / −débito)</label>
              <input id="balance-amt" type="number" step="0.01" placeholder="ej: 50.00 o -10.00"
                value={balanceAmt} onChange={e => setBalanceAmt(e.target.value)} required
                className={inputCls} />
            </div>
            <Button type="submit" disabled={adjustingBalance || !balanceAmt}>
              {adjustingBalance ? 'Aplicando...' : 'Aplicar'}
            </Button>
          </form>
        </Card>

        {/* Historial de balance */}
        <Card className="p-5 space-y-4 lg:col-span-2">
          <div>
            <h2 className="font-semibold">Historial de balance</h2>
            <p className="text-xs text-[var(--color-muted)] mt-0.5">
              Cada fila es un movimiento real que tocó el balance — llamada facturada, ajuste manual,
              pago de factura o recálculo de tarifas. Esto es lo que explica el número de arriba.
            </p>
          </div>
          {balanceTx === null || (loadingBalanceTx && balanceTx.length === 0) ? (
            <p className="text-sm text-[var(--color-muted)] py-4 text-center">Cargando...</p>
          ) : balanceTx.length === 0 ? (
            <p className="text-sm text-[var(--color-muted)] py-4 text-center">Sin movimientos todavía.</p>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm tabular-nums">
                  <thead>
                    <tr className="text-left text-xs text-[var(--color-text-2)] uppercase tracking-wider border-b border-[var(--color-border)]">
                      <th className="py-2 pr-4">Fecha</th>
                      <th className="py-2 pr-4">Tipo</th>
                      <th className="py-2 pr-4 text-right">Monto</th>
                      <th className="py-2 pr-4 text-right">Balance después</th>
                      <th className="py-2 pr-4">Referencia</th>
                      <th className="py-2">Por</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--color-border)]/40">
                    {balanceTx.map(tx => (
                      <tr key={tx.id}>
                        <td className="py-2 pr-4 text-[var(--color-text-2)] whitespace-nowrap">
                          {new Date(tx.created_at).toLocaleString('es-PE')}
                        </td>
                        <td className="py-2 pr-4">{BALANCE_TX_LABEL[tx.type] ?? tx.type}</td>
                        <td className={`py-2 pr-4 text-right font-mono tabular-nums ${parseFloat(tx.amount) >= 0 ? 'text-success' : 'text-danger'}`}>
                          {parseFloat(tx.amount) >= 0 ? '+' : ''}{parseFloat(tx.amount).toFixed(2)}
                        </td>
                        <td className="py-2 pr-4 text-right font-mono">{parseFloat(tx.balance_after).toFixed(2)}</td>
                        <td className="py-2 pr-4 text-[var(--color-text-2)] font-mono text-xs">{tx.reference ?? '—'}</td>
                        <td className="py-2 text-[var(--color-text-2)]">{tx.created_by ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {balanceTxMore && (
                <button onClick={() => loadBalanceTx(false)} disabled={loadingBalanceTx}
                  className="focus-ring text-sm text-brand-400 hover:text-brand-300 disabled:opacity-50">
                  {loadingBalanceTx ? 'Cargando...' : 'Cargar más'}
                </button>
              )}
            </>
          )}
        </Card>
      </div>
      )}

      {/* ── TAB: RED Y RUTEO ──────────────────────────────────────────────── */}
      {tab === 'red' && (
      <>
      {/* Prefijos de campaña */}
      <Card className="p-5 space-y-4">
        <div>
          <h2 className="font-semibold">Prefijos de campaña</h2>
          <p className="text-xs text-[var(--color-muted)] mt-0.5">
            Además del prefijo principal (<span className="font-mono">{customer.techprefix}</span>), este
            cliente puede tener prefijos adicionales — uno por campaña de su Vicidial/marcador — que
            facturan al mismo balance pero permiten ver consumo desglosado por campaña en su panel.
            El prefijo (4 dígitos) se asigna solo, para evitar colisiones — solo elegí una etiqueta.
          </p>
        </div>

        <form onSubmit={addPrefix} className="flex gap-3 flex-wrap">
          <input type="text" placeholder="Etiqueta — ej: Campaña Cobranzas" aria-label="Etiqueta del prefijo de campaña"
            value={newPrefixLabel} onChange={e => setNewPrefixLabel(e.target.value)}
            className="flex-1 min-w-56 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-500" />
          <Button type="submit" disabled={addingPrefix} icon={<Plus size={16} />}>
            {addingPrefix ? 'Agregando...' : 'Agregar prefijo'}
          </Button>
        </form>

        {customer.prefixes.length === 0 ? (
          <p className="text-sm text-[var(--color-muted)] py-2">Sin prefijos de campaña — solo rutea por el principal.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-[var(--color-border)]">
            <table className="w-full text-sm tabular-nums">
              <thead>
                <tr className="text-xs text-[var(--color-text-2)] uppercase border-b border-[var(--color-border)] bg-[var(--color-surface)]">
                  <th className="px-4 py-2 text-left">Prefijo</th>
                  <th className="px-4 py-2 text-left">Etiqueta</th>
                  <th className="px-4 py-2 text-left">Grupo de ruteo</th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody>
                {customer.prefixes.map(p => (
                  <tr key={p.id} className="border-b border-[var(--color-border)]/50 hover:bg-white/2">
                    <td className="px-4 py-2.5 font-mono text-brand-400">{p.techprefix}</td>
                    <td className="px-4 py-2.5 text-[var(--color-text-2)]">{p.label || '—'}</td>
                    <td className="px-4 py-2.5">
                      <select
                        aria-label={`Grupo de ruteo del prefijo ${p.techprefix}`}
                        disabled={routingBusy === String(p.id)}
                        value={p.routing_group_id ?? ''}
                        onChange={e => setPrefixRoutingGroup(p.id, e.target.value)}
                        className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:border-brand-500">
                        <option value="">
                          Hereda del cliente{customer.groups.find(g => g.group_id === customer.routing_group_id)
                            ? ` (${customer.groups.find(g => g.group_id === customer.routing_group_id)!.name})`
                            : ''}
                        </option>
                        {customer.groups.map(g => (
                          <option key={g.group_id} value={g.group_id}>{g.name}</option>
                        ))}
                      </select>
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <button onClick={() => deletePrefix(p.id)} aria-label="Eliminar prefijo"
                        className="focus-ring text-[var(--color-muted)] hover:text-danger transition-colors">
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      </>
      )}

      {/* ── TAB: GENERAL (continuación) ───────────────────────────────────── */}
      {tab === 'general' && (
      <>
      {/* Acceso al portal */}
      <Card className="p-5 space-y-4">
        <div>
          <h2 className="font-semibold">Acceso al portal</h2>
          <p className="text-xs text-[var(--color-muted)] mt-0.5">
            Usuario para que el cliente acceda a <strong>/my/</strong> y vea sus CDRs, saldo y facturas.
          </p>
        </div>

        {customer.portal_user ? (
          <div className="space-y-4">
            {/* Usuario existente */}
            <div className="flex items-center gap-4 p-3 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] flex-wrap">
              <div className="w-8 h-8 rounded-full bg-brand-600/20 flex items-center justify-center text-brand-400 shrink-0">
                <UserPlus size={16} />
              </div>
              <div className="flex-1 min-w-[8rem]">
                <p className="text-sm font-medium truncate">{customer.portal_user.name}</p>
                <p className="text-xs text-[var(--color-muted)] truncate">{customer.portal_user.email}</p>
              </div>
              <button onClick={deletePortalUser} disabled={portalBusy}
                className="focus-ring flex items-center gap-1.5 text-xs text-[var(--color-muted)] hover:text-danger transition-colors disabled:opacity-50">
                <UserX size={14} /> Eliminar acceso
              </button>
            </div>

            {/* Cambiar contraseña */}
            <form onSubmit={resetPortalPassword} className="flex gap-3 items-end flex-wrap">
              <div className="flex-1 min-w-[10rem]">
                <label htmlFor="portal-reset-pass" className={labelCls}>Nueva contraseña</label>
                <input id="portal-reset-pass" type="password" minLength={6} placeholder="Mínimo 6 caracteres"
                  value={newPass} onChange={e => setNewPass(e.target.value)} required
                  className={inputCls} />
              </div>
              <Button type="submit" variant="secondary" disabled={portalBusy || !newPass} icon={<KeyRound size={14} />} className="bg-[var(--color-surface)]">
                {portalBusy ? 'Cambiando...' : 'Cambiar contraseña'}
              </Button>
            </form>
          </div>
        ) : (
          <form onSubmit={createPortalUser} className="space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label htmlFor="portal-new-name" className={labelCls}>Nombre</label>
                <input id="portal-new-name" className={inputCls} placeholder="Nombre del contacto" required
                  value={portalForm.name} onChange={e => setPortalForm(f => ({...f, name: e.target.value}))} />
              </div>
              <div>
                <label htmlFor="portal-new-email" className={labelCls}>Email (login)</label>
                <input id="portal-new-email" type="email" className={inputCls} placeholder="cliente@empresa.com" required
                  value={portalForm.email} onChange={e => setPortalForm(f => ({...f, email: e.target.value}))} />
              </div>
            </div>
            <div className="flex gap-3 items-end flex-wrap">
              <div className="flex-1 min-w-[10rem]">
                <label htmlFor="portal-new-password" className={labelCls}>Contraseña inicial</label>
                <input id="portal-new-password" type="password" minLength={6} className={inputCls} placeholder="Mínimo 6 caracteres" required
                  value={portalForm.password} onChange={e => setPortalForm(f => ({...f, password: e.target.value}))} />
              </div>
              <Button type="submit" disabled={portalBusy} icon={<UserPlus size={14} />}>
                {portalBusy ? 'Creando...' : 'Crear acceso'}
              </Button>
            </div>
          </form>
        )}
      </Card>
      </>
      )}

      {/* ── TAB: RED Y RUTEO (continuación) ───────────────────────────────── */}
      {tab === 'red' && (
      <>
      {/* Grupo de ruteo — el cliente solo selecciona entre los grupos que ya tiene
          habilitados. Habilitar/deshabilitar grupos y asignarle carriers se hace
          desde /carrier-groups (sección "Habilitar para un cliente" en el detalle
          de cada grupo) — ver problema 4 del pase de UI. */}
      <Card className="p-5 space-y-3">
        <div>
          <h2 className="font-semibold">Grupo de ruteo</h2>
          <p className="text-xs text-[var(--color-muted)] mt-0.5">
            Este cliente rutea todas sus llamadas a través de UN solo grupo de carriers por vez.
          </p>
        </div>

        <label htmlFor="routing-main-group" className={labelCls}>Grupo del prefijo principal ({customer.techprefix})</label>
        {customer.groups.length === 0 ? (
          <p className="text-sm text-warning">
            Este cliente todavía no tiene ningún grupo habilitado —{' '}
            <Link href="/carrier-groups" className="focus-ring underline hover:text-warning/80">gestionalo desde Grupos de ruteo</Link>.
          </p>
        ) : (
          <>
            <select
              id="routing-main-group"
              disabled={routingBusy === 'main'}
              value={customer.routing_group_id ?? ''}
              onChange={e => { if (e.target.value) setMainRoutingGroup(e.target.value) }}
              className={inputCls}>
              {!customer.routing_group_id && (
                <option value="" disabled>⚠ Sin ruteo — el cliente no puede llamar</option>
              )}
              {customer.groups.map(g => (
                <option key={g.group_id} value={g.group_id}>{g.name}</option>
              ))}
            </select>
            {customer.routing_group_id !== null && (
              <button type="button" onClick={cutMainRouting} disabled={routingBusy === 'main'}
                className="focus-ring text-xs text-danger hover:text-danger/80 disabled:opacity-50">
                Cortar ruteo del cliente (deja de rutear llamadas)
              </button>
            )}
          </>
        )}
      </Card>
      </>
      )}

      {/* Notas internas — visible siempre en la tab General */}
      {tab === 'general' && (
        <EntityComments entity="customer" entityId={parseInt(id)} />
      )}
    </div>
  )
}
