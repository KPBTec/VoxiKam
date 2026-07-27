'use client'
import { ErrorBanner } from '@/components/ErrorBanner'
import { useEffect, useState } from 'react'
import { apiGet, apiPost, apiDelete } from '@/lib/api'
import { Plus, Trash2, Copy, Check } from 'lucide-react'

interface ApiKey {
  id: number; label: string; key_prefix: string
  created_at: string; last_used_at: string | null; revoked: boolean | number
}

const cardCls  = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'
const inputCls = 'w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm text-[var(--color-text)] focus:outline-none focus:border-brand-500'
const labelCls = 'block text-xs text-[var(--color-text-2)] uppercase tracking-wider mb-1'

export default function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKey[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [label, setLabel] = useState('')
  const [creating, setCreating] = useState(false)
  const [newKey, setNewKey] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const load = () =>
    apiGet('/my/api-keys').then(k => { setKeys(k); setError('') }).catch((e: any) => setError(e.message)).finally(() => setLoading(false))
  useEffect(() => { load() }, [])

  async function create(e: React.FormEvent) {
    e.preventDefault(); setCreating(true); setError(''); setCopied(false)
    try {
      const res: any = await apiPost('/my/api-keys', { label })
      setNewKey(res.api_key); setLabel(''); load()
    } catch (e: any) { setError(e.message) }
    finally { setCreating(false) }
  }

  async function revoke(id: number) {
    if (!confirm('¿Revocar esta API key? Cualquier integración que la use dejará de funcionar de inmediato.')) return
    setError('')
    try { await apiDelete(`/my/api-keys/${id}`); load() }
    catch (e: any) { setError(e.message) }
  }

  function copy() {
    if (!newKey) return
    navigator.clipboard.writeText(newKey)
    setCopied(true); setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-[var(--color-text)]">API Keys</h1>
          <p className="text-sm text-[var(--color-text-2)] mt-0.5">
            Credenciales para consultar tu saldo y llamadas por API, sin pasar por el login web.
          </p>
        </div>
      </div>

      {error && <ErrorBanner>{error}</ErrorBanner>}

      {newKey && (
        <div className="bg-brand-500/10 border border-brand-500/30 rounded-xl p-5 space-y-3">
          <p className="text-sm text-[var(--color-text)] font-medium">
            Tu nueva API key — copiala ahora, no se vuelve a mostrar completa.
          </p>
          <div className="flex items-center gap-2">
            <code className="flex-1 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-xs font-mono text-brand-400 overflow-x-auto">
              {newKey}
            </code>
            <button onClick={copy} className="p-2 rounded-lg border border-[var(--color-border)] hover:border-brand-500 text-[var(--color-text-2)] hover:text-brand-400 transition-colors">
              {copied ? <Check size={15} /> : <Copy size={15} />}
            </button>
          </div>
          <button onClick={() => setNewKey(null)} className="text-xs text-[var(--color-muted)] hover:text-[var(--color-text)]">
            Ya la copié, cerrar
          </button>
        </div>
      )}

      <form onSubmit={create} className={`${cardCls} p-5 flex gap-3 items-end`}>
        <div className="flex-1">
          <label className={labelCls}>Nombre (para identificarla después)</label>
          <input required className={inputCls} placeholder="ej: integración CRM"
            value={label} onChange={e => setLabel(e.target.value)} />
        </div>
        <button type="submit" disabled={creating}
          className="flex items-center gap-1.5 px-4 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm rounded-lg">
          <Plus size={15} /> {creating ? 'Creando…' : 'Nueva key'}
        </button>
      </form>

      <div className={`${cardCls} overflow-x-auto`}>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-[var(--color-text-2)] uppercase border-b border-[var(--color-border)]">
              <th className="px-6 py-3 text-left">Nombre</th>
              <th className="px-6 py-3 text-left">Prefijo</th>
              <th className="px-6 py-3 text-left">Creada</th>
              <th className="px-6 py-3 text-left">Último uso</th>
              <th className="px-6 py-3 text-left">Estado</th>
              <th className="px-6 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--color-border)]">
            {keys.map(k => (
              <tr key={k.id} className="hover:bg-white/2">
                <td className="px-6 py-3 text-[var(--color-text)] font-medium">{k.label || '—'}</td>
                <td className="px-6 py-3 font-mono text-xs text-[var(--color-text-2)]">{k.key_prefix}…</td>
                <td className="px-6 py-3 text-[var(--color-text-2)]">{new Date(k.created_at).toLocaleDateString()}</td>
                <td className="px-6 py-3 text-[var(--color-text-2)]">{k.last_used_at ? new Date(k.last_used_at).toLocaleDateString() : 'Nunca'}</td>
                <td className="px-6 py-3">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${k.revoked ? 'bg-zinc-800 text-zinc-500' : 'bg-green-900/30 text-green-400'}`}>
                    {k.revoked ? 'revocada' : 'activa'}
                  </span>
                </td>
                <td className="px-6 py-3 text-right">
                  {!k.revoked && (
                    <button onClick={() => revoke(k.id)} className="text-[var(--color-muted)] hover:text-red-400 transition-colors">
                      <Trash2 size={14} />
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {!loading && keys.length === 0 && (
              <tr><td colSpan={6} className="px-6 py-10 text-center text-[var(--color-muted)] text-sm">Sin API keys todavía — creá la primera arriba.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
