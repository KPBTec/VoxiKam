'use client'
import { ErrorBanner } from '@/components/ErrorBanner'
import { useEffect, useState } from 'react'
import { apiGet, apiPost, apiDelete } from '@/lib/api'
import { ArrowLeft, Plus, Trash2, Layers, Hash } from 'lucide-react'
import Link from 'next/link'
import { ClickableRow } from '@/components/ClickableRow'

interface Plan   { id: number; name: string; currency: string; description: string | null; status: string }
interface Rate   { id: number; prefix: string; destination: string; group_name: string; rateinitial: number; connectcharge: number }
interface Prefix { id: number; prefix: string; destination: string; group_name: string; country: string | null; owner_customer_id: number | null; is_own: boolean | number }

const cardCls  = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'
const inputCls = 'bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm text-[var(--color-text)] focus:outline-none focus:border-brand-500'
const labelCls = 'block text-xs text-[var(--color-text-2)] uppercase tracking-wider mb-1'

export default function ResellerRates() {
  const [plans, setPlans]     = useState<Plan[]>([])
  const [prefixes, setPrefixes] = useState<Prefix[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState('')

  const [showCreate, setShowCreate] = useState(false)
  const [planForm, setPlanForm]     = useState({ name: '', currency: 'PEN', description: '' })
  const [creating, setCreating]     = useState(false)

  const [selected, setSelected] = useState<Plan | null>(null)
  const [rates, setRates]       = useState<Rate[]>([])
  const [loadingRates, setLoadingRates] = useState(false)
  const [addMode, setAddMode]   = useState<'individual' | 'group'>('individual')
  const [rateForm, setRateForm] = useState({ prefix_id: '', rateinitial: '', connectcharge: '0', initblock: '1', billingblock: '1', minimal_time_charge: '0' })
  const [savingRate, setSavingRate] = useState(false)
  const [grpForm, setGrpForm]   = useState({ group_name: '', rateinitial: '', connectcharge: '0', billingblock: '1' })
  const [savingGrpRate, setSavingGrpRate] = useState(false)

  const groups = Array.from(
    prefixes.reduce((m, p) => {
      if (p.group_name) m.set(p.group_name, (m.get(p.group_name) ?? 0) + 1)
      return m
    }, new Map<string, number>())
  ).map(([group_name, prefix_count]) => ({ group_name, prefix_count }))

  async function load() {
    setLoading(true); setError('')
    try {
      const [myPlans, pfx] = await Promise.all([
        apiGet('/reseller/rate-plans'),
        apiGet('/reseller/prefixes'),
      ])
      setPlans(myPlans); setPrefixes(pfx)
    } catch (e: any) { setError(e.message) }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  async function createPlan(e: React.FormEvent) {
    e.preventDefault(); setCreating(true); setError('')
    try {
      await apiPost('/reseller/rate-plans', planForm)
      setPlanForm({ name: '', currency: 'PEN', description: '' })
      setShowCreate(false); load()
    } catch (e: any) { setError(e.message) }
    finally { setCreating(false) }
  }

  async function openPlan(p: Plan) {
    setSelected(p); setLoadingRates(true)
    try { setRates(await apiGet(`/reseller/rate-plans/${p.id}/rates`)) }
    catch (e: any) { setError(e.message) }
    finally { setLoadingRates(false) }
  }

  async function addRate(e: React.FormEvent) {
    e.preventDefault(); if (!selected || !rateForm.prefix_id || !rateForm.rateinitial) return
    setSavingRate(true); setError('')
    try {
      await apiPost(`/reseller/rate-plans/${selected.id}/rates`, {
        prefix_id: +rateForm.prefix_id,
        rateinitial: +rateForm.rateinitial,
        connectcharge: +rateForm.connectcharge,
        initblock: +rateForm.initblock,
        billingblock: +rateForm.billingblock,
        minimal_time_charge: +rateForm.minimal_time_charge,
      })
      setRateForm({ prefix_id: '', rateinitial: '', connectcharge: '0', initblock: '60', billingblock: '60', minimal_time_charge: '0' })
      setRates(await apiGet(`/reseller/rate-plans/${selected.id}/rates`))
    } catch (e: any) { setError(e.message) }
    finally { setSavingRate(false) }
  }

  async function delRate(rid: number) {
    if (!selected) return
    await apiDelete(`/reseller/rate-plans/${selected.id}/rates/${rid}`)
    setRates(await apiGet(`/reseller/rate-plans/${selected.id}/rates`))
  }

  async function addGroupRate(e: React.FormEvent) {
    e.preventDefault(); if (!selected || !grpForm.group_name || !grpForm.rateinitial) return
    setSavingGrpRate(true); setError('')
    try {
      const res: any = await apiPost(`/reseller/rate-plans/${selected.id}/group-rates`, {
        group_name: grpForm.group_name,
        rateinitial: +grpForm.rateinitial,
        connectcharge: +grpForm.connectcharge,
        billingblock: +grpForm.billingblock,
      })
      setGrpForm({ group_name: '', rateinitial: '', connectcharge: '0', billingblock: '60' })
      setRates(await apiGet(`/reseller/rate-plans/${selected.id}/rates`))
      if (res?.updated !== undefined) alert(`Actualizado en ${res.updated} prefijos del grupo ${grpForm.group_name}`)
    } catch (e: any) { setError(e.message) }
    finally { setSavingGrpRate(false) }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-[var(--color-text)]">Tarifas propias</h1>
          <p className="text-sm text-[var(--color-text-2)] mt-0.5">Tus planes de tarifas — los que le asignás a tus sub-clientes</p>
          <Link href="/my/reseller/prefixes" className="flex items-center gap-1.5 text-xs text-[var(--color-muted)] hover:text-brand-400 transition-colors mt-1">
            <Hash size={13} /> Gestionar tus prefijos propios →
          </Link>
        </div>
        {!selected && (
          <button onClick={() => setShowCreate(v => !v)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-brand-600 hover:bg-brand-500 text-white text-sm rounded-lg">
            <Plus size={15} /> Nuevo plan
          </button>
        )}
      </div>

      {error && <ErrorBanner>{error}</ErrorBanner>}

      {showCreate && !selected && (
        <form onSubmit={createPlan} className={`${cardCls} p-5 flex flex-wrap gap-3 items-end`}>
          <div>
            <label className={labelCls}>Nombre del plan</label>
            <input required className={inputCls} value={planForm.name} onChange={e => setPlanForm(f => ({...f, name: e.target.value}))} />
          </div>
          <div>
            <label className={labelCls}>Moneda</label>
            <select className={inputCls} value={planForm.currency} onChange={e => setPlanForm(f => ({...f, currency: e.target.value}))}>
              <option>PEN</option><option>USD</option>
            </select>
          </div>
          <div className="flex-1 min-w-48">
            <label className={labelCls}>Descripción</label>
            <input className={inputCls + ' w-full'} value={planForm.description} onChange={e => setPlanForm(f => ({...f, description: e.target.value}))} />
          </div>
          <button type="submit" disabled={creating}
            className="px-4 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm rounded-lg">
            {creating ? 'Creando…' : 'Crear plan'}
          </button>
        </form>
      )}

      <div className={`${cardCls} overflow-x-auto`}>
        {selected ? (
          <div>
            <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--color-border)]">
              <button onClick={() => setSelected(null)} className="flex items-center gap-1.5 text-sm text-[var(--color-text-2)] hover:text-[var(--color-text)]">
                <ArrowLeft size={15} /> Volver a planes
              </button>
              <span className="text-sm text-[var(--color-text)] font-medium">{selected.name} ({selected.currency})</span>
            </div>

            <div className="p-5 space-y-4">
              <div className="flex items-center gap-4">
                <h3 className="text-sm font-semibold text-[var(--color-text)]">Agregar tarifa</h3>
                <div className="flex rounded-lg overflow-hidden border border-[var(--color-border)] text-xs">
                  <button onClick={() => setAddMode('group')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 transition-colors ${addMode==='group' ? 'bg-brand-600 text-white' : 'text-[var(--color-text-2)] hover:text-white'}`}>
                    <Layers size={13}/> Por grupo
                  </button>
                  <button onClick={() => setAddMode('individual')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 transition-colors ${addMode==='individual' ? 'bg-brand-600 text-white' : 'text-[var(--color-text-2)] hover:text-white'}`}>
                    <Hash size={13}/> Individual
                  </button>
                </div>
              </div>

              {addMode === 'group' ? (
                <form onSubmit={addGroupRate} className="flex gap-3 items-end flex-wrap">
                  <div className="w-52">
                    <label className={labelCls}>Grupo</label>
                    <select required value={grpForm.group_name} onChange={e => setGrpForm(f => ({...f, group_name: e.target.value}))}
                      className={`w-full ${inputCls}`}>
                      <option value="">Seleccionar grupo…</option>
                      {groups.map(g => <option key={g.group_name} value={g.group_name}>{g.group_name} ({g.prefix_count} prefijos)</option>)}
                    </select>
                  </div>
                  <div>
                    <label className={labelCls}>Tarifa/min</label>
                    <input required type="number" step="0.0001" min="0" placeholder="0.0000"
                      value={grpForm.rateinitial} onChange={e => setGrpForm(f => ({...f, rateinitial: e.target.value}))}
                      className={`w-28 ${inputCls}`} />
                  </div>
                  <div>
                    <label className={labelCls}>Cargo conexión</label>
                    <input type="number" step="0.0001" min="0" value={grpForm.connectcharge}
                      onChange={e => setGrpForm(f => ({...f, connectcharge: e.target.value}))} className={`w-28 ${inputCls}`} />
                  </div>
                  <div>
                    <label className={labelCls}>Bloque (s)</label>
                    <input type="number" min="1" value={grpForm.billingblock}
                      onChange={e => setGrpForm(f => ({...f, billingblock: e.target.value}))} className={`w-24 ${inputCls}`} />
                  </div>
                  <button type="submit" disabled={savingGrpRate}
                    className="px-4 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm rounded-lg">
                    {savingGrpRate ? 'Aplicando…' : 'Aplicar a todo el grupo'}
                  </button>
                </form>
              ) : (
                <form onSubmit={addRate} className="flex gap-3 items-end flex-wrap">
                  <div className="flex-1 min-w-48">
                    <label className={labelCls}>Prefijo / Destino</label>
                    <select required value={rateForm.prefix_id} onChange={e => setRateForm(f => ({...f, prefix_id: e.target.value}))}
                      className={`w-full ${inputCls}`}>
                      <option value="">Seleccionar…</option>
                      {prefixes.slice().sort((a, b) => a.prefix.localeCompare(b.prefix)).map(p => (
                        <option key={p.id} value={p.id}>{p.prefix} — {p.destination}{p.group_name ? ` (${p.group_name})` : ''}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className={labelCls}>Tarifa/min</label>
                    <input required type="number" step="0.0001" min="0" placeholder="0.0000"
                      value={rateForm.rateinitial} onChange={e => setRateForm(f => ({...f, rateinitial: e.target.value}))}
                      className={`w-28 ${inputCls}`} />
                  </div>
                  <div>
                    <label className={labelCls}>Cargo conexión</label>
                    <input type="number" step="0.0001" min="0" value={rateForm.connectcharge}
                      onChange={e => setRateForm(f => ({...f, connectcharge: e.target.value}))} className={`w-28 ${inputCls}`} />
                  </div>
                  <div>
                    <label className={labelCls}>Bloque inicial (s)</label>
                    <input type="number" min="1" value={rateForm.initblock}
                      onChange={e => setRateForm(f => ({...f, initblock: e.target.value}))} className={`w-24 ${inputCls}`} />
                  </div>
                  <div>
                    <label className={labelCls}>Bloque (s)</label>
                    <input type="number" min="1" value={rateForm.billingblock}
                      onChange={e => setRateForm(f => ({...f, billingblock: e.target.value}))} className={`w-24 ${inputCls}`} />
                  </div>
                  <button type="submit" disabled={savingRate}
                    className="px-4 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm rounded-lg">
                    {savingRate ? 'Guardando…' : 'Agregar / actualizar'}
                  </button>
                </form>
              )}

              {loadingRates ? (
                <p className="p-8 text-center text-[var(--color-text-2)] text-sm">Cargando…</p>
              ) : rates.length === 0 ? (
                <p className="p-8 text-center text-[var(--color-muted)] text-sm">Sin tarifas cargadas en este plan todavía.</p>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-[var(--color-text-2)] uppercase border-b border-[var(--color-border)]">
                      <th className="px-4 py-2 text-left">Prefijo</th>
                      <th className="px-4 py-2 text-left">Destino</th>
                      <th className="px-4 py-2 text-right">Tarifa/min</th>
                      <th className="px-4 py-2 text-right">Conexión</th>
                      <th className="px-4 py-2" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--color-border)]">
                    {rates.map(r => (
                      <tr key={r.id} className="hover:bg-white/2">
                        <td className="px-4 py-2 font-mono text-brand-400">{r.prefix}</td>
                        <td className="px-4 py-2 text-[var(--color-text)]">{r.destination}</td>
                        <td className="px-4 py-2 text-right font-mono">{Number(r.rateinitial).toFixed(4)}</td>
                        <td className="px-4 py-2 text-right font-mono text-[var(--color-text-2)]">{Number(r.connectcharge).toFixed(4)}</td>
                        <td className="px-4 py-2 text-right">
                          <button onClick={() => delRate(r.id)} aria-label="Eliminar tarifa" className="text-[var(--color-muted)] hover:text-red-400">
                            <Trash2 size={14} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        ) : loading ? (
          <p className="p-8 text-center text-[var(--color-text-2)] text-sm">Cargando…</p>
        ) : plans.length === 0 ? (
          <p className="p-10 text-center text-[var(--color-muted)] text-sm">Sin planes todavía — creá el primero arriba.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-[var(--color-text-2)] uppercase border-b border-[var(--color-border)]">
                <th className="px-6 py-3 text-left">Nombre</th>
                <th className="px-6 py-3 text-left">Moneda</th>
                <th className="px-6 py-3 text-left">Descripción</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              {plans.map(p => (
                <ClickableRow key={p.id} onActivate={() => openPlan(p)} className="hover:bg-white/2 cursor-pointer">
                  <td className="px-6 py-3 font-medium text-[var(--color-text)]">{p.name}</td>
                  <td className="px-6 py-3 text-[var(--color-text)]">{p.currency}</td>
                  <td className="px-6 py-3 text-[var(--color-text-2)]">{p.description || '—'}</td>
                </ClickableRow>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
