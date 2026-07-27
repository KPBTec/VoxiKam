'use client'
import { useEffect, useState } from 'react'
import { apiGet, apiPost, apiDelete, apiPut, apiFetch } from '@/lib/api'
import { Plus, Trash2, Layers, Hash, Pencil, Check, X } from 'lucide-react'
import Link from 'next/link'

interface Plan   { id: number; name: string; currency: string; status: string }
interface Rate   { id: number; prefix: string; destination: string; group_name: string; rateinitial: number; connectcharge: number; billingblock: number }
interface Prefix { id: number; prefix: string; destination: string; group_name: string; country: string }
interface Group  { group_name: string; prefix_count: number }

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

export default function RatesPage() {
  const [plans, setPlans]       = useState<Plan[]>([])
  const [sel, setSel]           = useState<number | null>(null)
  const [rates, setRates]       = useState<Rate[]>([])
  const [prefixes, setPrefixes] = useState<Prefix[]>([])
  const [groups, setGroups]     = useState<Group[]>([])
  const [addMode, setAddMode]   = useState<'group' | 'individual'>('group')

  // Nuevo plan
  const [newPlan, setNewPlan]         = useState('')
  const [newCurrency, setNewCurrency] = useState('PEN')

  // Editar plan
  const [editPlanId, setEditPlanId]   = useState<number | null>(null)
  const [editPlanName, setEditPlanName] = useState('')

  // Tarifa por grupo
  const [grpForm, setGrpForm]   = useState({ group_name: '', rateinitial: '', connectcharge: '0', billingblock: '1' })
  const [grpSaving, setGrpSaving] = useState(false)

  // Tarifa individual
  const [rateForm, setRateForm] = useState({ prefix_id: '', rateinitial: '', connectcharge: '0', billingblock: '1' })
  const [saving, setSaving]     = useState(false)

  const [error, setError] = useState('')
  const loadPlans  = () => apiGet('/admin/rates/plans').then(setPlans).catch((e: any) => setError(e.message))
  const loadPfx    = () => apiGet('/admin/rates/prefixes').then(setPrefixes).catch((e: any) => setError(e.message))
  const loadGroups = () => apiGet('/admin/rates/groups').then(setGroups).catch((e: any) => setError(e.message))
  const loadRates  = (pid: number) => apiGet(`/admin/rates/plans/${pid}/rates`).then(setRates).catch((e: any) => setError(e.message))

  useEffect(() => { loadPlans(); loadPfx(); loadGroups() }, [])
  useEffect(() => { if (sel) loadRates(sel); else setRates([]) }, [sel])

  async function createPlan() {
    if (!newPlan.trim()) return
    await apiPost('/admin/rates/plans', { name: newPlan, currency: newCurrency, description: '', status: 'active' })
    setNewPlan(''); loadPlans()
  }

  function startEditPlan(p: Plan) {
    setEditPlanId(p.id); setEditPlanName(p.name)
  }

  async function saveEditPlan(p: Plan) {
    if (!editPlanName.trim()) return
    await apiPut(`/admin/rates/plans/${p.id}`, { name: editPlanName, currency: p.currency, description: '', status: p.status })
    setEditPlanId(null); loadPlans()
  }

  async function deletePlan(pid: number) {
    if (!confirm('¿Eliminar este plan? Se borrarán todas las tarifas asociadas.')) return
    await apiDelete(`/admin/rates/plans/${pid}`)
    if (sel === pid) setSel(null)
    loadPlans()
  }

  async function addGroupRate(e: React.FormEvent) {
    e.preventDefault()
    if (!sel || !grpForm.group_name || !grpForm.rateinitial) return
    setGrpSaving(true)
    try {
      const res: any = await apiPost(`/admin/rates/plans/${sel}/group-rates`, {
        group_name:    grpForm.group_name,
        rateinitial:   +grpForm.rateinitial,
        connectcharge: +grpForm.connectcharge,
        billingblock:  +grpForm.billingblock,
      })
      setGrpForm({ group_name: '', rateinitial: '', connectcharge: '0', billingblock: '1' })
      loadRates(sel)
      if (res?.updated !== undefined) alert(`Actualizado en ${res.updated} prefijos del grupo ${grpForm.group_name}`)
    } finally { setGrpSaving(false) }
  }

  async function addRate(e: React.FormEvent) {
    e.preventDefault()
    if (!sel || !rateForm.prefix_id || !rateForm.rateinitial) return
    setSaving(true)
    try {
      await apiPost(`/admin/rates/plans/${sel}/rates`, {
        prefix_id:     +rateForm.prefix_id,
        rateinitial:   +rateForm.rateinitial,
        connectcharge: +rateForm.connectcharge,
        billingblock:  +rateForm.billingblock,
      })
      setRateForm({ prefix_id: '', rateinitial: '', connectcharge: '0', billingblock: '1' })
      loadRates(sel)
    } finally { setSaving(false) }
  }

  async function delRate(rid: number) {
    if (!sel) return
    await apiFetch(`/admin/rates/plans/${sel}/rates/${rid}`, { method: 'DELETE' })
    loadRates(sel)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Tarifas de venta</h1>
        <p className="text-sm text-[var(--color-muted)] mt-1">
          Lo que le cobras a tus clientes — asigna un plan a cada cliente en su perfil.{' '}
          <span className="text-[var(--color-text-2)]">Los costos del carrier están en cada carrier → "Buy rates".</span>
        </p>
        <Link href="/prefixes" className="flex items-center gap-1.5 text-xs text-[var(--color-muted)] hover:text-brand-400 transition-colors mt-1">
          <Hash size={13} /> Gestionar el catálogo de prefijos de destino →
        </Link>
      </div>

      {error && <div className="bg-red-900/30 border border-red-700 text-red-300 text-sm rounded-lg px-4 py-3">{error}</div>}

      {/* ── Planes + tarifas ─────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Columna planes */}
        <div className="lg:col-span-1 space-y-3">
          <h2 className="text-sm font-semibold text-[var(--color-text-2)] uppercase tracking-wider">Planes de venta</h2>

          <div className="flex gap-2">
            <input value={newPlan} onChange={e => setNewPlan(e.target.value)} placeholder="Nombre del plan"
              onKeyDown={e => e.key === 'Enter' && createPlan()}
              className={`flex-1 ${input}`} />
            <select value={newCurrency} onChange={e => setNewCurrency(e.target.value)} className={input}>
              <option>PEN</option><option>USD</option>
            </select>
          </div>
          <button onClick={createPlan} className="w-full flex items-center justify-center gap-2 bg-brand-600 hover:bg-brand-500 text-white text-sm px-3 py-2 rounded-lg transition-colors">
            <Plus size={14}/> Crear plan
          </button>

          <div className="space-y-1 pt-1">
            {plans.map(p => (
              <div key={p.id}
                className={`rounded-lg border text-sm transition-colors ${sel===p.id ? 'bg-brand-600/15 border-brand-600/30' : 'bg-[var(--color-surface)] border-[var(--color-border)]'}`}>
                {editPlanId === p.id ? (
                  <div className="flex items-center gap-1 px-3 py-2">
                    <input autoFocus value={editPlanName}
                      onChange={e => setEditPlanName(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter') saveEditPlan(p); if (e.key === 'Escape') setEditPlanId(null) }}
                      className="flex-1 min-w-0 bg-transparent text-sm focus:outline-none" />
                    <button onClick={() => saveEditPlan(p)} className="text-green-400 hover:text-green-300"><Check size={14}/></button>
                    <button onClick={() => setEditPlanId(null)} className="text-[var(--color-muted)] hover:text-[var(--color-text)]"><X size={14}/></button>
                  </div>
                ) : (
                  <div className="flex items-center">
                    <button onClick={() => setSel(p.id)} className="flex-1 text-left px-4 py-2.5">
                      <span className={sel===p.id ? 'text-brand-400' : ''}>{p.name}</span>
                      <span className="block text-xs text-[var(--color-muted)]">{p.currency}</span>
                    </button>
                    <button onClick={() => startEditPlan(p)}
                      className="p-2 text-[var(--color-muted)] hover:text-brand-400 transition-colors">
                      <Pencil size={13}/>
                    </button>
                    <button onClick={() => deletePlan(p.id)}
                      className="p-2 text-[var(--color-muted)] hover:text-red-400 transition-colors">
                      <Trash2 size={13}/>
                    </button>
                  </div>
                )}
              </div>
            ))}
            {plans.length === 0 && <p className="text-xs text-[var(--color-muted)] text-center py-4">Sin planes</p>}
          </div>
        </div>

        {/* Columna tarifas del plan */}
        <div className="lg:col-span-3 space-y-4">
          {!sel ? (
            <div className={`${card} p-10 text-center text-[var(--color-muted)] text-sm`}>
              Selecciona un plan para ver y editar sus tarifas
            </div>
          ) : (
            <>
              {/* Selector de modo */}
              <div className={`${card} p-5 space-y-4`}>
                <div className="flex items-center gap-4">
                  <h3 className="text-sm font-semibold">Agregar tarifa</h3>
                  <div className="flex rounded-lg overflow-hidden border border-[var(--color-border)] text-xs">
                    <button onClick={() => setAddMode('group')}
                      className={`flex items-center gap-1.5 px-3 py-1.5 transition-colors ${addMode==='group' ? 'bg-brand-600 text-white' : 'text-[var(--color-muted)] hover:text-[var(--color-text)]'}`}>
                      <Layers size={13}/> Por grupo
                    </button>
                    <button onClick={() => setAddMode('individual')}
                      className={`flex items-center gap-1.5 px-3 py-1.5 transition-colors ${addMode==='individual' ? 'bg-brand-600 text-white' : 'text-[var(--color-muted)] hover:text-[var(--color-text)]'}`}>
                      <Hash size={13}/> Individual
                    </button>
                  </div>
                </div>

                {addMode === 'group' ? (
                  <form onSubmit={addGroupRate} className="flex gap-3 items-end flex-wrap">
                    <div className="w-52">
                      <label className={lbl}>Grupo</label>
                      <select required value={grpForm.group_name}
                        onChange={e => setGrpForm(f => ({...f, group_name: e.target.value}))}
                        className={`w-full ${input}`}>
                        <option value="">Seleccionar grupo…</option>
                        {groups.map(g => (
                          <option key={g.group_name} value={g.group_name}>
                            {g.group_name} ({g.prefix_count} prefijos)
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className={lbl}>Tarifa/min</label>
                      <input required type="number" step="0.0001" min="0" placeholder="0.0000"
                        value={grpForm.rateinitial}
                        onChange={e => setGrpForm(f => ({...f, rateinitial: e.target.value}))}
                        className={`w-28 ${input}`} />
                    </div>
                    <div>
                      <label className={lbl}>Cargo conexión</label>
                      <input type="number" step="0.0001" min="0" placeholder="0.00"
                        value={grpForm.connectcharge}
                        onChange={e => setGrpForm(f => ({...f, connectcharge: e.target.value}))}
                        className={`w-28 ${input}`} />
                    </div>
                    <div>
                      <label className={lbl}>Bloque (seg)</label>
                      <input type="number" min="1" placeholder="60"
                        value={grpForm.billingblock}
                        onChange={e => setGrpForm(f => ({...f, billingblock: e.target.value}))}
                        className={`w-20 ${input}`} />
                    </div>
                    <button type="submit" disabled={grpSaving}
                      className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm px-4 py-2 rounded-lg transition-colors">
                      <Layers size={15}/> {grpSaving ? 'Aplicando…' : 'Aplicar al grupo'}
                    </button>
                  </form>
                ) : (
                  <form onSubmit={addRate} className="flex gap-3 items-end flex-wrap">
                    <div className="flex-1 min-w-48">
                      <label className={lbl}>Prefijo / Destino</label>
                      <select required value={rateForm.prefix_id}
                        onChange={e => setRateForm(f => ({...f, prefix_id: e.target.value}))}
                        className={`w-full ${input}`}>
                        <option value="">Seleccionar…</option>
                        {prefixes
                          .slice()
                          .sort((a, b) => a.prefix.localeCompare(b.prefix))
                          .map(p => <option key={p.id} value={p.id}>{p.prefix} — {p.destination}{p.group_name ? ` (${p.group_name})` : ''}</option>)}
                      </select>
                    </div>
                    <div>
                      <label className={lbl}>Tarifa/min</label>
                      <input required type="number" step="0.0001" min="0" placeholder="0.0000"
                        value={rateForm.rateinitial}
                        onChange={e => setRateForm(f => ({...f, rateinitial: e.target.value}))}
                        className={`w-28 ${input}`} />
                    </div>
                    <div>
                      <label className={lbl}>Cargo conexión</label>
                      <input type="number" step="0.0001" min="0" placeholder="0.00"
                        value={rateForm.connectcharge}
                        onChange={e => setRateForm(f => ({...f, connectcharge: e.target.value}))}
                        className={`w-28 ${input}`} />
                    </div>
                    <div>
                      <label className={lbl}>Bloque (seg)</label>
                      <input type="number" min="1" placeholder="60"
                        value={rateForm.billingblock}
                        onChange={e => setRateForm(f => ({...f, billingblock: e.target.value}))}
                        className={`w-20 ${input}`} />
                    </div>
                    <button type="submit" disabled={saving}
                      className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm px-4 py-2 rounded-lg transition-colors">
                      <Plus size={15}/> {saving ? 'Agregando…' : 'Agregar'}
                    </button>
                  </form>
                )}
              </div>

              {/* Tabla de tarifas agrupadas */}
              <div className={`${card} overflow-x-auto`}>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-[var(--color-text-2)] uppercase border-b border-[var(--color-border)] bg-[var(--color-surface)]">
                      <th className="px-5 py-3 text-left">Prefijo</th>
                      <th className="px-5 py-3 text-left">Destino</th>
                      <th className="px-5 py-3 text-left">Grupo</th>
                      <th className="px-5 py-3 text-right">Tarifa/min</th>
                      <th className="px-5 py-3 text-right">Conexión</th>
                      <th className="px-5 py-3 text-right">Bloque</th>
                      <th className="px-5 py-3"/>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--color-border)]">
                    {rates
                      .slice()
                      .sort((a, b) => (a.group_name || '').localeCompare(b.group_name || '') || a.prefix.localeCompare(b.prefix))
                      .map(r => (
                      <tr key={r.id} className="hover:bg-white/2">
                        <td className="px-5 py-2.5 font-mono text-brand-400">{r.prefix}</td>
                        <td className="px-5 py-2.5">{r.destination}</td>
                        <td className="px-5 py-2.5">{groupBadge(r.group_name)}</td>
                        <td className="px-5 py-2.5 text-right font-mono text-green-400">
                          S/ {(+r.rateinitial).toFixed(4)}
                        </td>
                        <td className="px-5 py-2.5 text-right font-mono text-[var(--color-muted)]">
                          S/ {(+r.connectcharge).toFixed(4)}
                        </td>
                        <td className="px-5 py-2.5 text-right text-[var(--color-muted)]">{r.billingblock}s</td>
                        <td className="px-5 py-2.5 text-right">
                          <button onClick={() => delRate(r.id)}
                            className="text-[var(--color-muted)] hover:text-red-400 transition-colors">
                            <Trash2 size={14}/>
                          </button>
                        </td>
                      </tr>
                    ))}
                    {rates.length === 0 && (
                      <tr><td colSpan={7} className="px-5 py-8 text-center text-[var(--color-muted)] text-sm">Sin tarifas en este plan</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
