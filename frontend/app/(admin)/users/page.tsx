'use client'
import { useEffect, useState } from 'react'
import { apiGet, apiPost, apiPut, getErrorMessage } from '@/lib/api'
import { UserPlus, KeyRound, UserX, UserCheck } from 'lucide-react'
import { StatusBadge } from '@/components/StatusBadge'
import { ErrorBanner } from '@/components/ErrorBanner'
import { Field } from '@/components/Field'

interface AdminUser {
  id: number
  name: string
  email: string
  is_active: boolean
  is_superadmin: boolean
  created_at: string
}

export default function AdminUsersPage() {
  const [users, setUsers]     = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState('')
  // AuthUser (localStorage) no trae id — se pide una vez a /auth/me, que sí
  // devuelve la fila completa de `users` (mismo endpoint que ya existía).
  const [meId, setMeId] = useState<number | null>(null)

  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const [creating, setCreating] = useState(false)

  const [pwFor, setPwFor]   = useState<number | null>(null)
  const [pwValue, setPwValue] = useState('')

  async function load() {
    setLoading(true); setError('')
    try {
      const [list, me] = await Promise.all([
        apiGet<AdminUser[]>('/admin/users'),
        apiGet<{ id: number }>('/auth/me'),
      ])
      setUsers(list)
      setMeId(me.id)
    } catch (e) { setError(getErrorMessage(e, 'Error cargando usuarios')) }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  async function createAdmin(e: React.FormEvent) {
    e.preventDefault(); setCreating(true); setError('')
    try {
      await apiPost('/admin/users', form)
      setForm({ name: '', email: '', password: '' })
      load()
    } catch (e) { setError(getErrorMessage(e, 'Error al crear el usuario')) }
    finally { setCreating(false) }
  }

  async function toggleActive(u: AdminUser) {
    setError('')
    try {
      await apiPut(`/admin/users/${u.id}/active`, { is_active: !u.is_active })
      load()
    } catch (e) { setError(getErrorMessage(e, 'Error al cambiar el estado')) }
  }

  async function savePassword(uid: number) {
    setError('')
    try {
      await apiPut(`/admin/users/${uid}/password`, { password: pwValue })
      setPwFor(null); setPwValue('')
    } catch (e) { setError(getErrorMessage(e, 'Error al guardar la contraseña')) }
  }

  const card = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'

  if (loading) return <div className="text-[var(--color-muted)] p-8">Cargando...</div>

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Usuarios admin</h1>
        <p className="text-sm text-[var(--color-text-2)] mt-1">
          Cada persona con su propia cuenta — antes solo existía el admin único creado al instalar.
        </p>
      </div>

      {error && <ErrorBanner>{error}</ErrorBanner>}

      <form onSubmit={createAdmin} className={`${card} p-5 grid grid-cols-4 gap-3 items-end`}>
        <Field
          id="new-user-name" label="Nombre" required
          value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
        />
        <Field
          id="new-user-email" label="Email" type="email" required
          value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
        />
        <Field
          id="new-user-password" label="Contraseña" type="password" required minLength={8}
          value={form.password} onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
        />
        <button type="submit" disabled={creating}
          className="flex items-center justify-center gap-1.5 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm font-medium rounded-lg">
          <UserPlus size={15} /> {creating ? 'Creando…' : 'Crear usuario'}
        </button>
      </form>

      <div className={`${card} overflow-x-auto`}>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[var(--color-text-2)] text-xs uppercase border-b border-[var(--color-border)]">
              <th className="px-5 py-3 text-left">Nombre</th>
              <th className="px-5 py-3 text-left">Email</th>
              <th className="px-5 py-3 text-left">Estado</th>
              <th className="px-5 py-3 text-left">Creado</th>
              <th className="px-5 py-3 text-right">Acciones</th>
            </tr>
          </thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id} className="border-b border-[var(--color-border)]/50">
                <td className="px-5 py-3 font-medium">
                  {u.name} {u.id === meId && <span className="text-xs text-[var(--color-muted)]">(vos)</span>}
                  {u.is_superadmin && (
                    <span className="ml-2 px-2 py-0.5 rounded-full text-[10px] font-medium bg-brand-600/20 text-brand-400">Super admin</span>
                  )}
                </td>
                <td className="px-5 py-3 text-[var(--color-text-2)]">{u.email}</td>
                <td className="px-5 py-3">
                  <StatusBadge variant={u.is_active ? 'success' : 'muted'}>
                    {u.is_active ? 'Activo' : 'Inactivo'}
                  </StatusBadge>
                </td>
                <td className="px-5 py-3 text-xs text-[var(--color-muted)]">{new Date(u.created_at).toLocaleDateString('es-PE')}</td>
                <td className="px-5 py-3">
                  <div className="flex items-center justify-end gap-2">
                    {pwFor === u.id ? (
                      <>
                        <input
                          type="password" autoFocus minLength={8} placeholder="Nueva contraseña"
                          aria-label={`Nueva contraseña para ${u.name}`}
                          value={pwValue} onChange={e => setPwValue(e.target.value)}
                          className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-2 py-1 text-xs w-36"
                        />
                        <button onClick={() => savePassword(u.id)} className="text-xs text-brand-400 hover:text-brand-300">Guardar</button>
                        <button onClick={() => { setPwFor(null); setPwValue('') }} className="text-xs text-[var(--color-muted)]">Cancelar</button>
                      </>
                    ) : (
                      <button
                        onClick={() => setPwFor(u.id)}
                        disabled={u.is_superadmin && u.id !== meId}
                        title={u.is_superadmin && u.id !== meId ? 'Solo el super admin puede cambiar su propia contraseña' : ''}
                        className="flex items-center gap-1 text-xs text-[var(--color-text-2)] hover:text-[var(--color-text)] disabled:opacity-30 disabled:cursor-not-allowed"
                      >
                        <KeyRound size={13} /> Contraseña
                      </button>
                    )}
                    <button
                      onClick={() => toggleActive(u)}
                      disabled={(u.id === meId && u.is_active) || u.is_superadmin}
                      title={u.is_superadmin ? 'El super admin no puede ser desactivado' : (u.id === meId && u.is_active ? 'No podés desactivar tu propia cuenta' : '')}
                      className={`flex items-center gap-1 text-xs disabled:opacity-30 disabled:cursor-not-allowed ${u.is_active ? 'text-orange-400 hover:text-orange-300' : 'text-green-400 hover:text-green-300'}`}
                    >
                      {u.is_active ? <><UserX size={13} /> Desactivar</> : <><UserCheck size={13} /> Activar</>}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
