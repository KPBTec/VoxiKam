'use client'
import { useEffect, useMemo, useState } from 'react'
import { apiGet, apiPost, apiFetch, getErrorMessage } from '@/lib/api'
import Link from 'next/link'
import { Field } from '@/components/Field'
import { StatusBadge, carrierStatusVariant } from '@/components/StatusBadge'
import { Button } from '@/components/Button'
import { Card } from '@/components/Card'
import { Modal } from '@/components/Modal'

interface Carrier {
  id: number; name: string; host: string; port: number
  priority: number; status: string; outbound_prefix: string; notes: string
  owner_customer_id?: number | null; owner_name?: string | null
  provider_id?: number | null; provider_name?: string | null
  rate_count: number; cps_limit: number | null
}

interface Provider { id: number; name: string }

const EMPTY = { name: '', provider_id: null, host: '', port: 5060, priority: 10, outbound_prefix: '', remove_prefix: '', status: 'active', cps_limit: null, notes: '' }

export default function CarriersPage() {
  useEffect(() => { document.title = 'Carriers · VoxiKam' }, [])

  const [carriers, setCarriers] = useState<Carrier[]>([])
  const [providers, setProviders] = useState<Provider[]>([])
  const [form, setForm] = useState<any>(EMPTY)
  const [editing, setEditing] = useState<number | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [showReseller, setShowReseller] = useState(false)

  // Orden por columna — el orden que trae el backend (prioridad DESC, nombre)
  // sigue siendo el default hasta que se toca un header; a partir de ahí el
  // orden lo decide el usuario, no el servidor.
  type SortKey = 'name' | 'provider_name' | 'host' | 'port' | 'outbound_prefix' | 'priority' | 'status'
  const [sortKey, setSortKey] = useState<SortKey | null>(null)
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir(d => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortKey(key); setSortDir('asc') }
  }

  const sortedCarriers = useMemo(() => {
    if (!sortKey) return carriers
    const sign = sortDir === 'asc' ? 1 : -1
    return [...carriers].sort((a, b) => {
      const av = a[sortKey] ?? '', bv = b[sortKey] ?? ''
      if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * sign
      return String(av).localeCompare(String(bv)) * sign
    })
  }, [carriers, sortKey, sortDir])

  function SortableTh({ label, sortableKey }: { label: string; sortableKey: SortKey }) {
    const active = sortKey === sortableKey
    return (
      <th className="px-6 py-3 text-left">
        <button onClick={() => toggleSort(sortableKey)}
          className="focus-ring flex items-center gap-1 hover:text-[var(--color-text)] transition-colors">
          {label}
          <span className={`text-[10px] ${active ? 'text-brand-400' : 'text-[var(--color-muted)]/40'}`}>
            {active ? (sortDir === 'asc' ? '▲' : '▼') : '▲'}
          </span>
        </button>
      </th>
    )
  }

  const load = (withReseller = showReseller) =>
    apiGet<Carrier[]>(`/admin/carriers?include_reseller=${withReseller}`).then(setCarriers)
      .catch(e => setError(getErrorMessage(e, 'Error cargando carriers')))
  useEffect(() => { load() }, [showReseller])
  useEffect(() => { apiGet('/admin/providers').then(setProviders).catch(() => {}) }, [])

  function edit(c: Carrier) {
    setForm({ ...c }); setEditing(c.id); setShowForm(true); setError('')
  }

  async function save() {
    if (!form.name || !form.host) { setError('Nombre y Host son requeridos'); return }
    setSaving(true); setError('')
    try {
      if (editing) {
        await apiFetch(`/admin/carriers/${editing}`, { method: 'PUT', body: JSON.stringify(form) })
      } else {
        await apiPost('/admin/carriers', form)
      }
      setShowForm(false); setForm(EMPTY); setEditing(null); load()
    } catch (e) { setError(getErrorMessage(e, 'Error al guardar el carrier')) }
    finally { setSaving(false) }
  }

  async function del(id: number) {
    if (!confirm('¿Eliminar carrier?')) return
    await apiFetch(`/admin/carriers/${id}`, { method: 'DELETE' })
    load()
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-[var(--color-text)]">Carriers / Proveedores</h1>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-xs text-[var(--color-text-2)] cursor-pointer">
            <input type="checkbox" checked={showReseller} onChange={e => setShowReseller(e.target.checked)}
              className="rounded border-[var(--color-border)] bg-[var(--color-surface)]" />
            Incluir carriers de resellers
          </label>
          <Button onClick={() => { setShowForm(true); setForm(EMPTY); setEditing(null) }}>
            + Nuevo carrier
          </Button>
        </div>
      </div>

      {error && !showForm && <p className="text-danger text-sm">{error}</p>}

      {showForm && (
        <Modal onClose={() => { setShowForm(false); setEditing(null) }} labelledBy="carrier-modal-title"
          className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-2xl w-full max-w-2xl mx-4 shadow-2xl max-h-[90vh] overflow-y-auto">
        <Card className="p-6 space-y-4 rounded-none border-none">
          <h2 id="carrier-modal-title" className="font-medium text-[var(--color-text)]">{editing ? 'Editar carrier' : 'Nuevo carrier'}</h2>
          {error && <p className="text-danger text-sm">{error}</p>}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {[['Nombre', 'name', 'text'], ['Host / IP', 'host', 'text'], ['Puerto', 'port', 'number'], ['Prefijo saliente', 'outbound_prefix', 'text'], ['Prioridad', 'priority', 'number']].map(([label, key, type]) => (
              <Field
                key={key} id={`carrier-${key}`} label={label} type={type}
                value={form[key] ?? ''}
                onChange={e => setForm((f: any) => ({ ...f, [key]: type === 'number' ? +e.target.value : e.target.value }))}
                className="focus-ring w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-3 py-2 text-sm text-[var(--color-text)]"
              />
            ))}
            <div>
              <label htmlFor="carrier-new-provider" className="block text-xs text-[var(--color-text-2)] mb-1">Proveedor</label>
              <select id="carrier-new-provider" value={form.provider_id ?? ''}
                onChange={e => setForm((f: any) => ({ ...f, provider_id: e.target.value ? +e.target.value : null }))}
                className="focus-ring w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-3 py-2 text-sm text-[var(--color-text)]">
                <option value="">Sin proveedor</option>
                {providers.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="carrier-new-status" className="block text-xs text-[var(--color-text-2)] mb-1">Estado</label>
              <select id="carrier-new-status" value={form.status} onChange={e => setForm((f: any) => ({ ...f, status: e.target.value }))}
                className="focus-ring w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-3 py-2 text-sm text-[var(--color-text)]">
                <option value="active">Activo</option>
                <option value="inactive">Inactivo</option>
              </select>
            </div>
            <Field
              id="carrier-cps_limit" label="Límite CPS (vacío = sin límite)" type="number" min={1} max={65535}
              value={form.cps_limit ?? ''}
              onChange={e => setForm((f: any) => ({ ...f, cps_limit: e.target.value === '' ? null : +e.target.value }))}
              className="focus-ring w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-3 py-2 text-sm text-[var(--color-text)]"
            />
          </div>
          <Field
            id="carrier-notes" label="Notas"
            value={form.notes ?? ''} onChange={e => setForm((f: any) => ({ ...f, notes: e.target.value }))}
            className="focus-ring w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-3 py-2 text-sm text-[var(--color-text)]"
          />
          <div className="flex gap-3">
            <Button onClick={save} disabled={saving}>
              {saving ? 'Guardando…' : 'Guardar'}
            </Button>
            <Button variant="ghost" onClick={() => { setShowForm(false); setEditing(null) }}>
              Cancelar
            </Button>
          </div>
        </Card>
        </Modal>
      )}

      <Card className="overflow-x-auto">
        <table className="w-full text-sm tabular-nums">
          <thead>
            <tr className="text-xs text-[var(--color-text-2)] uppercase border-b border-[var(--color-border)]">
              <SortableTh label="Nombre" sortableKey="name" />
              <SortableTh label="Proveedor" sortableKey="provider_name" />
              <SortableTh label="Host" sortableKey="host" />
              <SortableTh label="Puerto" sortableKey="port" />
              <SortableTh label="Prefijo" sortableKey="outbound_prefix" />
              <SortableTh label="Prioridad" sortableKey="priority" />
              <SortableTh label="Estado" sortableKey="status" />
              <th className="px-6 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--color-border)]">
            {sortedCarriers.map(c => (
              <tr key={c.id} className="hover:bg-white/2">
                <td className="px-6 py-3 text-[var(--color-text)] font-medium">
                  {c.name}
                  {c.owner_customer_id && (
                    <StatusBadge variant="brand" rounded="md" tight className="ml-2 align-middle">
                      reseller: {c.owner_name || `#${c.owner_customer_id}`}
                    </StatusBadge>
                  )}
                  {c.rate_count === 0 && (
                    <StatusBadge variant="danger" rounded="md" tight className="ml-2 align-middle">
                      ⚠ sin tarifas
                    </StatusBadge>
                  )}
                </td>
                <td className="px-6 py-3 text-[var(--color-text-2)]">{c.provider_name || '—'}</td>
                <td className="px-6 py-3 font-mono text-xs text-[var(--color-text)]">{c.host}</td>
                <td className="px-6 py-3 font-mono text-xs text-[var(--color-text-2)]">{c.port}</td>
                <td className="px-6 py-3 font-mono text-xs text-[var(--color-text-2)]">{c.outbound_prefix || '—'}</td>
                <td className="px-6 py-3 font-mono text-[var(--color-text-2)]">{c.priority}</td>
                <td className="px-6 py-3">
                  <StatusBadge variant={carrierStatusVariant(c.status)}>{c.status}</StatusBadge>
                </td>
                <td className="px-6 py-3 text-right space-x-3">
                  <Link href={`/carriers/${c.id}`}
                    className={`focus-ring text-xs ${c.rate_count === 0 ? 'text-danger hover:text-danger/80 font-medium' : 'text-brand-400 hover:text-brand-300'}`}>
                    {c.rate_count === 0 ? 'Ajustar tarifas →' : 'Tarifas →'}
                  </Link>
                  <button onClick={() => edit(c)} className="focus-ring text-xs text-brand-400 hover:text-brand-300">Editar</button>
                  <button onClick={() => del(c.id)} className="focus-ring text-xs text-danger hover:text-danger/80">Eliminar</button>
                </td>
              </tr>
            ))}
            {carriers.length === 0 && (
              <tr><td colSpan={8} className="px-6 py-10 text-center text-[var(--color-muted)] text-sm">Sin carriers configurados</td></tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
