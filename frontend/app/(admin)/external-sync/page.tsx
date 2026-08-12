'use client'
import { useEffect, useState } from 'react'
import { apiGet, apiPut, apiPost } from '@/lib/api'
import { Save, PlugZap, Play, Database } from 'lucide-react'
import { Toggle } from '@/components/Toggle'

interface Config {
  engine: 'mysql' | 'postgres' | 'sqlserver'
  host: string
  port: number
  db_name: string
  db_user: string
  has_password: boolean
  enabled: boolean
  last_sync_at: string | null
  last_sync_id: number
  last_status: string | null
  last_error: string | null
}

interface LogRow {
  id: number
  started_at: string
  finished_at: string | null
  rows_synced: number
  rows_failed: number
  status: string
  detail: string | null
}

const DEFAULT_PORTS: Record<string, number> = { mysql: 3306, postgres: 5432, sqlserver: 1433 }
const ENGINE_LABELS: Record<string, string> = { mysql: 'MySQL / MariaDB', postgres: 'PostgreSQL', sqlserver: 'SQL Server' }
const card = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'

export default function ExternalSyncPage() {
  const [cfg, setCfg] = useState<Config | null>(null)
  const [form, setForm] = useState({
    engine: 'mysql', host: '', port: 3306, db_name: '', db_user: '', db_pass: '', enabled: false,
  })
  const [permissions, setPermissions] = useState<string[]>([])
  const [log, setLog] = useState<LogRow[]>([])
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; output: string } | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')

  async function load() {
    setError('')
    try {
      const c: Config = await apiGet('/admin/external-sync/config')
      setCfg(c)
      setForm({
        engine: c.engine, host: c.host, port: c.port, db_name: c.db_name,
        db_user: c.db_user, db_pass: '', enabled: c.enabled,
      })
      setLog(await apiGet('/admin/external-sync/log'))
    } catch (e: any) { setError(e.message || 'Error cargando configuración') }
  }

  async function loadPermissions(engine: string) {
    try {
      const r = await apiGet(`/admin/external-sync/permissions-needed?engine=${engine}`)
      setPermissions(r.permissions)
    } catch { /* no crítico — el bloque de permisos sugeridos queda vacío */ }
  }

  useEffect(() => { load() }, [])
  useEffect(() => { loadPermissions(form.engine) }, [form.engine])

  function changeEngine(engine: string) {
    setForm(f => ({ ...f, engine: engine as Config['engine'], port: DEFAULT_PORTS[engine] }))
  }

  async function save(e: React.FormEvent) {
    e.preventDefault(); setSaving(true); setTestResult(null)
    try {
      await apiPut('/admin/external-sync/config', {
        ...form,
        db_pass: form.db_pass || null,
      })
      setForm(f => ({ ...f, db_pass: '' }))
      await load()
    } finally { setSaving(false) }
  }

  async function testConnection() {
    setTesting(true); setTestResult(null)
    try {
      const r = await apiPost('/admin/external-sync/test-connection', {})
      setTestResult(r)
    } finally { setTesting(false) }
  }

  async function runNow() {
    setRunning(true)
    try {
      await apiPost('/admin/external-sync/run-now', {})
      setTimeout(load, 2000)
    } finally { setRunning(false) }
  }

  if (!cfg && error) return <div className="text-red-400 p-8">{error}</div>
  if (!cfg) return <div className="text-[var(--color-muted)] p-8">Cargando...</div>

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Sincronización externa</h1>
        <p className="text-sm text-[var(--color-text-2)] mt-1">
          Copia los CDRs hacia una base de datos externa, de forma incremental y de solo lectura sobre VoxiKam —
          útil para BI/reportería sin darle acceso directo a la DB de producción. Corre de noche (00:15) o a pedido.
        </p>
      </div>

      <form onSubmit={save} className={`${card} p-5 space-y-4`}>
        <div className="flex items-center gap-2">
          <Database size={16} className="text-[var(--color-muted)]" />
          <h2 className="font-semibold text-sm">Destino</h2>
        </div>

        <div className="grid grid-cols-3 gap-2">
          {(['mysql', 'postgres', 'sqlserver'] as const).map(e => (
            <button key={e} type="button" onClick={() => changeEngine(e)}
              className={`px-3 py-2 rounded-lg text-xs font-medium border transition-colors ${
                form.engine === e
                  ? 'bg-brand-600/20 border-brand-500 text-brand-400'
                  : 'border-[var(--color-border)] text-[var(--color-text-2)] hover:text-white'
              }`}>
              {ENGINE_LABELS[e]}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-[var(--color-text-2)] mb-1">Host</label>
            <input required value={form.host} onChange={e => setForm(f => ({ ...f, host: e.target.value }))}
              placeholder="10.0.0.20"
              className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-xs text-[var(--color-text-2)] mb-1">Puerto</label>
            <input required type="number" value={form.port}
              onChange={e => setForm(f => ({ ...f, port: parseInt(e.target.value) || 0 }))}
              className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-xs text-[var(--color-text-2)] mb-1">Base de datos</label>
            <input required value={form.db_name} onChange={e => setForm(f => ({ ...f, db_name: e.target.value }))}
              className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-xs text-[var(--color-text-2)] mb-1">Usuario</label>
            <input required value={form.db_user} onChange={e => setForm(f => ({ ...f, db_user: e.target.value }))}
              className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm" />
          </div>
          <div className="col-span-2">
            <label className="block text-xs text-[var(--color-text-2)] mb-1">Contraseña</label>
            <input type="password" value={form.db_pass} onChange={e => setForm(f => ({ ...f, db_pass: e.target.value }))}
              placeholder={cfg.has_password ? '•••••••••••• (dejar vacío para no cambiarla)' : ''}
              className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm" />
          </div>
        </div>

        {permissions.length > 0 && (
          <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg p-3">
            <p className="text-xs text-[var(--color-text-2)] mb-1.5">Permisos que necesita el usuario en el destino:</p>
            <ul className="text-xs text-[var(--color-muted)] list-disc list-inside space-y-0.5">
              {permissions.map(p => <li key={p}>{p}</li>)}
            </ul>
          </div>
        )}

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm">
            <Toggle checked={form.enabled} onChange={() => setForm(f => ({ ...f, enabled: !f.enabled }))} label="Habilitar sincronización" />
            Habilitada (corre en el cron de las 00:15)
          </div>

          <div className="flex gap-2">
            <button type="button" onClick={testConnection} disabled={testing}
              className="flex items-center gap-1.5 px-3 py-2 border border-[var(--color-border)] hover:border-brand-500 disabled:opacity-50 text-xs font-medium rounded-lg">
              <PlugZap size={13} /> {testing ? 'Probando…' : 'Probar conexión'}
            </button>
            <button type="submit" disabled={saving}
              className="flex items-center gap-1.5 px-3 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-xs font-medium rounded-lg">
              <Save size={13} /> {saving ? 'Guardando…' : 'Guardar'}
            </button>
          </div>
        </div>

        {testResult && (
          <p className={`text-xs ${testResult.ok ? 'text-green-400' : 'text-red-400'}`}>
            {testResult.output || (testResult.ok ? 'Conexión OK' : 'Error de conexión')}
          </p>
        )}
      </form>

      <div className={`${card} p-5 flex items-center justify-between`}>
        <div>
          <p className="text-sm font-medium">Última corrida</p>
          <p className="text-xs text-[var(--color-text-2)] mt-0.5">
            {cfg.last_sync_at ? new Date(cfg.last_sync_at).toLocaleString('es-PE') : 'todavía no corrió'}
            {cfg.last_status && (
              <span className={
                cfg.last_status === 'ok' ? 'text-green-400 ml-2'
                : cfg.last_status === 'partial' ? 'text-yellow-400 ml-2'
                : 'text-red-400 ml-2'
              }>{cfg.last_status}</span>
            )}
          </p>
          {cfg.last_error && <p className="text-xs text-red-400 mt-1">{cfg.last_error}</p>}
        </div>
        <button onClick={runNow} disabled={running}
          className="flex items-center gap-1.5 px-3 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-xs font-medium rounded-lg">
          <Play size={13} /> {running ? 'Iniciando…' : 'Sincronizar ahora'}
        </button>
      </div>

      <div className={`${card} overflow-x-auto`}>
        <div className="px-5 py-3 border-b border-[var(--color-border)]">
          <h2 className="font-semibold text-sm">Historial</h2>
        </div>
        {log.length === 0 ? (
          <div className="text-[var(--color-muted)] p-8 text-center text-sm">Sin corridas todavía</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[var(--color-text-2)] text-xs uppercase border-b border-[var(--color-border)]">
                <th className="px-5 py-3 text-left">Inicio</th>
                <th className="px-5 py-3 text-right">Filas OK</th>
                <th className="px-5 py-3 text-right">Fallidas</th>
                <th className="px-5 py-3 text-left">Estado</th>
                <th className="px-5 py-3 text-left">Detalle</th>
              </tr>
            </thead>
            <tbody>
              {log.map(l => (
                <tr key={l.id} className="border-b border-[var(--color-border)]/50">
                  <td className="px-5 py-2.5 text-xs">{new Date(l.started_at).toLocaleString('es-PE')}</td>
                  <td className="px-5 py-2.5 text-right">{l.rows_synced.toLocaleString('es-PE')}</td>
                  <td className={`px-5 py-2.5 text-right ${l.rows_failed ? 'text-red-400' : 'text-[var(--color-muted)]'}`}>{l.rows_failed.toLocaleString('es-PE')}</td>
                  <td className={`px-5 py-2.5 text-xs ${l.status === 'ok' ? 'text-green-400' : l.status === 'running' ? 'text-yellow-400' : l.status === 'partial' ? 'text-yellow-400' : 'text-red-400'}`}>{l.status}</td>
                  <td className="px-5 py-2.5 text-xs text-[var(--color-muted)] max-w-[300px] truncate">{l.detail ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
