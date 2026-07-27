'use client'
import { useEffect, useState } from 'react'
import { apiGet } from '@/lib/api'
import { ChevronDown } from 'lucide-react'
import { ErrorBanner } from '@/components/ErrorBanner'

interface AuditRow {
  id: number
  entity: string
  entity_id: number
  field: string
  old_value: string | null
  new_value: string | null
  changed_by: string | null
  changed_at: string
}

const ENTITY_LABELS: Record<string, string> = {
  customer: 'Clientes', customer_profile: 'Perfiles', admin_user: 'Usuarios admin',
  carrier: 'Carriers', carrier_group: 'Grupos de ruteo', disconnect_policy: 'Disconnect policies',
  rate_plan: 'Tarifas', prefix: 'Prefijos', rate_plan_draft: 'Pricelists', area: 'Áreas',
  firewall_rule: 'Firewall',
  invoice: 'Facturas', invoice_settings: 'Config. facturas', alert_rule: 'Reglas de alerta',
  system_service: 'Servicios', mail_config: 'Correo', external_sync_config: 'Sync externa',
  traffic_sampling: 'Retención de datos', webhook: 'Webhooks', api_key: 'API keys',
  system_domain: 'Dominio', lan_peer: 'Entrante (LAN peers)',
}

// Mismas categorías que ya usa el sidebar admin (Sidebar.tsx) — el admin ya
// tiene ese modelo mental, no hace falta inventar uno nuevo. 19+ entidades
// en una fila de pills horizontales era demasiado; agrupado en acordeón
// vertical se navega igual que el menú principal.
const GROUPS: { label: string; entities: string[] }[] = [
  { label: 'Clientes',     entities: ['customer', 'customer_profile', 'admin_user'] },
  { label: 'Ruteo',        entities: ['carrier', 'carrier_group', 'disconnect_policy', 'lan_peer'] },
  { label: 'Tarifas',      entities: ['rate_plan', 'prefix', 'rate_plan_draft', 'area'] },
  { label: 'Seguridad',    entities: ['firewall_rule'] },
  { label: 'Facturación',  entities: ['invoice', 'invoice_settings', 'alert_rule'] },
  { label: 'Sistema',      entities: ['system_service', 'mail_config', 'external_sync_config',
                                       'traffic_sampling', 'webhook', 'api_key', 'system_domain'] },
]

export default function AuditPage() {
  const [rows, setRows]     = useState<AuditRow[]>([])
  const [entity, setEntity] = useState('')
  const [openGroup, setOpenGroup] = useState<string | null>(
    GROUPS.find(g => g.entities.includes(entity))?.label ?? null
  )
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  async function load() {
    setLoading(true); setError('')
    try {
      const p = new URLSearchParams({ limit: '150' })
      if (entity) p.set('entity', entity)
      setRows(await apiGet(`/admin/audit?${p}`))
    } catch (e: any) { setError(e.message || 'Error cargando auditoría') }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [entity]) // eslint-disable-line react-hooks/exhaustive-deps

  const card = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'

  function selectEntity(e: string) {
    setEntity(e)
    const g = GROUPS.find(g => g.entities.includes(e))
    setOpenGroup(g ? g.label : null)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Auditoría</h1>
        <p className="text-sm text-[var(--color-text-2)] mt-1">
          Cambios de configuración con impacto en servicio, dinero o seguridad — no un log de todo,
          selectivo a propósito (ver detalle en CLAUDE.md del proyecto).
        </p>
      </div>

      {error && <ErrorBanner>{error}</ErrorBanner>}

      <div className="grid grid-cols-1 lg:grid-cols-[220px_1fr] gap-4 items-start">
        {/* Filtro — mismo patrón visual de acordeón que el sidebar admin */}
        <div className={`${card} p-2 space-y-0.5`}>
          <button onClick={() => selectEntity('')}
            className={`w-full text-left px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
              entity === '' ? 'bg-brand-600 text-white' : 'text-[var(--color-text-2)] hover:bg-white/5'
            }`}>
            Todas
          </button>
          {GROUPS.map(g => {
            const isOpen = openGroup === g.label
            const hasActive = g.entities.includes(entity)
            return (
              <div key={g.label}>
                <button onClick={() => setOpenGroup(isOpen ? null : g.label)}
                  className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-semibold uppercase tracking-wider transition-colors ${
                    hasActive ? 'text-brand-400' : 'text-[var(--color-muted)] hover:text-[var(--color-text-2)]'
                  }`}>
                  {g.label}
                  <ChevronDown size={13} className={`transition-transform ${isOpen ? 'rotate-180' : ''}`} />
                </button>
                {isOpen && (
                  <div className="pl-2 pb-1 space-y-0.5">
                    {g.entities.map(e => (
                      <button key={e} onClick={() => selectEntity(e)}
                        className={`w-full text-left px-3 py-1.5 rounded-lg text-sm transition-colors ${
                          entity === e ? 'bg-brand-600/20 text-brand-400' : 'text-[var(--color-text-2)] hover:bg-white/5'
                        }`}>
                        {ENTITY_LABELS[e] ?? e}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>

        <div className={`${card} overflow-x-auto`}>
          {loading ? (
            <div className="text-[var(--color-muted)] p-8 text-center text-sm">Cargando...</div>
          ) : rows.length === 0 ? (
            <div className="text-[var(--color-muted)] p-8 text-center text-sm">Sin cambios registrados todavía</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[var(--color-text-2)] text-xs uppercase border-b border-[var(--color-border)]">
                  <th className="px-5 py-3 text-left">Fecha</th>
                  <th className="px-5 py-3 text-left">Quién</th>
                  <th className="px-5 py-3 text-left">Entidad</th>
                  <th className="px-5 py-3 text-left">Campo</th>
                  <th className="px-5 py-3 text-left">Antes</th>
                  <th className="px-5 py-3 text-left">Ahora</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(r => (
                  <tr key={r.id} className="border-b border-[var(--color-border)]/50">
                    <td className="px-5 py-2.5 text-xs text-[var(--color-muted)] whitespace-nowrap">
                      {new Date(r.changed_at).toLocaleString('es-PE')}
                    </td>
                    <td className="px-5 py-2.5">{r.changed_by ?? '—'}</td>
                    <td className="px-5 py-2.5 text-xs">
                      <span className="px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-300">{ENTITY_LABELS[r.entity] ?? r.entity}</span>
                      <span className="text-[var(--color-muted)] ml-1.5">#{r.entity_id}</span>
                    </td>
                    <td className="px-5 py-2.5 font-mono text-xs text-warning">{r.field}</td>
                    <td className="px-5 py-2.5 text-xs text-[var(--color-muted)] max-w-[160px] truncate">{r.old_value ?? '—'}</td>
                    <td className="px-5 py-2.5 text-xs max-w-[160px] truncate">{r.new_value ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}
