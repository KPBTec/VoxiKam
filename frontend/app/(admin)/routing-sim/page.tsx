'use client'
import { useEffect, useState } from 'react'
import { apiGet } from '@/lib/api'
import { Route, PlayCircle, AlertTriangle } from 'lucide-react'

interface Customer { id: number; name: string; techprefix: string }

interface RateInfo {
  prefix: string; destination: string; group_name?: string
  rateinitial?: string; buy_rate?: string; connectcharge?: string
}

interface CarrierResult {
  carrier_id: number
  carrier_name: string
  host: string
  port: number
  status: string
  priority: number
  transformed_destination: string
  buy_rate: RateInfo | null
  margin_per_minute: number | null
  would_select: boolean
}

interface SimResult {
  customer: { id: number; name: string; status: string }
  destination_input: string
  destination_normalized: string
  sell_rate: RateInfo | null
  carriers: CarrierResult[]
  warning: string | null
}

const card = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'

export default function RoutingSimPage() {
  const [customers, setCustomers] = useState<Customer[]>([])
  const [customerId, setCustomerId] = useState('')
  const [destination, setDestination] = useState('')
  const [result, setResult] = useState<SimResult | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    apiGet('/admin/customers').then(list => {
      setCustomers(list)
      if (list.length) setCustomerId(String(list[0].id))
    }).catch((e: any) => setError(e.message || 'Error cargando clientes'))
  }, [])

  async function run(e: React.FormEvent) {
    e.preventDefault()
    setRunning(true); setError(''); setResult(null)
    try {
      const p = new URLSearchParams({ customer_id: customerId, destination })
      setResult(await apiGet(`/admin/routing/simulate?${p}`))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al simular')
    } finally { setRunning(false) }
  }

  const fmt = (n: string | number | undefined) => n == null ? '—' : `S/. ${parseFloat(String(n)).toFixed(6)}`

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Routing Simulation</h1>
        <p className="text-sm text-[var(--color-text-2)] mt-1">
          Dry-run: qué carrier y qué tarifa aplicaría para un cliente y un destino — sin originar ninguna llamada.
        </p>
      </div>

      <form onSubmit={run} className={`${card} p-5`}>
        <div className="grid grid-cols-[2fr_2fr_auto] gap-3 items-end">
          <div>
            <label className="block text-xs text-[var(--color-text-2)] mb-1">Cliente</label>
            <select value={customerId} onChange={e => setCustomerId(e.target.value)}
              className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm">
              {customers.map(c => <option key={c.id} value={c.id}>{c.name} ({c.techprefix})</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs text-[var(--color-text-2)] mb-1">Destino (con o sin techprefix)</label>
            <input required value={destination} onChange={e => setDestination(e.target.value)}
              placeholder="51987654321"
              className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm" />
          </div>
          <button type="submit" disabled={running || !customerId}
            className="flex items-center gap-1.5 px-3 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-xs font-medium rounded-lg">
            <PlayCircle size={13} /> {running ? 'Simulando…' : 'Simular'}
          </button>
        </div>
        {error && <p className="text-xs text-red-400 mt-2">{error}</p>}
      </form>

      {result && (
        <>
          <div className={`${card} p-5`}>
            <div className="flex items-center gap-2 mb-3">
              <Route size={15} className="text-[var(--color-muted)]" />
              <h2 className="font-semibold text-sm">Tarifa al cliente</h2>
            </div>
            <p className="text-xs text-[var(--color-text-2)] mb-3">
              Destino normalizado (sin techprefix): <span className="font-mono text-white">{result.destination_normalized}</span>
            </p>
            {result.sell_rate ? (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                <div><p className="text-xs text-[var(--color-muted)]">Prefijo</p><p className="font-mono">{result.sell_rate.prefix}</p></div>
                <div><p className="text-xs text-[var(--color-muted)]">Destino</p><p>{result.sell_rate.destination}</p></div>
                <div><p className="text-xs text-[var(--color-muted)]">S/./min</p><p className="font-mono">{fmt(result.sell_rate.rateinitial)}</p></div>
                <div><p className="text-xs text-[var(--color-muted)]">Cargo conexión</p><p className="font-mono">{fmt(result.sell_rate.connectcharge)}</p></div>
              </div>
            ) : (
              <p className="text-sm text-red-400">Sin tarifa configurada para este destino — la llamada se rechazaría en el ingest</p>
            )}
          </div>

          {result.warning && (
            <div className="bg-red-950/40 border border-red-800/50 rounded-xl p-4 flex items-center gap-2 text-sm text-red-300">
              <AlertTriangle size={16} /> {result.warning}
            </div>
          )}

          <div className={`${card} overflow-x-auto`}>
            <div className="px-5 py-3 border-b border-[var(--color-border)]">
              <h2 className="font-semibold text-sm">Carriers asignados (orden de failover)</h2>
            </div>
            {result.carriers.length === 0 ? (
              <div className="text-[var(--color-muted)] p-8 text-center text-sm">Sin carriers asignados a este cliente</div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[var(--color-text-2)] text-xs uppercase border-b border-[var(--color-border)]">
                    <th className="px-5 py-3 text-left">Carrier</th>
                    <th className="px-5 py-3 text-center">Estado</th>
                    <th className="px-5 py-3 text-right">Prioridad</th>
                    <th className="px-5 py-3 text-left">Número transformado</th>
                    <th className="px-5 py-3 text-right">Buy rate</th>
                    <th className="px-5 py-3 text-right">Margen/min</th>
                  </tr>
                </thead>
                <tbody>
                  {result.carriers.map(c => (
                    <tr key={c.carrier_id} className={`border-b border-[var(--color-border)]/50 ${c.would_select ? 'bg-brand-600/10' : ''}`}>
                      <td className="px-5 py-2.5">
                        {c.carrier_name}
                        {c.would_select && <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded-full bg-brand-600 text-white">SE USARÍA</span>}
                      </td>
                      <td className="px-5 py-2.5 text-center">
                        <span className={`text-xs ${c.status === 'active' ? 'text-green-400' : 'text-[var(--color-muted)]'}`}>{c.status}</span>
                      </td>
                      <td className="px-5 py-2.5 text-right">{c.priority}</td>
                      <td className="px-5 py-2.5 font-mono text-xs">{c.transformed_destination}</td>
                      <td className="px-5 py-2.5 text-right font-mono">{c.buy_rate ? fmt(c.buy_rate.buy_rate) : <span className="text-red-400">sin tarifa</span>}</td>
                      <td className={`px-5 py-2.5 text-right font-mono ${c.margin_per_minute != null && c.margin_per_minute < 0 ? 'text-red-400' : 'text-green-400'}`}>
                        {c.margin_per_minute != null ? fmt(c.margin_per_minute) : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  )
}
