'use client'
import { useEffect, useState } from 'react'
import { apiGet, apiPut } from '@/lib/api'
import { Save, Gauge } from 'lucide-react'

const card = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'

const PRESETS = [
  { hours: 1, label: '1 hora' },
  { hours: 6, label: '6 horas' },
  { hours: 24, label: '1 día' },
  { hours: 72, label: '3 días' },
  { hours: 168, label: '7 días' },
  { hours: 24 * 30, label: '30 días' },
  { hours: 24 * 90, label: '90 días' },
  { hours: 24 * 180, label: '6 meses' },
]

export default function TrafficSamplingPage() {
  const [hours, setHours] = useState(24)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  async function load() {
    setLoading(true); setError('')
    try {
      const r = await apiGet('/admin/traffic-sampling/config')
      setHours(r.retention_hours)
    } catch (e: any) { setError(e.message || 'Error cargando configuración') }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  async function save(e: React.FormEvent) {
    e.preventDefault(); setSaving(true); setSaved(false); setError('')
    try {
      const r = await apiPut('/admin/traffic-sampling/config', { retention_hours: hours })
      if (r.ok === false) { setError(r.error); return }
      setSaved(true)
    } finally { setSaving(false) }
  }

  if (loading) return <div className="text-[var(--color-muted)] p-8">Cargando...</div>

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Retención de datos</h1>
        <p className="text-sm text-[var(--color-text-2)] mt-1">
          Cuántas horas de tráfico SIP (<a href="/traces" className="underline">Trazas SIP</a>) se conservan antes de purgarse.
          Bajarlo reduce el tamaño de la DB en tráfico de alto volumen; subirlo da más margen para investigar un incidente después de que pasó.
          Los CDRs (facturación) no se purgan nunca — son registros de facturación, no diagnóstico.
        </p>
      </div>

      <form onSubmit={save} className={`${card} p-5 space-y-4`}>
        <div className="flex items-center gap-2">
          <Gauge size={16} className="text-[var(--color-muted)]" />
          <h2 className="font-semibold text-sm">Ventana de retención</h2>
        </div>

        <div className="flex flex-wrap gap-2">
          {PRESETS.map(p => (
            <button key={p.hours} type="button" onClick={() => setHours(p.hours)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                hours === p.hours
                  ? 'bg-brand-600/20 border-brand-500 text-brand-400'
                  : 'border-[var(--color-border)] text-[var(--color-text-2)] hover:text-white'
              }`}>
              {p.label}
            </button>
          ))}
        </div>

        <div className="flex items-end gap-3">
          <div>
            <label className="block text-xs text-[var(--color-text-2)] mb-1">Horas exactas</label>
            <input type="number" min={1} max={24 * 180} value={hours}
              onChange={e => setHours(parseInt(e.target.value) || 1)}
              className="w-40 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm" />
          </div>
          <button type="submit" disabled={saving}
            className="flex items-center gap-1.5 px-3 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-xs font-medium rounded-lg">
            <Save size={13} /> {saving ? 'Guardando…' : 'Guardar'}
          </button>
          {saved && <span className="text-xs text-green-400">Guardado</span>}
        </div>
        {error && <p className="text-xs text-red-400">{error}</p>}

        <p className="text-xs text-[var(--color-muted)]">
          El purgado fino (por hora) lo hace <code>voxikam-hep.service</code> cada hora; el purgado grueso
          (por día completo, más liviano en tablas grandes) lo hace el cron nocturno de particiones.
        </p>
      </form>
    </div>
  )
}
