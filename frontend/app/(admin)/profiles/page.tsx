'use client'
import { useEffect, useState } from 'react'
import { apiGet, apiPost, apiPut, apiDelete } from '@/lib/api'
import { Plus, Pencil, Trash2, Save, X, Users } from 'lucide-react'
import { ErrorBanner } from '@/components/ErrorBanner'
import { PermissionTree, PermissionResource } from '@/components/PermissionTree'
import { Modal } from '@/components/Modal'

interface Profile {
  id: number; name: string; description: string | null
  customers_count: number
  permissions?: Record<string, boolean>
}

const emptyForm = () => ({ name: '', description: '', permissions: {} as Record<string, boolean> })

export default function ProfilesPage() {
  const [profiles, setProfiles]   = useState<Profile[]>([])
  const [resources, setResources] = useState<PermissionResource[]>([])
  const [modal, setModal]         = useState<'create' | number | null>(null)
  const [form, setForm]           = useState(emptyForm())
  const [saving, setSaving]       = useState(false)
  const [error, setError]         = useState('')

  const load = () => apiGet('/admin/profiles').then(p => { setProfiles(p); setError('') }).catch((e: any) => setError(e.message || 'Error cargando perfiles'))
  useEffect(() => {
    load()
    apiGet('/admin/profiles/resources').then(setResources).catch((e: any) => setError(e.message || 'Error cargando el árbol de permisos'))
  }, [])

  function openCreate() { setForm(emptyForm()); setError(''); setModal('create') }

  async function openEdit(p: Profile) {
    setError('')
    try {
      const full = await apiGet(`/admin/profiles/${p.id}`)
      setForm({ name: full.name, description: full.description ?? '', permissions: full.permissions ?? {} })
      setModal(p.id)
    } catch (e: any) { setError(e.message || 'Error cargando el perfil') }
  }

  function togglePermission(key: string, val: boolean) {
    setForm(f => ({ ...f, permissions: { ...f.permissions, [key]: val } }))
  }

  async function save(e: React.FormEvent) {
    e.preventDefault(); setSaving(true); setError('')
    const body = { name: form.name, description: form.description || null, permissions: form.permissions }
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
  const inp   = 'w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus-ring'
  const label = 'block text-xs text-[var(--color-text-2)] uppercase tracking-wider mb-1'

  return (
    <div className="space-y-6">
      {error && <ErrorBanner>{error}</ErrorBanner>}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold">Perfiles de cliente</h1>
          <p className="text-sm text-[var(--color-text-2)] mt-0.5">
            Definí qué menús, submenús y secciones puede ver cada perfil, y asignalo a los clientes que quieras.
          </p>
        </div>
        <button onClick={openCreate}
          className="focus-ring flex items-center gap-2 bg-brand-600 hover:bg-brand-500 text-white text-sm px-4 py-2 rounded-lg transition-colors">
          <Plus size={16} /> Nuevo perfil
        </button>
      </div>

      {profiles.length === 0 ? (
        <div className={`${card} p-10 text-center text-[var(--color-muted)] text-sm`}>
          Sin perfiles. Crea uno para empezar.
        </div>
      ) : (
        <div className={`${card} overflow-hidden divide-y divide-[var(--color-border)]`}>
          {profiles.map(p => (
            <div key={p.id} className="flex items-center justify-between gap-3 px-5 py-4">
              <div className="min-w-0">
                <h2 className="font-semibold text-[var(--color-text)] truncate">{p.name}</h2>
                {p.description && (
                  <p className="text-sm text-[var(--color-text-2)] truncate mt-0.5">{p.description}</p>
                )}
                <span className="flex items-center gap-1 text-xs text-[var(--color-muted)] mt-1">
                  <Users size={12} /> {p.customers_count} cliente{p.customers_count !== 1 ? 's' : ''}
                </span>
              </div>
              <div className="flex gap-1 shrink-0">
                <button onClick={() => openEdit(p)}
                  className="focus-ring flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-brand-400 hover:bg-white/5 transition-colors">
                  <Pencil size={14} /> Editar
                </button>
                <button onClick={() => del(p)} aria-label="Eliminar perfil"
                  className="focus-ring p-2 rounded-lg text-[var(--color-muted)] hover:text-danger hover:bg-danger/10 transition-colors">
                  <Trash2 size={15} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modal */}
      {modal !== null && (
        <Modal onClose={() => setModal(null)} labelledBy="profile-modal-title"
          className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-2xl w-full max-w-md mx-4 shadow-2xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)] sticky top-0 bg-[var(--color-card)]">
              <h2 id="profile-modal-title" className="font-semibold">{modal === 'create' ? 'Nuevo perfil' : 'Editar perfil'}</h2>
              <button onClick={() => setModal(null)} aria-label="Cerrar"
                className="focus-ring text-[var(--color-muted)] hover:text-[var(--color-text)] transition-colors">
                <X size={18} />
              </button>
            </div>

            <form onSubmit={save} className="p-6 space-y-4">
              {error && <ErrorBanner>{error}</ErrorBanner>}
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
                <p className="text-xs text-[var(--color-text-2)] uppercase tracking-wider mb-3">Menús de cliente</p>
                <PermissionTree resources={resources} value={form.permissions} onChange={togglePermission}
                  sectionFilter={r => !r.resource_key.startsWith('reseller_')} />
              </div>

              <div>
                <p className="text-xs text-[var(--color-text-2)] uppercase tracking-wider mb-3">Menús de reseller</p>
                <p className="text-xs text-[var(--color-muted)] -mt-2 mb-3">Solo tienen efecto en clientes convertidos en reseller.</p>
                <PermissionTree resources={resources} value={form.permissions} onChange={togglePermission}
                  sectionFilter={r => r.resource_key.startsWith('reseller_')} />
              </div>

              <div className="flex gap-3 pt-2">
                <button type="submit" disabled={saving}
                  className="focus-ring flex items-center gap-1.5 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm px-4 py-2 rounded-lg transition-colors">
                  <Save size={14} /> {saving ? 'Guardando...' : 'Guardar'}
                </button>
                <button type="button" onClick={() => setModal(null)}
                  className="focus-ring text-sm px-4 py-2 rounded-lg border border-[var(--color-border)] hover:border-[var(--color-text-2)] transition-colors">
                  Cancelar
                </button>
              </div>
            </form>
        </Modal>
      )}
    </div>
  )
}
