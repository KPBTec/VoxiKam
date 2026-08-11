'use client'
import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { apiGet, apiPost, apiDelete, apiPut } from '@/lib/api'
import Link from 'next/link'
import { ArrowLeft, Plus, Trash2, Layers, Hash } from 'lucide-react'
import { EntityComments } from '@/components/EntityComments'
import { StatusBadge, carrierStatusVariant } from '@/components/StatusBadge'
import { Button } from '@/components/Button'
import { Card } from '@/components/Card'

interface Carrier {
  id: number; name: string; host: string; port: number
  priority: number; status: string; outbound_prefix: string
  remove_prefix: string; failover_id: number | null; notes: string | null
  cps_limit: number | null
}
interface BuyRate {
  id: number; prefix: string; destination: string; group_name: string
  buy_rate: number; connectcharge: number; billingblock: number
}
interface Prefix { id: number; prefix: string; destination: string; group_name: string }
interface Group  { group_name: string; prefix_count: number }

const input = 'w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-500'
const lbl   = 'block text-xs text-[var(--color-text-2)] uppercase tracking-wider mb-1'

const GROUP_COLORS: Record<string, string> = {
  'FIJO LIMA':      'bg-info-900/50 text-info-300',
  'FIJO PROVINCIA': 'bg-info-100 text-info-400',
  'MOVILES':        'bg-brand-500/15 text-brand-400',
}
function groupBadge(g: string) {
  return <span className={`px-2 py-0.5 rounded text-xs font-medium ${GROUP_COLORS[g] ?? 'bg-[var(--color-border)] text-[var(--color-muted)]'}`}>{g || '—'}</span>
}

export default function CarrierDetailPage() {
  const { id } = useParams<{ id: string }>()
  useEffect(() => { document.title = 'Carrier · VoxiKam' }, [])

  const [carrier,  setCarrier]  = useState<Carrier | null>(null)
  const [rates,    setRates]    = useState<BuyRate[]>([])
  const [prefixes, setPrefixes] = useState<Prefix[]>([])
  const [groups,   setGroups]   = useState<Group[]>([])
  const [editMode, setEditMode] = useState(false)
  const [form,     setForm]     = useState<Partial<Carrier>>({})
  const [addMode,  setAddMode]  = useState<'group' | 'individual'>('group')

  // Group rate form
  const [grpForm,    setGrpForm]    = useState({ group_name: '', buy_rate: '', connectcharge: '0', billingblock: '1' })
  const [grpSaving,  setGrpSaving]  = useState(false)

  // Individual rate form
  const [rateForm,   setRateForm]   = useState({ prefix_id: '', buy_rate: '', connectcharge: '0', billingblock: '1' })
  const [rateSaving, setRateSaving] = useState(false)

  const [saving, setSaving] = useState(false)
  const [error,  setError]  = useState('')

  const loadCarrier = () => apiGet(`/admin/carriers/${id}`).then((c: Carrier) => { setCarrier(c); setForm(c) }).catch((e: any) => setError(e.message))
  const loadRates   = () => apiGet(`/admin/carriers/${id}/rates`).then(setRates).catch((e: any) => setError(e.message))

  useEffect(() => {
    loadCarrier(); loadRates()
    apiGet('/admin/rates/prefixes').then(setPrefixes).catch((e: any) => setError(e.message))
    apiGet('/admin/rates/groups').then(setGroups).catch((e: any) => setError(e.message))
  }, [id])

  async function saveCarrier(e: React.FormEvent) {
    e.preventDefault(); setSaving(true); setError('')
    try {
      await apiPut(`/admin/carriers/${id}`, form)
      setEditMode(false); loadCarrier()
    } catch (e: any) { setError(e.message) }
    finally { setSaving(false) }
  }

  async function addGroupRate(e: React.FormEvent) {
    e.preventDefault()
    if (!grpForm.group_name || !grpForm.buy_rate) return
    setGrpSaving(true)
    try {
      const res: any = await apiPost(`/admin/carriers/${id}/group-rates`, {
        group_name:    grpForm.group_name,
        buy_rate:      +grpForm.buy_rate,
        connectcharge: +grpForm.connectcharge,
        billingblock:  +grpForm.billingblock,
      })
      setGrpForm({ group_name: '', buy_rate: '', connectcharge: '0', billingblock: '1' })
      loadRates()
      if (res?.updated !== undefined) alert(`Actualizado en ${res.updated} prefijos del grupo ${grpForm.group_name}`)
    } catch (e: any) { setError(e.message) }
    finally { setGrpSaving(false) }
  }

  async function addRate(e: React.FormEvent) {
    e.preventDefault()
    if (!rateForm.prefix_id || !rateForm.buy_rate) return
    setRateSaving(true)
    try {
      await apiPost(`/admin/carriers/${id}/rates`, {
        prefix_id:     +rateForm.prefix_id,
        buy_rate:      +rateForm.buy_rate,
        connectcharge: +rateForm.connectcharge,
        billingblock:  +rateForm.billingblock,
      })
      setRateForm({ prefix_id: '', buy_rate: '', connectcharge: '0', billingblock: '1' })
      loadRates()
    } catch (e: any) { setError(e.message) }
    finally { setRateSaving(false) }
  }

  async function delRate(rid: number) {
    await apiDelete(`/admin/carriers/${id}/rates/${rid}`)
    loadRates()
  }

  if (!carrier && error) return <div className="p-6 text-danger">{error}</div>
  if (!carrier) return <div className="p-6 text-[var(--color-text-2)]">Cargando…</div>

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link href="/carriers" aria-label="Volver" className="focus-ring text-[var(--color-muted)] hover:text-[var(--color-text)] transition-colors">
          <ArrowLeft size={20} />
        </Link>
        <div className="flex-1">
          <h1 className="text-2xl font-bold">{carrier.name}</h1>
          <p className="text-sm text-[var(--color-text-2)] font-mono">{carrier.host}:{carrier.port}</p>
        </div>
        <StatusBadge variant={carrierStatusVariant(carrier.status)} bordered>{carrier.status}</StatusBadge>
      </div>

      {error && (
        <div className="bg-danger/10 border border-danger/30 text-danger text-sm rounded-lg px-4 py-3">{error}</div>
      )}

      {/* Info del carrier */}
      <Card className="p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">Configuración</h2>
          {!editMode
            ? <button onClick={() => setEditMode(true)} className="focus-ring text-xs text-brand-400 hover:text-brand-300">Editar</button>
            : <button onClick={() => { setEditMode(false); setForm(carrier) }} className="focus-ring text-xs text-[var(--color-muted)]">Cancelar</button>
          }
        </div>

        {!editMode ? (
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-2 text-sm">
            {([
              ['Host / IP',        carrier.host],
              ['Puerto',           carrier.port.toString()],
              ['Prefijo saliente', carrier.outbound_prefix || '—'],
              ['Prioridad',        carrier.priority.toString()],
              ['Límite CPS',       carrier.cps_limit ? `${carrier.cps_limit}/seg` : 'Sin límite'],
              ['Notas',            carrier.notes || '—'],
            ] as [string, string][]).map(([k, v]) => (
              <div key={k} className="flex justify-between border-b border-[var(--color-border)]/40 pb-1">
                <dt className="text-[var(--color-text-2)]">{k}</dt>
                <dd className="font-medium font-mono tabular-nums text-xs">{v}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <form onSubmit={saveCarrier} className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {([
              ['Nombre',           'name',           'text'],
              ['Host / IP',        'host',           'text'],
              ['Puerto',           'port',           'number'],
              ['Prefijo saliente', 'outbound_prefix','text'],
              ['Prioridad',        'priority',       'number'],
            ] as [string, keyof Carrier, string][]).map(([label, key, type]) => (
              <div key={key}>
                <label htmlFor={`carrier-edit-${key}`} className={lbl}>{label}</label>
                <input id={`carrier-edit-${key}`} type={type} className={`focus-ring ${input}`} value={(form[key] as string) ?? ''}
                  onChange={e => setForm(f => ({ ...f, [key]: type === 'number' ? +e.target.value : e.target.value }))} />
              </div>
            ))}
            <div>
              <label htmlFor="carrier-edit-status" className={lbl}>Estado</label>
              <select id="carrier-edit-status" className={`focus-ring ${input}`} value={form.status ?? 'active'}
                onChange={e => setForm(f => ({ ...f, status: e.target.value }))}>
                <option value="active">Activo</option>
                <option value="inactive">Inactivo</option>
              </select>
            </div>
            <div>
              <label htmlFor="carrier-edit-cps_limit" className={lbl}>Límite CPS (vacío = sin límite)</label>
              <input id="carrier-edit-cps_limit" type="number" min={1} max={65535} className={`focus-ring ${input}`}
                value={form.cps_limit ?? ''}
                onChange={e => setForm(f => ({ ...f, cps_limit: e.target.value === '' ? null : +e.target.value }))} />
              <p className="text-[10px] text-[var(--color-muted)] mt-1">
                El excedente se encola (no se rechaza) hasta 2s antes de fallar.
              </p>
            </div>
            <div className="col-span-2">
              <label htmlFor="carrier-edit-notes" className={lbl}>Notas</label>
              <input id="carrier-edit-notes" className={`focus-ring ${input}`} value={form.notes ?? ''}
                onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} />
            </div>
            <div className="col-span-2 flex gap-3 pt-1">
              <Button type="submit" disabled={saving}>
                {saving ? 'Guardando…' : 'Guardar'}
              </Button>
            </div>
          </form>
        )}
      </Card>

      {/* Buy rates */}
      <Card className="p-5 space-y-4">
        <div>
          <h2 className="font-semibold">Tarifas de costo (buy rates)</h2>
          <p className="text-xs text-[var(--color-muted)] mt-0.5">
            Lo que te cobra este carrier por minuto — usado para calcular ganancia en cada CDR.
          </p>
        </div>

        {/* Selector modo */}
        <div className="flex items-center gap-4">
          <div className="flex rounded-lg overflow-hidden border border-[var(--color-border)] text-xs">
            <button onClick={() => setAddMode('group')}
              className={`focus-ring flex items-center gap-1.5 px-3 py-1.5 transition-colors ${addMode==='group' ? 'bg-brand-600 text-white' : 'text-[var(--color-muted)] hover:text-[var(--color-text)]'}`}>
              <Layers size={13}/> Por grupo
            </button>
            <button onClick={() => setAddMode('individual')}
              className={`focus-ring flex items-center gap-1.5 px-3 py-1.5 transition-colors ${addMode==='individual' ? 'bg-brand-600 text-white' : 'text-[var(--color-muted)] hover:text-[var(--color-text)]'}`}>
              <Hash size={13}/> Individual
            </button>
          </div>
        </div>

        {addMode === 'group' ? (
          <form onSubmit={addGroupRate} className="flex gap-3 flex-wrap items-end">
            <div className="w-52">
              <label htmlFor="grp-group_name" className={lbl}>Grupo</label>
              <select id="grp-group_name" required value={grpForm.group_name}
                onChange={e => setGrpForm(f => ({ ...f, group_name: e.target.value }))}
                className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-500">
                <option value="">Seleccionar grupo…</option>
                {groups.map(g => (
                  <option key={g.group_name} value={g.group_name}>
                    {g.group_name} ({g.prefix_count} prefijos)
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="grp-buy_rate" className={lbl}>Costo/min</label>
              <input id="grp-buy_rate" required type="number" step="0.0001" min="0" placeholder="0.0000"
                value={grpForm.buy_rate}
                onChange={e => setGrpForm(f => ({ ...f, buy_rate: e.target.value }))}
                className="w-28 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-500" />
            </div>
            <div>
              <label htmlFor="grp-connectcharge" className={lbl}>Cargo conexión</label>
              <input id="grp-connectcharge" type="number" step="0.0001" min="0" placeholder="0.00"
                value={grpForm.connectcharge}
                onChange={e => setGrpForm(f => ({ ...f, connectcharge: e.target.value }))}
                className="w-28 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-500" />
            </div>
            <div>
              <label htmlFor="grp-billingblock" className={lbl}>Bloque (seg)</label>
              <input id="grp-billingblock" type="number" min="1" placeholder="60"
                value={grpForm.billingblock}
                onChange={e => setGrpForm(f => ({ ...f, billingblock: e.target.value }))}
                className="w-20 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-500" />
            </div>
            <Button type="submit" disabled={grpSaving} icon={<Layers size={15}/>}>
              {grpSaving ? 'Aplicando…' : 'Aplicar al grupo'}
            </Button>
          </form>
        ) : (
          <form onSubmit={addRate} className="flex gap-3 flex-wrap items-end">
            <div className="flex-1 min-w-48">
              <label htmlFor="rate-prefix_id" className={lbl}>Prefijo / Destino</label>
              <select id="rate-prefix_id" required value={rateForm.prefix_id}
                onChange={e => setRateForm(f => ({ ...f, prefix_id: e.target.value }))}
                className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-500">
                <option value="">Seleccionar…</option>
                {prefixes
                  .slice()
                  .sort((a, b) => a.prefix.localeCompare(b.prefix))
                  .map(p => <option key={p.id} value={p.id}>{p.prefix} — {p.destination}{p.group_name ? ` (${p.group_name})` : ''}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="rate-buy_rate" className={lbl}>Costo/min</label>
              <input id="rate-buy_rate" required type="number" step="0.0001" min="0" placeholder="0.0000"
                value={rateForm.buy_rate}
                onChange={e => setRateForm(f => ({ ...f, buy_rate: e.target.value }))}
                className="w-28 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-500" />
            </div>
            <div>
              <label htmlFor="rate-connectcharge" className={lbl}>Cargo conexión</label>
              <input id="rate-connectcharge" type="number" step="0.0001" min="0" placeholder="0.00"
                value={rateForm.connectcharge}
                onChange={e => setRateForm(f => ({ ...f, connectcharge: e.target.value }))}
                className="w-28 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-500" />
            </div>
            <div>
              <label htmlFor="rate-billingblock" className={lbl}>Bloque (seg)</label>
              <input id="rate-billingblock" type="number" min="1" placeholder="60"
                value={rateForm.billingblock}
                onChange={e => setRateForm(f => ({ ...f, billingblock: e.target.value }))}
                className="w-20 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-500" />
            </div>
            <Button type="submit" disabled={rateSaving} icon={<Plus size={15}/>}>
              {rateSaving ? 'Agregando…' : 'Agregar'}
            </Button>
          </form>
        )}

        {/* Tabla buy rates */}
        <div className="overflow-x-auto rounded-lg border border-[var(--color-border)]">
          <table className="w-full text-sm tabular-nums">
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
              {rates
                .slice()
                .sort((a, b) => (a.group_name || '').localeCompare(b.group_name || '') || a.prefix.localeCompare(b.prefix))
                .map(r => (
                <tr key={r.id} className="hover:bg-white/2">
                  <td className="px-5 py-2.5 font-mono text-brand-400">{r.prefix}</td>
                  <td className="px-5 py-2.5">{r.destination}</td>
                  <td className="px-5 py-2.5">{groupBadge(r.group_name || '')}</td>
                  <td className="px-5 py-2.5 text-right font-mono text-danger">
                    S/ {(+r.buy_rate).toFixed(4)}
                  </td>
                  <td className="px-5 py-2.5 text-right font-mono text-[var(--color-muted)]">
                    S/ {(+r.connectcharge).toFixed(4)}
                  </td>
                  <td className="px-5 py-2.5 text-right text-[var(--color-muted)]">{r.billingblock}s</td>
                  <td className="px-5 py-2.5 text-right">
                    <button onClick={() => delRate(r.id)} aria-label="Eliminar tarifa"
                      className="focus-ring text-[var(--color-muted)] hover:text-danger transition-colors">
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
      </Card>

      <EntityComments entity="carrier" entityId={parseInt(id)} />
    </div>
  )
}
