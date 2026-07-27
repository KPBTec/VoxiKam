'use client'
import { useEffect, useState } from 'react'
import { apiGet, apiPut, apiPost } from '@/lib/api'
import { KeyRound, Save, Send, ExternalLink } from 'lucide-react'

const card = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'
const inputCls = 'w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm'

export default function MailConfigPage() {
  const [provider, setProvider] = useState<'resend' | 'smtp'>('resend')
  const [hasApiKey, setHasApiKey] = useState(false)
  const [fromEmail, setFromEmail] = useState('')
  const [apiKeyInput, setApiKeyInput] = useState('')
  const [restartOrphanAlerts, setRestartOrphanAlerts] = useState(false)

  const [smtpHost, setSmtpHost] = useState('')
  const [smtpPort, setSmtpPort] = useState(587)
  const [smtpUsername, setSmtpUsername] = useState('')
  const [smtpPasswordInput, setSmtpPasswordInput] = useState('')
  const [hasSmtpPassword, setHasSmtpPassword] = useState(false)
  const [smtpEncryption, setSmtpEncryption] = useState<'tls' | 'ssl' | 'none'>('tls')

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const [testTo, setTestTo] = useState('')
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null)
  const [error, setError] = useState('')

  async function load() {
    setLoading(true); setError('')
    try {
      const m = await apiGet('/admin/mail-config')
      setProvider(m.provider ?? 'resend')
      setHasApiKey(m.has_api_key)
      setFromEmail(m.from_email)
      setRestartOrphanAlerts(m.restart_orphan_alerts)
      setSmtpHost(m.smtp_host ?? '')
      setSmtpPort(m.smtp_port ?? 587)
      setSmtpUsername(m.smtp_username ?? '')
      setHasSmtpPassword(m.has_smtp_password)
      setSmtpEncryption(m.smtp_encryption ?? 'tls')
    } catch (e: any) { setError(e.message || 'Error cargando configuración de correo') }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  async function save(e: React.FormEvent) {
    e.preventDefault(); setSaving(true); setSaved(false); setError('')
    try {
      await apiPut('/admin/mail-config', {
        provider,
        api_key: apiKeyInput || null,
        from_email: fromEmail,
        restart_orphan_alerts: restartOrphanAlerts,
        smtp_host: smtpHost,
        smtp_port: smtpPort,
        smtp_username: smtpUsername,
        smtp_password: smtpPasswordInput || null,
        smtp_encryption: smtpEncryption,
      })
      setApiKeyInput(''); setSmtpPasswordInput('')
      setSaved(true)
      await load()
    } catch (e: any) { setError(e.message || 'Error al guardar') }
    finally { setSaving(false) }
  }

  async function sendTest() {
    if (!testTo) return
    setTesting(true); setTestResult(null)
    try {
      await apiPost('/admin/mail-config/test', { to: testTo })
      setTestResult({ ok: true, msg: `Enviado a ${testTo} — revisá la bandeja (y spam).` })
    } catch (e: any) {
      setTestResult({ ok: false, msg: e.message ?? 'Error al enviar' })
    } finally { setTesting(false) }
  }

  if (loading) return <div className="text-[var(--color-muted)] p-8">Cargando...</div>

  return (
    <div className="space-y-6">
      {error && <div className="bg-red-900/30 border border-red-700 text-red-300 text-sm rounded-lg px-4 py-3">{error}</div>}
      <div>
        <h1 className="text-2xl font-bold">Correo</h1>
        <p className="text-sm text-[var(--color-text-2)] mt-1">
          Configuración de envío compartida por Alertas de balance, Disconnect Policies y Facturas —
          un solo lugar para el proveedor y el remitente, sin importar cuál de esos módulos manda el correo.
        </p>
      </div>

      <div className={`${card} p-5`}>
        <div className="flex items-center gap-2 mb-1">
          <KeyRound size={16} className="text-[var(--color-muted)]" />
          <h2 className="font-semibold text-sm">Configuración de correo</h2>
        </div>
        <p className="text-xs text-[var(--color-text-2)] mb-4">
          Sin esto, las alertas y facturas quedan registradas pero <strong>ningún correo se envía</strong> — solo se loguea.
        </p>

        {/* Selector de proveedor */}
        <div className="flex rounded-lg overflow-hidden border border-[var(--color-border)] text-xs w-fit mb-4">
          <button type="button" onClick={() => setProvider('resend')}
            className={`px-4 py-2 transition-colors ${provider === 'resend' ? 'bg-brand-600 text-white' : 'text-[var(--color-muted)] hover:text-[var(--color-text)]'}`}>
            Resend (API)
          </button>
          <button type="button" onClick={() => setProvider('smtp')}
            className={`px-4 py-2 transition-colors ${provider === 'smtp' ? 'bg-brand-600 text-white' : 'text-[var(--color-muted)] hover:text-[var(--color-text)]'}`}>
            SMTP propio
          </button>
        </div>

        <form onSubmit={save} className="space-y-4">
          {provider === 'resend' ? (
            <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg p-4 space-y-3">
              <p className="text-xs text-[var(--color-text-2)]">
                <a href="https://resend.com" target="_blank" rel="noreferrer" className="text-brand-400 hover:underline inline-flex items-center gap-1">
                  Resend <ExternalLink size={11} />
                </a>{' '}
                es un proveedor de correo transaccional (no un servidor propio) — creás una cuenta gratis, verificás tu dominio
                y generás una API key en{' '}
                <a href="https://resend.com/api-keys" target="_blank" rel="noreferrer" className="text-brand-400 hover:underline inline-flex items-center gap-1">
                  resend.com/api-keys <ExternalLink size={11} />
                </a>.
                {hasApiKey ? ' Ya hay una API key configurada.' : ' Todavía no hay ninguna API key configurada.'}
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-[var(--color-text-2)] mb-1">API key de Resend</label>
                  <input type="password" value={apiKeyInput} onChange={e => setApiKeyInput(e.target.value)}
                    placeholder={hasApiKey ? '•••••••••••• (dejar vacío para no cambiarla)' : 're_xxxxxxxxxxxxxxxx'}
                    className={inputCls} />
                </div>
                <div>
                  <label className="block text-xs text-[var(--color-text-2)] mb-1">Remitente (debe estar verificado en Resend)</label>
                  <input type="email" required value={fromEmail} onChange={e => setFromEmail(e.target.value)}
                    placeholder="no-reply@tudominio.com" className={inputCls} />
                </div>
              </div>
            </div>
          ) : (
            <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg p-4 space-y-3">
              <p className="text-xs text-[var(--color-text-2)]">
                Usá tu propio servidor SMTP (Gmail con contraseña de aplicación, tu hosting, un relay corporativo, etc.) —
                necesitás host, puerto, usuario y contraseña que te da tu proveedor de correo.
                {hasSmtpPassword ? ' Ya hay una contraseña configurada.' : ' Todavía no hay ninguna contraseña configurada.'}
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-[var(--color-text-2)] mb-1">Host SMTP</label>
                  <input required value={smtpHost} onChange={e => setSmtpHost(e.target.value)}
                    placeholder="smtp.tudominio.com" className={inputCls} />
                </div>
                <div>
                  <label className="block text-xs text-[var(--color-text-2)] mb-1">Puerto</label>
                  <input required type="number" value={smtpPort} onChange={e => setSmtpPort(+e.target.value)}
                    placeholder="587" className={inputCls} />
                </div>
                <div>
                  <label className="block text-xs text-[var(--color-text-2)] mb-1">Usuario</label>
                  <input required value={smtpUsername} onChange={e => setSmtpUsername(e.target.value)}
                    placeholder="no-reply@tudominio.com" className={inputCls} />
                </div>
                <div>
                  <label className="block text-xs text-[var(--color-text-2)] mb-1">Contraseña</label>
                  <input type="password" value={smtpPasswordInput} onChange={e => setSmtpPasswordInput(e.target.value)}
                    placeholder={hasSmtpPassword ? '•••••••••••• (dejar vacío para no cambiarla)' : 'contraseña o app-password'}
                    className={inputCls} />
                </div>
                <div>
                  <label className="block text-xs text-[var(--color-text-2)] mb-1">Cifrado</label>
                  <select value={smtpEncryption} onChange={e => setSmtpEncryption(e.target.value as any)} className={inputCls}>
                    <option value="tls">STARTTLS (típico en el puerto 587)</option>
                    <option value="ssl">SSL/TLS implícito (típico en el puerto 465)</option>
                    <option value="none">Sin cifrado (solo redes internas de confianza)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-[var(--color-text-2)] mb-1">Remitente</label>
                  <input type="email" required value={fromEmail} onChange={e => setFromEmail(e.target.value)}
                    placeholder="no-reply@tudominio.com" className={inputCls} />
                </div>
              </div>
            </div>
          )}

          <div className="border-t border-[var(--color-border)] pt-4">
            <label className="flex items-start gap-2.5 cursor-pointer select-none">
              <input type="checkbox" checked={restartOrphanAlerts} onChange={e => setRestartOrphanAlerts(e.target.checked)} className="mt-0.5" />
              <span>
                <span className="block text-sm font-medium">Alertar llamadas interrumpidas por reinicio de Kamailio</span>
                <span className="block text-xs text-[var(--color-text-2)] mt-0.5">
                  Si Kamailio se reinicia con llamadas en curso, esas llamadas nunca facturan (queda registrado igual,
                  con estado <code>RESTART_ORPHANED</code>, sin monto). Con esto activado, además te llega un correo
                  cada vez que pasa, para revisarlas a mano.
                </span>
              </span>
            </label>
          </div>

          <div className="flex items-center gap-3">
            <button type="submit" disabled={saving}
              className="flex items-center gap-1.5 px-3 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-xs font-medium rounded-lg">
              <Save size={13} /> {saving ? 'Guardando…' : 'Guardar configuración de correo'}
            </button>
            {saved && <span className="text-xs text-green-400">Guardado</span>}
          </div>
        </form>
      </div>

      <div className={`${card} p-5`}>
        <div className="flex items-center gap-2 mb-1">
          <Send size={16} className="text-[var(--color-muted)]" />
          <h2 className="font-semibold text-sm">Enviar correo de prueba</h2>
        </div>
        <p className="text-xs text-[var(--color-text-2)] mb-3">
          Usa la configuración guardada AHORA MISMO (guardala primero) — la forma más rápida de confirmar que funciona
          antes de confiar en las alertas o el envío automático de facturas.
        </p>
        <div className="flex gap-3 items-end flex-wrap">
          <div className="flex-1 min-w-56">
            <label className="block text-xs text-[var(--color-text-2)] mb-1">Enviar a</label>
            <input type="email" value={testTo} onChange={e => setTestTo(e.target.value)}
              placeholder="tu-correo@ejemplo.com" className={inputCls} />
          </div>
          <button type="button" onClick={sendTest} disabled={testing || !testTo}
            className="flex items-center gap-1.5 px-3 py-2 bg-[var(--color-surface)] border border-[var(--color-border)] hover:border-brand-500 disabled:opacity-50 text-xs font-medium rounded-lg">
            <Send size={13} /> {testing ? 'Enviando…' : 'Enviar prueba'}
          </button>
        </div>
        {testResult && (
          <p className={`text-xs mt-2 ${testResult.ok ? 'text-green-400' : 'text-red-400'}`}>{testResult.msg}</p>
        )}
      </div>
    </div>
  )
}
