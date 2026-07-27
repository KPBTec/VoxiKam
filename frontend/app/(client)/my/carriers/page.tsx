'use client'
import { ErrorBanner } from '@/components/ErrorBanner'
import { useEffect, useState } from 'react'
import { apiGet, apiPut } from '@/lib/api'
import { Route } from 'lucide-react'

interface GroupOption { label: string }
interface Prefix {
  prefix_ref: string
  label: string
  active_group_label: string | null
}

const cardCls  = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'
const selectCls = 'bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm text-[var(--color-text)] focus:outline-none focus:border-brand-500'

export default function MyCarriersPage() {
  const [groups, setGroups]     = useState<GroupOption[]>([])
  const [prefixes, setPrefixes] = useState<Prefix[]>([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState('')
  const [saving, setSaving]     = useState<string | null>(null)

  const load = () =>
    Promise.all([apiGet('/my/carrier-groups'), apiGet('/my/prefixes')])
      .then(([g, p]) => { setGroups(g); setPrefixes(p); setError('') })
      .catch((e: any) => setError(e.message))
      .finally(() => setLoading(false))
  useEffect(() => { load() }, [])

  async function choose(prefixRef: string, groupLabel: string) {
    // Para el prefijo principal, group_label vacío corta el ruteo por completo
    // (no hay fallback automático) — para prefijos de campaña, vacío solo
    // significa "heredá el grupo del principal", que es seguro.
    if (prefixRef === 'main' && !groupLabel) {
      if (!confirm('¿Cortar tu ruteo? Vas a DEJAR DE HACER/RECIBIR LLAMADAS por completo hasta que elijas un grupo de nuevo.')) return
    }
    setSaving(prefixRef); setError('')
    try {
      await apiPut(`/my/prefixes/${prefixRef}/group`, { group_label: groupLabel || null })
      await load()
    } catch (e: any) { setError(e.message) }
    finally { setSaving(null) }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-[var(--color-text)] flex items-center gap-2">
          <Route size={20} className="text-brand-500" /> Mis carriers
        </h1>
        <p className="text-sm text-[var(--color-text-2)] mt-0.5">
          Elegí qué grupo atiende las llamadas de cada prefijo. En prefijos de campaña,
          "Automático" hereda el grupo de tu prefijo principal. En el prefijo principal no
          hay reparto automático — si lo dejás sin grupo, tu cuenta deja de rutear llamadas.
        </p>
      </div>

      {error && <ErrorBanner>{error}</ErrorBanner>}

      {!loading && groups.length === 0 && (
        <div className={`${cardCls} px-6 py-10 text-center text-[var(--color-muted)] text-sm`}>
          Todavía no tenés grupos de ruteo habilitados — contactá a soporte.
        </div>
      )}

      {groups.length > 0 && (
        <div className={`${cardCls} overflow-x-auto`}>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-[var(--color-text-2)] uppercase border-b border-[var(--color-border)]">
                <th className="px-6 py-3 text-left">Prefijo</th>
                <th className="px-6 py-3 text-left">Grupo activo</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              {prefixes.map(p => {
                const isMain = p.prefix_ref === 'main'
                const noRoute = isMain && !p.active_group_label
                return (
                  <tr key={p.prefix_ref} className="hover:bg-white/2">
                    <td className="px-6 py-3 text-[var(--color-text)] font-medium">
                      {p.label}
                      {noRoute && (
                        <span className="ml-2 text-[10px] font-semibold text-red-400">⚠ SIN RUTEO</span>
                      )}
                    </td>
                    <td className="px-6 py-3">
                      <select
                        className={selectCls}
                        disabled={saving === p.prefix_ref}
                        value={p.active_group_label || ''}
                        onChange={e => choose(p.prefix_ref, e.target.value)}
                      >
                        {isMain ? (
                          <option value="">⚠ Cortar ruteo (sin grupo — deja de llamar)</option>
                        ) : (
                          <option value="">Automático (hereda el grupo principal)</option>
                        )}
                        {groups.map(g => (
                          <option key={g.label} value={g.label}>{g.label}</option>
                        ))}
                      </select>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
