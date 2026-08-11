'use client'
import { useEffect, useState } from 'react'
import { apiPut, getErrorMessage } from '@/lib/api'

const card  = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'
const inp   = 'w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus-ring'
const label = 'block text-xs text-[var(--color-text-2)] uppercase tracking-wider mb-1'

// Compartido entre /account (admin) y /my/account (cliente) — el endpoint
// PUT /auth/me/password no depende del rol, solo de quién está logueado.
export function AccountSettings() {
  const [current, setCurrent]   = useState('')
  const [next, setNext]         = useState('')
  const [confirm, setConfirm]   = useState('')
  const [saving, setSaving]     = useState(false)
  const [saved, setSaved]       = useState(false)
  const [error, setError]       = useState('')

  useEffect(() => { document.title = 'Mi cuenta · VoxiKam' }, [])

  async function submit(e: React.FormEvent) {
    e.preventDefault(); setError(''); setSaved(false)
    if (next.length < 8) { setError('La contraseña nueva debe tener al menos 8 caracteres'); return }
    if (next !== confirm) { setError('Las contraseñas no coinciden'); return }
    setSaving(true)
    try {
      await apiPut('/auth/me/password', { current_password: current, new_password: next })
      setCurrent(''); setNext(''); setConfirm('')
      setSaved(true)
      setTimeout(() => setSaved(false), 4000)
    } catch (e: any) {
      setError(getErrorMessage(e, 'No se pudo cambiar la contraseña'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-[var(--color-text)]">Mi cuenta</h1>
        <p className="text-sm text-[var(--color-text-2)] mt-0.5">Cambiá tu contraseña de acceso al panel.</p>
      </div>

      <form onSubmit={submit} className={`${card} p-5 space-y-4 max-w-md`}>
        {error && <p className="text-xs text-danger bg-danger/10 border border-danger/30 rounded-lg px-3 py-2">{error}</p>}
        {saved && <p className="text-xs text-success bg-success/10 border border-success/30 rounded-lg px-3 py-2">Contraseña actualizada</p>}

        <div>
          <label htmlFor="acc-current" className={label}>Contraseña actual</label>
          <input id="acc-current" type="password" required value={current}
            onChange={e => setCurrent(e.target.value)} className={inp} />
        </div>
        <div>
          <label htmlFor="acc-next" className={label}>Contraseña nueva</label>
          <input id="acc-next" type="password" required minLength={8} value={next}
            onChange={e => setNext(e.target.value)} className={inp} />
        </div>
        <div>
          <label htmlFor="acc-confirm" className={label}>Confirmar contraseña nueva</label>
          <input id="acc-confirm" type="password" required minLength={8} value={confirm}
            onChange={e => setConfirm(e.target.value)} className={inp} />
        </div>

        <button type="submit" disabled={saving}
          className="focus-ring flex items-center gap-1.5 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm px-4 py-2 rounded-lg transition-colors">
          {saving ? 'Guardando…' : 'Cambiar contraseña'}
        </button>
      </form>
    </div>
  )
}
