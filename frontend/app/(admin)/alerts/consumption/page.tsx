'use client'
import { useEffect, useState } from 'react'
import { apiGet, apiPut } from '@/lib/api'
import { Mail, Save } from 'lucide-react'

interface Rule {
  id: number
  billing_type: 'prepago' | 'postpago'
  label: string
  threshold: string
  active: boolean
}

interface AffectedRow {
  id: number
  name: string
  email: string
  balance: string
  last_topup_amount?: string | null
  pct_remaining?: string | null
  rule_id: number
  rule_label: string
  threshold: string
}

interface Affected {
  prepago: AffectedRow[]
  postpago: AffectedRow[]
}

export default function AlertConsumptionPage() {
  const [rules, setRules]       = useState<Rule[]>([])
  const [affected, setAffected] = useState<Affected>({ prepago: [], postpago: [] })
  const [notifyEmail, setNotifyEmail] = useState('')
  const [savingEmail, setSavingEmail] = useState(false)
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState('')

  async function load() {
    setLoading(true); setError('')
    try {
      const [r, a, e] = await Promise.all([
        apiGet('/admin/alerts/rules'),
        apiGet('/admin/alerts/affected'),
        apiGet('/admin/alerts/notify-email'),
      ])
      setRules(r)
      setAffected(a)
      setNotifyEmail(e.email)
    } catch (e: any) { setError(e.message || 'Error cargando alertas') }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  async function toggleRule(rule: Rule) {
    await apiPut(`/admin/alerts/rules/${rule.id}`, { active: !rule.active })
    load()
  }

  async function updateThreshold(rule: Rule, value: string) {
    setRules(rs => rs.map(r => r.id === rule.id ? { ...r, threshold: value } : r))
  }

  async function saveThreshold(rule: Rule) {
    await apiPut(`/admin/alerts/rules/${rule.id}`, { threshold: parseFloat(rule.threshold) })
    load()
  }

  async function saveNotifyEmail(e: React.FormEvent) {
    e.preventDefault(); setSavingEmail(true)
    try { await apiPut('/admin/alerts/notify-email', { email: notifyEmail }) }
    finally { setSavingEmail(false) }
  }

  const card = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'

  function RuleGroup({ title, items }: { title: string; items: Rule[] }) {
    return (
      <div className={`${card} p-5`}>
        <h2 className="font-semibold text-sm mb-4">{title}</h2>
        <div className="space-y-3">
          {items.map(r => (
            <div key={r.id} className="flex items-center gap-3 justify-between">
              <div className="flex-1 min-w-0">
                <p className="text-sm truncate" style={{ opacity: r.active ? 1 : 0.45 }}>{r.label}</p>
              </div>
              <div className="flex items-center gap-1.5">
                <input
                  type="number"
                  value={r.threshold}
                  onChange={e => updateThreshold(r, e.target.value)}
                  onBlur={() => saveThreshold(r)}
                  className="w-20 bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-2 py-1 text-xs text-right"
                />
                <span className="text-xs text-[var(--color-muted)] w-4">{r.billing_type === 'prepago' ? '%' : ''}</span>
              </div>
              <button
                onClick={() => toggleRule(r)}
                className={`relative w-9 h-5 rounded-full transition-colors flex-shrink-0 ${r.active ? 'bg-brand-600' : 'bg-zinc-700'}`}
              >
                <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${r.active ? 'translate-x-4' : 'translate-x-0.5'}`} />
              </button>
            </div>
          ))}
          {items.length === 0 && <p className="text-xs text-[var(--color-muted)]">Sin reglas</p>}
        </div>
      </div>
    )
  }

  function AffectedTable({ title, rows, isPrepago }: { title: string; rows: AffectedRow[]; isPrepago: boolean }) {
    return (
      <div className={`${card} overflow-x-auto`}>
        <div className="px-5 py-3 border-b border-[var(--color-border)]">
          <h2 className="font-semibold text-sm">{title}</h2>
        </div>
        {rows.length === 0 ? (
          <p className="p-6 text-center text-sm text-[var(--color-muted)]">Ningún cliente cruzando estas reglas ahora mismo</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[var(--color-text-2)] text-xs uppercase border-b border-[var(--color-border)]">
                <th className="px-5 py-2.5 text-left">Cliente</th>
                <th className="px-5 py-2.5 text-right">Balance</th>
                {isPrepago && <th className="px-5 py-2.5 text-right">% restante</th>}
                <th className="px-5 py-2.5 text-left">Regla cruzada</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={`${r.id}-${r.rule_id}-${i}`} className="border-b border-[var(--color-border)]/50">
                  <td className="px-5 py-2.5">{r.name}</td>
                  <td className="px-5 py-2.5 text-right font-mono">S/. {parseFloat(r.balance).toFixed(2)}</td>
                  {isPrepago && <td className="px-5 py-2.5 text-right font-mono">{r.pct_remaining ?? '—'}%</td>}
                  <td className="px-5 py-2.5 text-orange-400 text-xs">{r.rule_label}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    )
  }

  if (loading) return <div className="text-[var(--color-muted)] p-8">Cargando...</div>
  if (error) return <div className="text-red-400 p-8">{error}</div>

  const prepagoRules  = rules.filter(r => r.billing_type === 'prepago')
  const postpagoRules = rules.filter(r => r.billing_type === 'postpago')

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Alerta consumo</h1>
        <p className="text-sm text-[var(--color-text-2)] mt-1">
          Prepago avisa por % de saldo restante (respecto al último recargo) · Postpago avisa por balance absoluto.
          Cada regla se puede activar/desactivar y ajustar el umbral de forma independiente.
        </p>
      </div>

      <p className="text-xs text-[var(--color-text-2)] -mt-2">
        La API key de Resend y el remitente se configuran en <a href="/mail-config" className="underline">Sistema → Correo</a> —
        sin eso, las alertas quedan registradas pero ningún correo se envía.
      </p>

      <form onSubmit={saveNotifyEmail} className={`${card} p-4 flex items-center gap-3`}>
        <Mail size={16} className="text-[var(--color-muted)] flex-shrink-0" />
        <input
          type="email" required value={notifyEmail} onChange={e => setNotifyEmail(e.target.value)}
          placeholder="admin@tudominio.com"
          className="flex-1 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm"
        />
        <button type="submit" disabled={savingEmail}
          className="flex items-center gap-1.5 px-3 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-xs font-medium rounded-lg">
          <Save size={13} /> {savingEmail ? 'Guardando…' : 'Guardar email de notificación'}
        </button>
      </form>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <RuleGroup title="Reglas — Prepago" items={prepagoRules} />
        <RuleGroup title="Reglas — Postpago" items={postpagoRules} />
      </div>

      <div className="grid grid-cols-1 gap-4">
        <AffectedTable title="Clientes prepago con saldo bajo ahora" rows={affected.prepago} isPrepago />
        <AffectedTable title="Clientes postpago con balance alto ahora" rows={affected.postpago} isPrepago={false} />
      </div>
    </div>
  )
}
