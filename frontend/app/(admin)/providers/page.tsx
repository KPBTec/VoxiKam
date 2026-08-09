'use client'
import { useState } from 'react'
import { apiPost, apiFetch, getErrorMessage } from '@/lib/api'
import { useApiResource } from '@/lib/useApiResource'
import { Field } from '@/components/Field'
import Link from 'next/link'

interface Provider {
  id: number; name: string; notes: string | null; carrier_count: number
}

const EMPTY = { name: '', notes: '' }

export default function ProvidersPage() {
  const { data: providers, error: loadError, reload: load } =
    useApiResource<Provider[]>('/admin/providers', 'Error cargando proveedores')
  const [form, setForm]           = useState<any>(EMPTY)
  const [editing, setEditing]     = useState<number | null>(null)
  const [showForm, setShowForm]   = useState(false)
  const [saving, setSaving]       = useState(false)
  const [formError, setFormError] = useState('')
  const error = formError || loadError

  function edit(p: Provider) {
    setForm({ name: p.name, notes: p.notes ?? '' }); setEditing(p.id); setShowForm(true); setFormError('')
  }

  async function save() {
    if (!form.name) { setFormError('Nombre es requerido'); return }
    setSaving(true); setFormError('')
    try {
      if (editing) {
        await apiFetch(`/admin/providers/${editing}`, { method: 'PUT', body: JSON.stringify(form) })
      } else {
        await apiPost('/admin/providers', form)
      }
      setShowForm(false); setForm(EMPTY); setEditing(null); load()
    } catch (e) { setFormError(getErrorMessage(e, 'Error al guardar el proveedor')) }
    finally { setSaving(false) }
  }

  async function del(id: number) {
    if (!confirm('¿Eliminar proveedor? Los carriers que lo tengan asignado quedan sin proveedor.')) return
    await apiFetch(`/admin/providers/${id}`, { method: 'DELETE' })
    load()
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-[var(--color-text)]">Proveedores</h1>
        <button onClick={() => { setShowForm(true); setForm(EMPTY); setEditing(null) }}
          className="px-4 py-2 bg-brand-600 hover:bg-brand-500 text-white text-sm rounded-lg">
          + Nuevo proveedor
        </button>
      </div>

      <p className="text-sm text-[var(--color-text-2)]">
        Agrupa varios carriers/troncales del mismo proveedor real (ej. "Itelvox" con 3 rutas) — cada
        troncal sigue con su propio host y sus propias tarifas en{' '}
        <Link href="/carriers" className="underline hover:text-brand-400">Carriers</Link>, esto es
        solo para organizar y ver reportes agrupados por proveedor.
      </p>

      {error && !showForm && <p className="text-red-400 text-sm">{error}</p>}

      {showForm && (
        <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-6 space-y-4">
          <h2 className="font-medium text-[var(--color-text)]">{editing ? 'Editar proveedor' : 'Nuevo proveedor'}</h2>
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <Field
            id="provider-name" label="Nombre"
            value={form.name} onChange={e => setForm((f: any) => ({ ...f, name: e.target.value }))}
            className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-3 py-2 text-sm text-[var(--color-text)]"
          />
          <Field
            id="provider-notes" label="Notas"
            value={form.notes ?? ''} onChange={e => setForm((f: any) => ({ ...f, notes: e.target.value }))}
            className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-3 py-2 text-sm text-[var(--color-text)]"
          />
          <div className="flex gap-3">
            <button onClick={save} disabled={saving}
              className="px-4 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm rounded">
              {saving ? 'Guardando…' : 'Guardar'}
            </button>
            <button onClick={() => { setShowForm(false); setEditing(null) }}
              className="px-4 py-2 text-sm text-[var(--color-muted)] hover:text-[var(--color-text)]">
              Cancelar
            </button>
          </div>
        </div>
      )}

      <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-[var(--color-text-2)] uppercase border-b border-[var(--color-border)]">
              <th className="px-6 py-3 text-left">Nombre</th>
              <th className="px-6 py-3 text-left">Notas</th>
              <th className="px-6 py-3 text-left">Carriers</th>
              <th className="px-6 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--color-border)]">
            {(providers ?? []).map(p => (
              <tr key={p.id} className="hover:bg-white/2">
                <td className="px-6 py-3 text-[var(--color-text)] font-medium">{p.name}</td>
                <td className="px-6 py-3 text-[var(--color-text-2)]">{p.notes || '—'}</td>
                <td className="px-6 py-3 text-[var(--color-text-2)]">
                  {p.carrier_count} carrier{p.carrier_count === 1 ? '' : 's'}
                </td>
                <td className="px-6 py-3 text-right space-x-3">
                  <button onClick={() => edit(p)} className="text-xs text-brand-400 hover:text-brand-300">Editar</button>
                  <button onClick={() => del(p.id)} className="text-xs text-red-400 hover:text-red-300">Eliminar</button>
                </td>
              </tr>
            ))}
            {(providers ?? []).length === 0 && (
              <tr><td colSpan={4} className="px-6 py-10 text-center text-[var(--color-muted)] text-sm">Sin proveedores configurados</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
