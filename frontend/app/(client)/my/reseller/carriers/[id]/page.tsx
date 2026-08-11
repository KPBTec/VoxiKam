'use client'
import { ErrorBanner } from '@/components/ErrorBanner'
import { StatusBadge } from '@/components/StatusBadge'
import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { apiGet, apiPost, apiDelete } from '@/lib/api'
import Link from 'next/link'
import { ArrowLeft, Plus, Trash2, Layers, Hash } from 'lucide-react'

interface Carrier {
  id: number; name: string; host: string; port: number
  priority: number; status: string; outbound_prefix: string; remove_prefix: string; notes: string | null
}
interface BuyRate {
  id: number; prefix: string; destination: string; group_name: string
  buy_rate: number; connectcharge: number; billingblock: number
}
interface Prefix { id: number; prefix: string; destination: string; group_name: string }

const card  = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'
const input = 'w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm text-[var(--color-text)] focus-ring'
const lbl   = 'block text-xs text-[var(--color-text-2)] uppercase tracking-wider mb-1'

export default function ResellerCarrierDetail() {
  const { id } = useParams<{ id: string }>()

  const [carrier, setCarrier]   = useState<Carrier | null>(null)
  const [rates, setRates]       = useState<BuyRate[]>([])
  const [prefixes, setPrefixes] = useState<Prefix[]>([])
  const [addMode, setAddMode]   = useState<'group' | 'individual'>('group')
  const [error, setError]       = useState('')

  const [grpForm, setGrpForm]   = useState({ group_name: '', buy_rate: '', connectcharge: '0', billingblock: '1' })
  const [grpSaving, setGrpSaving] = useState(false)
  const [grpMsg, setGrpMsg] = useState('')
  const [rateForm, setRateForm] = useState({ prefix_id: '', buy_rate: '', connectcharge: '0', billingblock: '1' })
  const [rateSaving, setRateSaving] = useState(false)

  const loadCarrier = () => apiGet(`/reseller/carriers/${id}`).then(setCarrier).catch((e: any) => setError(e.message))
  const loadRates   = () => apiGet(`/reseller/carriers/${id}/rates`).then(setRates).catch((e: any) => setError(e.message))

  useEffect(() => {
    loadCarrier(); loadRates()
    apiGet('/reseller/prefixes').then(setPrefixes).catch((e: any) => setError(e.message))
  }, [id])
  useEffect(() => { document.title = `${carrier?.name ?? 'Carrier'} · VoxiKam` }, [carrier?.name])

  const groups = Array.from(
    prefixes.reduce((m, p) => {
      if (p.group_name) m.set(p.group_name, (m.get(p.group_name) ?? 0) + 1)
      return m
    }, new Map<string, number>())
  ).map(([group_name, prefix_count]) => ({ group_name, prefix_count }))

  async function addGroupRate(e: React.FormEvent) {
    e.preventDefault()
    if (!grpForm.group_name || !grpForm.buy_rate) return
    setGrpSaving(true); setError(''); setGrpMsg('')
    try {
      const res: any = await apiPost(`/reseller/carriers/${id}/group-rates`, {
        group_name: grpForm.group_name,
        buy_rate: +grpForm.buy_rate,
        connectcharge: +grpForm.connectcharge,
        billingblock: +grpForm.billingblock,
      })
      const groupName = grpForm.group_name
      setGrpForm({ group_name: '', buy_rate: '', connectcharge: '0', billingblock: '1' })
      loadRates()
      if (res?.updated !== undefined) {
        setGrpMsg(`Actualizado en ${res.updated} prefijos del grupo ${groupName}`)
        setTimeout(() => setGrpMsg(''), 3000)
      }
    } catch (e: any) { setError(e.message) }
    finally { setGrpSaving(false) }
  }

  async function addRate(e: React.FormEvent) {
    e.preventDefault()
    if (!rateForm.prefix_id || !rateForm.buy_rate) return
    setRateSaving(true); setError('')
    try {
      await apiPost(`/reseller/carriers/${id}/rates`, {
        prefix_id: +rateForm.prefix_id,
        buy_rate: +rateForm.buy_rate,
        connectcharge: +rateForm.connectcharge,
        billingblock: +rateForm.billingblock,
      })
      setRateForm({ prefix_id: '', buy_rate: '', connectcharge: '0', billingblock: '1' })
      loadRates()
    } catch (e: any) { setError(e.message) }
    finally { setRateSaving(false) }
  }

  async function delRate(rid: number) {
    await apiDelete(`/reseller/carriers/${id}/rates/${rid}`)
    loadRates()
  }

  if (!carrier && error) return <div className="p-6 text-danger">{error}</div>
  if (!carrier) return <div className="p-6 text-[var(--color-text-2)]">Cargando…</div>

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/my/reseller/carriers" aria-label="Volver" className="focus-ring text-[var(--color-text-2)] hover:text-[var(--color-text)] transition-colors">
          <ArrowLeft size={20} />
        </Link>
        <div className="flex-1">
          <h1 className="text-2xl font-bold text-[var(--color-text)]">{carrier.name}</h1>
          <p className="text-sm text-[var(--color-text-2)] font-mono">{carrier.host}:{carrier.port}</p>
        </div>
        <StatusBadge variant={carrier.status === 'active' ? 'success' : 'muted'}>{carrier.status}</StatusBadge>
      </div>

      {error && <ErrorBanner>{error}</ErrorBanner>}

      <div className={`${card} p-5 space-y-4`}>
        <div>
          <h2 className="font-semibold text-[var(--color-text)]">Tarifas de costo (buy rates)</h2>
          <p className="text-xs text-[var(--color-muted)] mt-0.5">Lo que te cobra este carrier por minuto — usado para calcular tu margen en cada llamada.</p>
        </div>

        <div className="flex rounded-lg overflow-hidden border border-[var(--color-border)] text-xs w-fit">
          <button onClick={() => setAddMode('group')}
            className={`focus-ring flex items-center gap-1.5 px-3 py-1.5 transition-colors ${addMode==='group' ? 'bg-brand-600 text-white' : 'text-[var(--color-text-2)] hover:text-white'}`}>
            <Layers size={13}/> Por grupo
          </button>
          <button onClick={() => setAddMode('individual')}
            className={`focus-ring flex items-center gap-1.5 px-3 py-1.5 transition-colors ${addMode==='individual' ? 'bg-brand-600 text-white' : 'text-[var(--color-text-2)] hover:text-white'}`}>
            <Hash size={13}/> Individual
          </button>
        </div>

        {addMode === 'group' ? (
          <form onSubmit={addGroupRate} className="flex gap-3 flex-wrap items-end">
            <div className="w-52">
              <label htmlFor="cd-grp-group" className={lbl}>Grupo</label>
              <select id="cd-grp-group" required value={grpForm.group_name} onChange={e => setGrpForm(f => ({...f, group_name: e.target.value}))} className={input}>
                <option value="">Seleccionar grupo…</option>
                {groups.map(g => <option key={g.group_name} value={g.group_name}>{g.group_name} ({g.prefix_count} prefijos)</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="cd-grp-rate" className={lbl}>Costo/min</label>
              <input id="cd-grp-rate" required type="number" step="0.0001" min="0" placeholder="0.0000" value={grpForm.buy_rate}
                onChange={e => setGrpForm(f => ({...f, buy_rate: e.target.value}))} className={`w-28 ${input}`} />
            </div>
            <div>
              <label htmlFor="cd-grp-connect" className={lbl}>Cargo conexión</label>
              <input id="cd-grp-connect" type="number" step="0.0001" min="0" value={grpForm.connectcharge}
                onChange={e => setGrpForm(f => ({...f, connectcharge: e.target.value}))} className={`w-28 ${input}`} />
            </div>
            <div>
              <label htmlFor="cd-grp-block" className={lbl}>Bloque (seg)</label>
              <input id="cd-grp-block" type="number" min="1" value={grpForm.billingblock}
                onChange={e => setGrpForm(f => ({...f, billingblock: e.target.value}))} className={`w-20 ${input}`} />
            </div>
            <button type="submit" disabled={grpSaving}
              className="focus-ring flex items-center gap-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm px-4 py-2 rounded-lg">
              <Layers size={15}/> {grpSaving ? 'Aplicando…' : 'Aplicar al grupo'}
            </button>
            {grpMsg && <span className="text-xs text-success">{grpMsg}</span>}
          </form>
        ) : (
          <form onSubmit={addRate} className="flex gap-3 flex-wrap items-end">
            <div className="flex-1 min-w-48">
              <label htmlFor="cd-rate-prefix" className={lbl}>Prefijo / Destino</label>
              <select id="cd-rate-prefix" required value={rateForm.prefix_id} onChange={e => setRateForm(f => ({...f, prefix_id: e.target.value}))} className={input}>
                <option value="">Seleccionar…</option>
                {prefixes.slice().sort((a, b) => a.prefix.localeCompare(b.prefix)).map(p => (
                  <option key={p.id} value={p.id}>{p.prefix} — {p.destination}{p.group_name ? ` (${p.group_name})` : ''}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="cd-rate-rate" className={lbl}>Costo/min</label>
              <input id="cd-rate-rate" required type="number" step="0.0001" min="0" placeholder="0.0000" value={rateForm.buy_rate}
                onChange={e => setRateForm(f => ({...f, buy_rate: e.target.value}))} className={`w-28 ${input}`} />
            </div>
            <div>
              <label htmlFor="cd-rate-connect" className={lbl}>Cargo conexión</label>
              <input id="cd-rate-connect" type="number" step="0.0001" min="0" value={rateForm.connectcharge}
                onChange={e => setRateForm(f => ({...f, connectcharge: e.target.value}))} className={`w-28 ${input}`} />
            </div>
            <div>
              <label htmlFor="cd-rate-block" className={lbl}>Bloque (seg)</label>
              <input id="cd-rate-block" type="number" min="1" value={rateForm.billingblock}
                onChange={e => setRateForm(f => ({...f, billingblock: e.target.value}))} className={`w-20 ${input}`} />
            </div>
            <button type="submit" disabled={rateSaving}
              className="focus-ring flex items-center gap-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm px-4 py-2 rounded-lg">
              <Plus size={15}/> {rateSaving ? 'Agregando…' : 'Agregar'}
            </button>
          </form>
        )}

        <div className="overflow-x-auto rounded-lg border border-[var(--color-border)]">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-[var(--color-text-2)] uppercase border-b border-[var(--color-border)] bg-[var(--color-surface)]">
                <th className="px-5 py-3 text-left">Prefijo</th>
                <th className="px-5 py-3 text-left">Destino</th>
                <th className="px-5 py-3 text-left">Grupo</th>
                <th className="px-5 py-3 text-right">Costo/min</th>
                <th className="px-5 py-3 text-right">Conexión</th>
                <th className="px-5 py-3 text-right">Bloque</th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              {rates.slice().sort((a, b) => (a.group_name || '').localeCompare(b.group_name || '') || a.prefix.localeCompare(b.prefix)).map(r => (
                <tr key={r.id} className="hover:bg-white/2">
                  <td className="px-5 py-2.5 font-mono text-brand-400">{r.prefix}</td>
                  <td className="px-5 py-2.5 text-[var(--color-text)]">{r.destination}</td>
                  <td className="px-5 py-2.5 text-[var(--color-text-2)]">{r.group_name || '—'}</td>
                  <td className="px-5 py-2.5 text-right font-mono tabular-nums text-danger">S/ {(+r.buy_rate).toFixed(4)}</td>
                  <td className="px-5 py-2.5 text-right font-mono tabular-nums text-[var(--color-text-2)]">S/ {(+r.connectcharge).toFixed(4)}</td>
                  <td className="px-5 py-2.5 text-right font-mono tabular-nums text-[var(--color-text-2)]">{r.billingblock}s</td>
                  <td className="px-5 py-2.5 text-right">
                    <button onClick={() => delRate(r.id)} aria-label="Eliminar tarifa" className="focus-ring text-[var(--color-muted)] hover:text-danger">
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
              {rates.length === 0 && (
                <tr><td colSpan={7} className="px-5 py-8 text-center text-[var(--color-muted)] text-sm">Sin tarifas de costo — aplica un grupo arriba</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
