'use client'
import { useEffect, useState } from 'react'
import { apiGet, apiPost, apiPut, apiDelete } from '@/lib/api'
import { Plus, Pencil, Trash2, Save, X, Users } from 'lucide-react'

const MODULE_LABELS: [string, string][] = [
  ['show_calls',       'Mis llamadas'],
  ['show_quality',     'Calidad ASR'],
  ['show_reports',     'Reportes'],
  ['show_invoices',    'Facturas'],
  ['show_trunk_guide', 'Trunk Guide'],
]

interface Profile {
  id: number; name: string; description: string | null
  show_calls: boolean; show_quality: boolean; show_reports: boolean
  show_invoices: boolean; show_trunk_guide: boolean
  customers_count: number
}

const emptyForm = () => ({
  name: '', description: '',
  show_calls: true, show_quality: true, show_reports: true,
  show_invoices: false, show_trunk_guide: true,
})

export default function ProfilesPage() {
  const [profiles, setProfiles] = useState<Profile[]>([])
  const [modal, setModal]       = useState<'create' | number | null>(null)
  const [form, setForm]         = useState(emptyForm())
  const [saving, setSaving]     = useState(false)
  const [error, setError]       = useState('')

  const load = () => apiGet('/admin/profiles').then(setProfiles)
  useEffect(() => { load() }, [])

  function openCreate() { setForm(emptyForm()); setError(''); setModal('create') }

  function openEdit(p: Profile) {
    setForm({
      name: p.name, description: p.description ?? '',
      show_calls: p.show_calls, show_quality: p.show_quality,
      show_reports: p.show_reports, show_invoices: p.show_invoices,
      show_trunk_guide: p.show_trunk_guide,
    })
    setError('')
    setModal(p.id)
  }

  async function save(e: React.FormEvent) {
    e.preventDefault(); setSaving(true); setError('')
    const body = { ...form, description: form.description || null }
    try {
      if (modal === 'create') {
        await apiPost('/admin/profiles', body)
      } else {
        await apiPut(`/admin/profiles/${modal}`, body)
      }
      setModal(null); load()
    } catch (e: any) { setError(e.message) }
    finally { setSaving(false) }
  }

  async function del(p: Profile) {
    if (!confirm(`¿Eliminar perfil "${p.name}"?\nLos clientes con este perfil quedarán en modo personalizado.`)) return
    await apiDelete(`/admin/profiles/${p.id}`)
    load()
  }

  const card  = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'
  const inp   = 'w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-500'
  const label = 'block text-xs text-[var(--color-text-2)] uppercase tracking-wider mb-1'

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Perfiles de cliente</h1>
          <p className="text-sm text-[var(--color-text-2)] mt-0.5">
            Define conjuntos de módulos y asígnalos a los clientes que quieras.
          </p>
        </div>
        <button onClick={openCreate}
          className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 text-white text-sm px-4 py-2 rounded-lg transition-colors">
          <Plus size={16} /> Nuevo perfil
        </button>
      </div>

      {profiles.length === 0 ? (
        <div className={`${card} p-10 text-center text-[var(--color-muted)] text-sm`}>
          Sin perfiles. Crea uno para empezar.
        </div>
      ) : (
        <div className="grid gap-4">
          {profiles.map(p => (
            <div key={p.id} className={`${card} p-5`}>
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 mb-1">
                    <h2 className="font-semibold text-[var(--color-text)]">{p.name}</h2>
                    <span className="flex items-center gap-1 text-xs text-[var(--color-muted)]">
                      <Users size={12} /> {p.customers_count} cliente{p.customers_count !== 1 ? 's' : ''}
                    </span>
                  </div>
                  {p.description && (
                    <p className="text-sm text-[var(--color-text-2)] mb-3">{p.description}</p>
                  )}
                  <div className="flex flex-wrap gap-1.5">
                    {MODULE_LABELS.map(([key, lbl]) => (
                      <span key={key}
                        className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                          (p as any)[key]
                            ? 'bg-green-900/30 text-green-400'
                            : 'bg-zinc-800 text-zinc-500 line-through'
                        }`}>
                        {lbl}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="flex gap-2 shrink-0">
                  <button onClick={() => openEdit(p)}
                    className="p-2 rounded-lg text-[var(--color-muted)] hover:text-[var(--color-text)] hover:bg-white/5 transition-colors">
                    <Pencil size={15} />
                  </button>
                  <button onClick={() => del(p)}
                    className="p-2 rounded-lg text-[var(--color-muted)] hover:text-red-400 hover:bg-red-900/10 transition-colors">
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modal */}
      {modal !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-2xl w-full max-w-md mx-4 shadow-2xl">
            <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)]">
              <h2 className="font-semibold">{modal === 'create' ? 'Nuevo perfil' : 'Editar perfil'}</h2>
              <button onClick={() => setModal(null)}
                className="text-[var(--color-muted)] hover:text-[var(--color-text)] transition-colors">
                <X size={18} />
              </button>
            </div>

            <form onSubmit={save} className="p-6 space-y-4">
              {error && (
                <div className="bg-red-900/30 border border-red-700 text-red-300 text-xs rounded-lg px-3 py-2">
                  {error}
                </div>
              )}
              <div>
                <label className={label}>Nombre del perfil</label>
                <input className={inp} required value={form.name}
                  placeholder="ej: Básico, Premium, Solo CDRs"
                  onChange={e => setForm(f => ({...f, name: e.target.value}))} />
              </div>
              <div>
                <label className={label}>Descripción (opcional)</label>
                <input className={inp} value={form.description}
                  placeholder="Breve descripción del perfil"
                  onChange={e => setForm(f => ({...f, description: e.target.value}))} />
              </div>

              <div>
                <p className="text-xs text-[var(--color-text-2)] uppercase tracking-wider mb-3">Módulos habilitados</p>
                <div className="space-y-2">
                  {MODULE_LABELS.map(([key, lbl]) => (
                    <div key={key} className="flex items-center justify-between">
                      <span className="text-sm text-[var(--color-text-2)]">{lbl}</span>
                      <button type="button"
                        onClick={() => setForm(f => ({...f, [key]: !(f as any)[key]}))}
                        className={`relative w-10 h-5 rounded-full transition-colors ${(form as any)[key] ? 'bg-brand-600' : 'bg-zinc-700'}`}>
                        <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${(form as any)[key] ? 'translate-x-5' : 'translate-x-0.5'}`} />
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex gap-3 pt-2">
                <button type="submit" disabled={saving}
                  className="flex items-center gap-1.5 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm px-4 py-2 rounded-lg transition-colors">
                  <Save size={14} /> {saving ? 'Guardando...' : 'Guardar'}
                </button>
                <button type="button" onClick={() => setModal(null)}
                  className="text-sm px-4 py-2 rounded-lg border border-[var(--color-border)] hover:border-[var(--color-text-2)] transition-colors">
                  Cancelar
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
