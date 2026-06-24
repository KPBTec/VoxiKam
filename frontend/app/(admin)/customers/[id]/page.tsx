'use client'
import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { apiGet, apiPost, apiDelete, apiPut } from '@/lib/api'
import Link from 'next/link'
import { ArrowLeft, Plus, Trash2, Save, KeyRound, UserX, UserPlus } from 'lucide-react'

interface CustomerIP { id: number; ip: string; description: string | null }
interface CustomerCarrier { id: number; name: string; host: string; priority: number }
interface PortalUser { id: number; name: string; email: string }
interface CustomerDetail {
  id: number; name: string; company: string | null; email: string; phone: string | null
  balance: string; credit_limit: string; rate_plan_id: number | null
  profile_id: number | null; profile_name: string | null
  calllimit: number; cpslimit: number; techprefix: string; currency: string
  show_calls: boolean; show_quality: boolean; show_reports: boolean
  show_invoices: boolean; show_trunk_guide: boolean
  status: string; notes: string | null
  ips: CustomerIP[]; carriers: CustomerCarrier[]
  portal_user: PortalUser | null
}
interface Carrier { id: number; name: string; host: string }
interface RatePlan { id: number; name: string; currency: string }
interface Profile {
  id: number; name: string
  show_calls: boolean; show_quality: boolean; show_reports: boolean
  show_invoices: boolean; show_trunk_guide: boolean
}

const MODULE_LABELS: [string, string][] = [
  ['show_calls', 'Mis llamadas'], ['show_quality', 'Calidad ASR'],
  ['show_reports', 'Reportes'], ['show_invoices', 'Facturas'], ['show_trunk_guide', 'Trunk Guide'],
]

const STATUSES = ['active', 'suspended', 'expired']

export default function CustomerDetailPage() {
  const { id } = useParams<{ id: string }>()

  const [customer, setCustomer]   = useState<CustomerDetail | null>(null)
  const [carriers, setCarriers]   = useState<Carrier[]>([])
  const [ratePlans, setRatePlans] = useState<RatePlan[]>([])
  const [profiles, setProfiles]   = useState<Profile[]>([])

  // IPs
  const [newIp, setNewIp]         = useState('')
  const [newIpDesc, setNewIpDesc] = useState('')
  const [addingIp, setAddingIp]   = useState(false)

  // Carriers
  const [newCarrierId, setNewCarrierId]           = useState('')
  const [newCarrierPriority, setNewCarrierPriority] = useState('10')
  const [addingCarrier, setAddingCarrier]         = useState(false)

  // Balance
  const [balanceAmt, setBalanceAmt]         = useState('')
  const [adjustingBalance, setAdjustingBalance] = useState(false)

  // Edit info
  const [editMode, setEditMode] = useState(false)
  const [editForm, setEditForm] = useState<Partial<CustomerDetail>>({})
  const [saving, setSaving]     = useState(false)
  const [error, setError]       = useState('')

  // Portal user
  const [portalForm, setPortalForm] = useState({ name: '', email: '', password: '' })
  const [newPass, setNewPass]       = useState('')
  const [portalBusy, setPortalBusy] = useState(false)

  const load = () => apiGet(`/admin/customers/${id}`).then(setCustomer)

  useEffect(() => {
    load()
    apiGet('/admin/carriers').then(setCarriers)
    apiGet('/admin/rates/plans').then(setRatePlans)
    apiGet('/admin/profiles').then(setProfiles)
  }, [id])

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
        profile_id:      editForm.profile_id      ?? null,
        show_calls:      editForm.show_calls      ?? true,
        show_quality:    editForm.show_quality    ?? true,
        show_reports:    editForm.show_reports    ?? true,
        show_invoices:   editForm.show_invoices   ?? false,
        show_trunk_guide: editForm.show_trunk_guide ?? true,
        status:        editForm.status ?? 'active',
        notes:         editForm.notes ?? null,
      })
      setEditMode(false); load()
    } catch (e: any) { setError(e.message) }
    finally { setSaving(false) }
  }

  async function addIp(e: React.FormEvent) {
    e.preventDefault(); setAddingIp(true)
    try {
      await apiPost(`/admin/customers/${id}/ips`, { ip: newIp, description: newIpDesc || null })
      setNewIp(''); setNewIpDesc(''); load()
    } catch (e: any) { setError(e.message) }
    finally { setAddingIp(false) }
  }

  async function deleteIp(ipId: number) {
    await apiDelete(`/admin/customers/${id}/ips/${ipId}`); load()
  }

  async function addCarrier(e: React.FormEvent) {
    e.preventDefault(); setAddingCarrier(true)
    try {
      await apiPost(`/admin/customers/${id}/carriers`, {
        carrier_id: +newCarrierId, priority: +newCarrierPriority,
      })
      setNewCarrierId(''); load()
    } catch (e: any) { setError(e.message) }
    finally { setAddingCarrier(false) }
  }

  async function removeCarrier(carrierId: number) {
    await apiDelete(`/admin/customers/${id}/carriers/${carrierId}`); load()
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

  async function adjustBalance(e: React.FormEvent) {
    e.preventDefault(); setAdjustingBalance(true)
    try {
      await apiPost(`/admin/customers/${id}/balance?amount=${balanceAmt}`, {})
      setBalanceAmt(''); load()
    } catch (e: any) { setError(e.message) }
    finally { setAdjustingBalance(false) }
  }

  if (!customer) return (
    <div className="p-6 text-[var(--color-text-2)]">Cargando...</div>
  )

  const statusBadge: Record<string, string> = {
    active:    'bg-green-900/30 text-green-400',
    suspended: 'bg-yellow-900/30 text-yellow-400',
    expired:   'bg-red-900/30 text-red-400',
  }

  const cardCls = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-5'
  const inputCls = 'w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-500'
  const labelCls = 'block text-xs text-[var(--color-text-2)] uppercase tracking-wider mb-1'

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link href="/customers" className="text-[var(--color-muted)] hover:text-[var(--color-text)] transition-colors">
          <ArrowLeft size={20} />
        </Link>
        <div className="flex-1">
          <h1 className="text-2xl font-bold">{customer.name}</h1>
          <p className="text-sm text-[var(--color-text-2)]">{customer.email}</p>
        </div>
        <span className={`px-3 py-1 rounded-full text-xs font-medium ${statusBadge[customer.status] ?? ''}`}>
          {customer.status}
        </span>
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-700 text-red-300 text-sm rounded-lg px-4 py-3">
          {error}
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        {([
          ['Prefijo', customer.techprefix, 'font-mono text-brand-400'],
          ['CPS límite', customer.cpslimit.toString(), ''],
          ['Calls máx', customer.calllimit.toString(), ''],
          ['Balance', `S/. ${parseFloat(customer.balance).toFixed(2)}`, 'text-green-400'],
        ] as [string, string, string][]).map(([label, value, cls]) => (
          <div key={label} className={cardCls}>
            <p className="text-xs text-[var(--color-text-2)] uppercase tracking-wider mb-1">{label}</p>
            <p className={`text-xl font-semibold ${cls}`}>{value}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* Info del cliente */}
        <div className={`${cardCls} space-y-4`}>
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">Información</h2>
            {!editMode ? (
              <button onClick={() => setEditMode(true)}
                className="text-xs text-brand-400 hover:text-brand-300">Editar</button>
            ) : (
              <button onClick={() => setEditMode(false)}
                className="text-xs text-[var(--color-muted)] hover:text-[var(--color-text)]">Cancelar</button>
            )}
          </div>

          {!editMode ? (
            <dl className="space-y-2 text-sm">
              {([
                ['Nombre',   customer.name],
                ['Empresa',  customer.company ?? '—'],
                ['Teléfono', customer.phone ?? '—'],
                ['Prefijo',  customer.techprefix],
                ['Plan tarifa', ratePlans.find(r => r.id === customer.rate_plan_id)?.name ?? '—'],
                ['Estado',   customer.status],
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
                <div className="flex flex-wrap gap-1.5">
                  {MODULE_LABELS.map(([key, lbl]) => (
                    <span key={key} className={`text-xs px-2 py-0.5 rounded-full font-medium ${(customer as any)[key] ? 'bg-green-900/30 text-green-400' : 'bg-zinc-800 text-zinc-500 line-through'}`}>
                      {lbl}
                    </span>
                  ))}
                </div>
              </div>
            </dl>
          ) : (
            <form onSubmit={saveInfo} className="space-y-3">
              <div>
                <label className={labelCls}>Nombre</label>
                <input className={inputCls} value={editForm.name ?? ''} onChange={e => setEditForm(f => ({...f, name: e.target.value}))} required />
              </div>
              <div>
                <label className={labelCls}>Empresa</label>
                <input className={inputCls} value={editForm.company ?? ''} onChange={e => setEditForm(f => ({...f, company: e.target.value}))} />
              </div>
              <div>
                <label className={labelCls}>Teléfono</label>
                <input className={inputCls} value={editForm.phone ?? ''} onChange={e => setEditForm(f => ({...f, phone: e.target.value}))} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className={labelCls}>CPS límite</label>
                  <input type="number" className={inputCls} value={editForm.cpslimit ?? 2} onChange={e => setEditForm(f => ({...f, cpslimit: +e.target.value}))} />
                </div>
                <div>
                  <label className={labelCls}>Calls máx</label>
                  <input type="number" className={inputCls} value={editForm.calllimit ?? 10} onChange={e => setEditForm(f => ({...f, calllimit: +e.target.value}))} />
                </div>
              </div>
              <div>
                <label className={labelCls}>Plan de tarifas</label>
                <select className={inputCls} value={editForm.rate_plan_id ?? ''} onChange={e => setEditForm(f => ({...f, rate_plan_id: e.target.value ? +e.target.value : null}))}>
                  <option value="">Sin plan</option>
                  {ratePlans.map(rp => <option key={rp.id} value={rp.id}>{rp.name} ({rp.currency})</option>)}
                </select>
              </div>
              <div>
                <label className={labelCls}>Estado</label>
                <select className={inputCls} value={editForm.status ?? 'active'} onChange={e => setEditForm(f => ({...f, status: e.target.value}))}>
                  {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div>
                <label className={labelCls}>Notas</label>
                <textarea className={inputCls} rows={2} value={editForm.notes ?? ''} onChange={e => setEditForm(f => ({...f, notes: e.target.value}))} />
              </div>
              <div className="space-y-2 pt-1">
                <p className="text-xs text-[var(--color-text-2)] uppercase tracking-wider">Módulos del portal</p>
                <div>
                  <label className={labelCls}>Perfil de módulos</label>
                  <select className={inputCls}
                    value={editForm.profile_id ?? ''}
                    onChange={e => setEditForm(f => ({...f, profile_id: e.target.value ? +e.target.value : null}))}>
                    <option value="">Personalizado (módulos manuales)</option>
                    {profiles.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                </div>
                {!editForm.profile_id ? (
                  MODULE_LABELS.map(([key, lbl]) => (
                    <div key={key} className="flex items-center justify-between">
                      <span className="text-sm text-[var(--color-text-2)]">{lbl}</span>
                      <button type="button"
                        onClick={() => setEditForm(f => ({...f, [key]: !(f as any)[key]}))}
                        className={`relative w-10 h-5 rounded-full transition-colors ${(editForm as any)[key] ? 'bg-brand-600' : 'bg-zinc-700'}`}>
                        <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${(editForm as any)[key] ? 'translate-x-5' : 'translate-x-0.5'}`} />
                      </button>
                    </div>
                  ))
                ) : (
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {(() => {
                      const prof = profiles.find(p => p.id === editForm.profile_id)
                      return MODULE_LABELS.map(([key, lbl]) => (
                        <span key={key} className={`text-xs px-2 py-0.5 rounded-full font-medium ${prof && (prof as any)[key] ? 'bg-green-900/30 text-green-400' : 'bg-zinc-800 text-zinc-500 line-through'}`}>
                          {lbl}
                        </span>
                      ))
                    })()}
                  </div>
                )}
              </div>
              <div className="flex gap-3 pt-1">
                <button type="submit" disabled={saving}
                  className="flex items-center gap-1.5 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm px-4 py-2 rounded-lg transition-colors">
                  <Save size={14} /> {saving ? 'Guardando...' : 'Guardar'}
                </button>
              </div>
            </form>
          )}
        </div>

        {/* Balance */}
        <div className={`${cardCls} space-y-4`}>
          <h2 className="font-semibold">Ajustar balance</h2>
          <p className="text-sm text-[var(--color-text-2)]">
            Balance actual: <span className="text-green-400 font-semibold">S/. {parseFloat(customer.balance).toFixed(2)}</span>
          </p>
          <form onSubmit={adjustBalance} className="flex gap-3 items-end">
            <div className="flex-1">
              <label className={labelCls}>Monto (+crédito / −débito)</label>
              <input type="number" step="0.01" placeholder="ej: 50.00 o -10.00"
                value={balanceAmt} onChange={e => setBalanceAmt(e.target.value)} required
                className={inputCls} />
            </div>
            <button type="submit" disabled={adjustingBalance || !balanceAmt}
              className="bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm px-4 py-2 rounded-lg transition-colors">
              {adjustingBalance ? 'Aplicando...' : 'Aplicar'}
            </button>
          </form>
        </div>
      </div>

      {/* IPs autorizadas */}
      <div className={`${cardCls} space-y-4`}>
        <div>
          <h2 className="font-semibold">IPs autorizadas del cliente</h2>
          <p className="text-xs text-[var(--color-muted)] mt-0.5">
            IPs o CIDRs desde los que este cliente puede enviar tráfico SIP. Cada cliente tiene su propia lista.
          </p>
        </div>

        <form onSubmit={addIp} className="flex gap-3 flex-wrap">
          <input type="text" placeholder="IP o CIDR — ej: 203.0.113.10 o 10.0.0.0/24"
            value={newIp} onChange={e => setNewIp(e.target.value)} required
            className="flex-1 min-w-56 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-500" />
          <input type="text" placeholder="Descripción (opcional)"
            value={newIpDesc} onChange={e => setNewIpDesc(e.target.value)}
            className="w-48 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-500" />
          <button type="submit" disabled={addingIp}
            className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm px-4 py-2 rounded-lg transition-colors">
            <Plus size={16} /> {addingIp ? 'Agregando...' : 'Agregar IP'}
          </button>
        </form>

        {customer.ips.length === 0 ? (
          <p className="text-sm text-[var(--color-muted)] py-2">Sin IPs configuradas — el cliente no podrá registrar el trunk SIP.</p>
        ) : (
          <div className="overflow-hidden rounded-lg border border-[var(--color-border)]">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-[var(--color-text-2)] uppercase border-b border-[var(--color-border)] bg-[var(--color-surface)]">
                  <th className="px-4 py-2 text-left">IP / CIDR</th>
                  <th className="px-4 py-2 text-left">Descripción</th>
                  <th className="px-4 py-2 text-left">Agregada</th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody>
                {customer.ips.map(ip => (
                  <tr key={ip.id} className="border-b border-[var(--color-border)]/50 hover:bg-white/2">
                    <td className="px-4 py-2.5 font-mono text-brand-400">{ip.ip}</td>
                    <td className="px-4 py-2.5 text-[var(--color-text-2)]">{ip.description ?? '—'}</td>
                    <td className="px-4 py-2.5 text-[var(--color-text-2)] text-xs font-mono">
                      {(ip as any).created_at ? new Date((ip as any).created_at).toLocaleDateString() : '—'}
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <button onClick={() => deleteIp(ip.id)}
                        className="text-[var(--color-muted)] hover:text-red-400 transition-colors">
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Acceso al portal */}
      <div className={`${cardCls} space-y-4`}>
        <div>
          <h2 className="font-semibold">Acceso al portal</h2>
          <p className="text-xs text-[var(--color-muted)] mt-0.5">
            Usuario para que el cliente acceda a <strong>/my/</strong> y vea sus CDRs, saldo y facturas.
          </p>
        </div>

        {customer.portal_user ? (
          <div className="space-y-4">
            {/* Usuario existente */}
            <div className="flex items-center gap-4 p-3 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)]">
              <div className="w-8 h-8 rounded-full bg-brand-600/20 flex items-center justify-center text-brand-400 shrink-0">
                <UserPlus size={16} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{customer.portal_user.name}</p>
                <p className="text-xs text-[var(--color-muted)] truncate">{customer.portal_user.email}</p>
              </div>
              <button onClick={deletePortalUser} disabled={portalBusy}
                className="flex items-center gap-1.5 text-xs text-[var(--color-muted)] hover:text-red-400 transition-colors disabled:opacity-50">
                <UserX size={14} /> Eliminar acceso
              </button>
            </div>

            {/* Cambiar contraseña */}
            <form onSubmit={resetPortalPassword} className="flex gap-3 items-end">
              <div className="flex-1">
                <label className={labelCls}>Nueva contraseña</label>
                <input type="password" minLength={6} placeholder="Mínimo 6 caracteres"
                  value={newPass} onChange={e => setNewPass(e.target.value)} required
                  className={inputCls} />
              </div>
              <button type="submit" disabled={portalBusy || !newPass}
                className="flex items-center gap-1.5 bg-[var(--color-surface)] border border-[var(--color-border)] hover:border-brand-500 text-sm px-4 py-2 rounded-lg transition-colors disabled:opacity-50">
                <KeyRound size={14} /> {portalBusy ? 'Cambiando...' : 'Cambiar contraseña'}
              </button>
            </form>
          </div>
        ) : (
          <form onSubmit={createPortalUser} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={labelCls}>Nombre</label>
                <input className={inputCls} placeholder="Nombre del contacto" required
                  value={portalForm.name} onChange={e => setPortalForm(f => ({...f, name: e.target.value}))} />
              </div>
              <div>
                <label className={labelCls}>Email (login)</label>
                <input type="email" className={inputCls} placeholder="cliente@empresa.com" required
                  value={portalForm.email} onChange={e => setPortalForm(f => ({...f, email: e.target.value}))} />
              </div>
            </div>
            <div className="flex gap-3 items-end">
              <div className="flex-1">
                <label className={labelCls}>Contraseña inicial</label>
                <input type="password" minLength={6} className={inputCls} placeholder="Mínimo 6 caracteres" required
                  value={portalForm.password} onChange={e => setPortalForm(f => ({...f, password: e.target.value}))} />
              </div>
              <button type="submit" disabled={portalBusy}
                className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm px-4 py-2 rounded-lg transition-colors">
                <UserPlus size={14} /> {portalBusy ? 'Creando...' : 'Crear acceso'}
              </button>
            </div>
          </form>
        )}
      </div>

      {/* Carriers asignados */}
      <div className={`${cardCls} space-y-4`}>
        <div>
          <h2 className="font-semibold">Carriers de salida</h2>
          <p className="text-xs text-[var(--color-muted)] mt-0.5">
            Carriers por los que este cliente puede enrutar llamadas (Kamailio dispatcher).
          </p>
        </div>

        <form onSubmit={addCarrier} className="flex gap-3 flex-wrap">
          <select value={newCarrierId} onChange={e => setNewCarrierId(e.target.value)} required
            className="flex-1 min-w-48 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-500">
            <option value="">Seleccionar carrier...</option>
            {carriers
              .filter(c => !customer.carriers.some(cc => cc.id === c.id))
              .map(c => <option key={c.id} value={c.id}>{c.name} — {c.host}</option>)
            }
          </select>
          <div>
            <input type="number" min={1} max={100} value={newCarrierPriority}
              onChange={e => setNewCarrierPriority(e.target.value)}
              placeholder="Prio" title="Prioridad (1=mayor)"
              className="w-20 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm text-center focus:outline-none focus:border-brand-500" />
          </div>
          <button type="submit" disabled={addingCarrier || !newCarrierId}
            className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm px-4 py-2 rounded-lg transition-colors">
            <Plus size={16} /> {addingCarrier ? 'Asignando...' : 'Asignar'}
          </button>
        </form>

        {customer.carriers.length === 0 ? (
          <p className="text-sm text-[var(--color-muted)] py-2">Sin carriers asignados — las llamadas no podrán enrutarse.</p>
        ) : (
          <div className="overflow-hidden rounded-lg border border-[var(--color-border)]">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-[var(--color-text-2)] uppercase border-b border-[var(--color-border)] bg-[var(--color-surface)]">
                  <th className="px-4 py-2 text-left">Carrier</th>
                  <th className="px-4 py-2 text-left">Host</th>
                  <th className="px-4 py-2 text-center">Prioridad</th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody>
                {customer.carriers
                  .sort((a, b) => a.priority - b.priority)
                  .map(cc => (
                  <tr key={cc.id} className="border-b border-[var(--color-border)]/50 hover:bg-white/2">
                    <td className="px-4 py-2.5 font-medium">{cc.name}</td>
                    <td className="px-4 py-2.5 font-mono text-[var(--color-text-2)] text-xs">{cc.host}</td>
                    <td className="px-4 py-2.5 text-center text-[var(--color-muted)]">{cc.priority}</td>
                    <td className="px-4 py-2.5 text-right">
                      <button onClick={() => removeCarrier(cc.id)}
                        className="text-[var(--color-muted)] hover:text-red-400 transition-colors">
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
