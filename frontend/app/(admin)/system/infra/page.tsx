'use client'
import { useEffect, useRef, useState } from 'react'
import { apiGet, apiPut, apiPost } from '@/lib/api'
import { Lock, DatabaseBackup, BellRing, Play, ShieldCheck, ShieldOff } from 'lucide-react'

const card = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'
const btn = 'flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg disabled:opacity-50'
const btnPrimary = `${btn} bg-brand-600 hover:bg-brand-500 text-white`
const btnGhost = `${btn} bg-[var(--color-surface)] border border-[var(--color-border)] hover:border-brand-500`

function fmtBytes(n: number) {
  if (!n) return '0 B'
  const u = ['B', 'KB', 'MB', 'GB']
  let i = 0
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++ }
  return `${n.toFixed(1)} ${u[i]}`
}

function fmtAgo(iso: string | null | undefined) {
  if (!iso) return 'nunca'
  const diffMs = Date.now() - new Date(iso).getTime()
  const min = Math.floor(diffMs / 60000)
  if (min < 1) return 'hace instantes'
  if (min < 60) return `hace ${min} min`
  const h = Math.floor(min / 60)
  if (h < 24) return `hace ${h}h`
  return `hace ${Math.floor(h / 24)}d`
}

type Action = { status: 'running' | 'ok' | 'error'; label: string; output_tail?: string } | null

type Infra = {
  tls: { enabled: boolean; domain: string; action: Action }
  backup: {
    enabled: boolean
    last_run: { timestamp: string; mariadb_ok: boolean; mariadb_bytes: number; clickhouse_ok: boolean; remote_synced: boolean } | null
    action: Action
    recent_files: { name: string; bytes: number; modified_at: string }[]
  }
  alerts: {
    enabled: boolean
    status: { last_check: string; problems: { key: string; label: string; status: string; detail: string }[] } | null
  }
}

export default function InfraPage() {
  const [data, setData] = useState<Infra | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  async function load() {
    try {
      const d = await apiGet('/admin/system/infra')
      setData(d)
      const running = d.tls.action?.status === 'running' || d.backup.action?.status === 'running'
      if (running && !pollRef.current) {
        pollRef.current = setInterval(load, 4000)
      } else if (!running && pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    } catch (e: any) { setError(e.message || 'Error cargando estado de infraestructura') }
  }

  useEffect(() => {
    load()
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  async function tlsAction(enable: boolean) {
    setBusy('tls'); setError('')
    try {
      await apiPost(`/admin/system/infra/tls/${enable ? 'enable' : 'disable'}`, {})
      await load()
    } catch (e: any) { setError(e.message || 'Error') } finally { setBusy(null) }
  }

  async function toggleBackup(enabled: boolean) {
    setBusy('backup-toggle'); setError('')
    try { await apiPut('/admin/system/infra/backup', { enabled }); await load() }
    catch (e: any) { setError(e.message || 'Error') } finally { setBusy(null) }
  }

  async function runBackupNow() {
    setBusy('backup-run'); setError('')
    try { await apiPost('/admin/system/infra/backup/run-now', {}); await load() }
    catch (e: any) { setError(e.message || 'Error') } finally { setBusy(null) }
  }

  async function toggleAlerts(enabled: boolean) {
    setBusy('alerts-toggle'); setError('')
    try { await apiPut('/admin/system/infra/alerts', { enabled }); await load() }
    catch (e: any) { setError(e.message || 'Error') } finally { setBusy(null) }
  }

  if (!data) return <div className="text-[var(--color-muted)] p-8">{error || 'Cargando...'}</div>

  const tlsRunning = data.tls.action?.status === 'running'
  const backupRunning = data.backup.action?.status === 'running'

  return (
    <div className="space-y-6">
      {error && <div className="bg-red-900/30 border border-red-700 text-red-300 text-sm rounded-lg px-4 py-3">{error}</div>}
      <div>
        <h1 className="text-2xl font-bold">Infraestructura</h1>
        <p className="text-sm text-[var(--color-text-2)] mt-1">
          HTTPS, backup automático de la base de datos y alertas de infraestructura — antes solo se podían
          activar por consola (SSH), acá se controlan y verifican sin salir del panel.
        </p>
      </div>

      {/* ── TLS ── */}
      <div className={`${card} p-5`}>
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-2">
            <Lock size={16} className="text-[var(--color-muted)]" />
            <h2 className="font-semibold text-sm">HTTPS (Let&apos;s Encrypt)</h2>
          </div>
          <span className={`text-xs px-2 py-1 rounded-full ${data.tls.enabled ? 'bg-green-900/40 text-green-400' : 'bg-[var(--color-surface)] text-[var(--color-text-2)]'}`}>
            {data.tls.enabled ? 'Activo' : 'Inactivo — HTTP plano'}
          </span>
        </div>
        <p className="text-xs text-[var(--color-text-2)] mt-2 mb-4">
          Dominio configurado: <span className="font-mono">{data.tls.domain || '(sin dominio)'}</span>.
          Necesita que ese dominio ya resuelva a este server y el puerto 80 alcanzable desde internet —
          certbot valida eso al activar.
        </p>

        {tlsRunning ? (
          <p className="text-xs text-amber-400">Operación en curso ({data.tls.action?.label})… esto puede tardar hasta un minuto la primera vez (instala certbot).</p>
        ) : (
          <div className="flex items-center gap-3">
            {!data.tls.enabled ? (
              <button onClick={() => tlsAction(true)} disabled={busy === 'tls' || !data.tls.domain} className={btnPrimary}>
                <ShieldCheck size={13} /> Activar HTTPS
              </button>
            ) : (
              <button onClick={() => tlsAction(false)} disabled={busy === 'tls'} className={btnGhost}>
                <ShieldOff size={13} /> Desactivar (volver a HTTP)
              </button>
            )}
            {!data.tls.domain && <span className="text-xs text-[var(--color-text-2)]">Configurá un dominio primero (Sistema → Dominio de acceso)</span>}
          </div>
        )}

        {data.tls.action && data.tls.action.status !== 'running' && (
          <div className={`mt-3 text-xs rounded-lg p-3 border ${data.tls.action.status === 'ok' ? 'border-green-800 bg-green-900/20 text-green-300' : 'border-red-800 bg-red-900/20 text-red-300'}`}>
            <p className="font-medium mb-1">Último resultado: {data.tls.action.status === 'ok' ? 'OK' : 'Error'}</p>
            {data.tls.action.output_tail && (
              <pre className="whitespace-pre-wrap font-mono text-[10px] opacity-80 max-h-40 overflow-y-auto">{data.tls.action.output_tail}</pre>
            )}
          </div>
        )}
      </div>

      {/* ── Backup ── */}
      <div className={`${card} p-5`}>
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-2">
            <DatabaseBackup size={16} className="text-[var(--color-muted)]" />
            <h2 className="font-semibold text-sm">Backup automático</h2>
          </div>
          <label className="flex items-center gap-2 cursor-pointer select-none text-xs">
            <input type="checkbox" checked={data.backup.enabled} disabled={busy === 'backup-toggle'}
              onChange={e => toggleBackup(e.target.checked)} />
            {data.backup.enabled ? 'Activado (diario 02:30)' : 'Desactivado'}
          </label>
        </div>
        <p className="text-xs text-[var(--color-text-2)] mt-2 mb-3">
          MariaDB (facturas/saldos/clientes) + best-effort de ClickHouse, guardado en <span className="font-mono">/var/backups/voxikam</span>,
          retención 14 días.
        </p>

        <div className="flex items-center gap-3 mb-4">
          <button onClick={runBackupNow} disabled={busy === 'backup-run' || backupRunning} className={btnGhost}>
            <Play size={13} /> {backupRunning ? 'Corriendo…' : 'Ejecutar ahora'}
          </button>
        </div>

        {data.backup.last_run && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs mb-4">
            <div>
              <p className="text-[var(--color-text-2)]">Última corrida</p>
              <p className="font-medium">{fmtAgo(data.backup.last_run.timestamp)}</p>
            </div>
            <div>
              <p className="text-[var(--color-text-2)]">MariaDB</p>
              <p className={`font-medium ${data.backup.last_run.mariadb_ok ? 'text-green-400' : 'text-red-400'}`}>
                {data.backup.last_run.mariadb_ok ? `OK · ${fmtBytes(data.backup.last_run.mariadb_bytes)}` : 'Falló'}
              </p>
            </div>
            <div>
              <p className="text-[var(--color-text-2)]">ClickHouse</p>
              <p className={`font-medium ${data.backup.last_run.clickhouse_ok ? 'text-green-400' : 'text-[var(--color-text-2)]'}`}>
                {data.backup.last_run.clickhouse_ok ? 'OK' : 'No disponible'}
              </p>
            </div>
            <div>
              <p className="text-[var(--color-text-2)]">Copia remota</p>
              <p className="font-medium">{data.backup.last_run.remote_synced ? 'Sincronizada' : 'Sin destino'}</p>
            </div>
          </div>
        )}

        {data.backup.recent_files.length > 0 && (
          <div className="border-t border-[var(--color-border)] pt-3">
            <p className="text-xs text-[var(--color-text-2)] mb-2">Últimos backups de MariaDB en disco</p>
            <div className="space-y-1">
              {data.backup.recent_files.slice(0, 5).map(f => (
                <div key={f.name} className="flex items-center justify-between text-xs font-mono text-[var(--color-text-2)]">
                  <span>{f.name}</span>
                  <span>{fmtBytes(f.bytes)} · {fmtAgo(f.modified_at)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {data.backup.action && data.backup.action.status !== 'running' && (
          <div className={`mt-3 text-xs rounded-lg p-3 border ${data.backup.action.status === 'ok' ? 'border-green-800 bg-green-900/20 text-green-300' : 'border-red-800 bg-red-900/20 text-red-300'}`}>
            Ejecución manual: {data.backup.action.status === 'ok' ? 'OK' : 'Error'}
          </div>
        )}
      </div>

      {/* ── Alertas de infraestructura ── */}
      <div className={`${card} p-5`}>
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-2">
            <BellRing size={16} className="text-[var(--color-muted)]" />
            <h2 className="font-semibold text-sm">Alertas de infraestructura por correo</h2>
          </div>
          <label className="flex items-center gap-2 cursor-pointer select-none text-xs">
            <input type="checkbox" checked={data.alerts.enabled} disabled={busy === 'alerts-toggle'}
              onChange={e => toggleAlerts(e.target.checked)} />
            {data.alerts.enabled ? 'Activadas' : 'Desactivadas'}
          </label>
        </div>
        <p className="text-xs text-[var(--color-text-2)] mt-2 mb-3">
          Corre cada 15 min — avisa por correo (mismo remitente configurado en Sistema → Correo) si un cron se
          cuelga o el disco/memoria del server se agotan. Con las alertas desactivadas, la detección sigue
          corriendo, solo no se manda el correo.
        </p>

        {data.alerts.status ? (
          <>
            <p className="text-xs text-[var(--color-text-2)] mb-2">
              Última verificación: {fmtAgo(data.alerts.status.last_check)}
            </p>
            {data.alerts.status.problems.length === 0 ? (
              <p className="text-xs text-green-400">Sin problemas detectados</p>
            ) : (
              <div className="space-y-1">
                {data.alerts.status.problems.map(p => (
                  <div key={p.key} className="flex items-start gap-2 text-xs bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2">
                    <span className="px-1.5 py-0.5 rounded bg-red-900/40 text-red-300 font-mono text-[10px] uppercase">{p.status}</span>
                    <span>
                      <span className="font-medium">{p.label}</span>
                      {p.detail && <span className="text-[var(--color-text-2)]"> — {p.detail}</span>}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </>
        ) : (
          <p className="text-xs text-[var(--color-text-2)]">Todavía no corrió ninguna verificación en este server.</p>
        )}
      </div>
    </div>
  )
}
