'use client'
import { useEffect, useState } from 'react'
import { apiGet, apiPost } from '@/lib/api'
import { AlertTriangle, Trash2 } from 'lucide-react'
import { ErrorBanner } from '@/components/ErrorBanner'

const CONFIRM_WORD = 'RESETEAR'

interface ResetResult {
  ok: boolean
  backup_file: string
  invoices_deleted: number
  balance_transactions_deleted: number
  customers_reset: number
}

export default function BillingResetPage() {
  const [invoiceCount, setInvoiceCount] = useState<number | null>(null)
  const [confirmText, setConfirmText] = useState('')
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<ResetResult | null>(null)

  useEffect(() => {
    apiGet('/admin/invoices').then(rows => setInvoiceCount(rows.length)).catch(() => setInvoiceCount(null))
  }, [])

  // Corre en background (puede tardar minutos con millones de CDRs — un
  // intento anterior síncrono se colgó y nginx cortó con 504 a los 60s) — se
  // arranca un job y se sondea su estado cada 2s hasta que termina, mismo
  // patrón que /billing-recalc.
  async function pollJob(jobId: string): Promise<ResetResult> {
    let notFoundStreak = 0
    for (;;) {
      await new Promise(r => setTimeout(r, 2000))
      let job: any
      try {
        job = await apiGet(`/admin/invoices/reset-module/jobs/${jobId}`)
        notFoundStreak = 0
      } catch (e: any) {
        // BackgroundTasks arranca DESPUÉS de que la respuesta del POST ya se
        // mandó — un 404 aislado es el job arrancando, no que no exista.
        // Confirmado en producción: /billing-recalc mostraba "no encontrado"
        // con el job ya escribiendo su archivo de estado del otro lado.
        notFoundStreak++
        if (notFoundStreak >= 10) throw new Error(e.message || 'Error consultando el estado del job')
        continue
      }
      if (job.status === 'running') continue
      if (job.status === 'error') throw new Error(job.error || 'Error reseteando el módulo')
      return job.result as ResetResult
    }
  }

  async function run() {
    if (confirmText !== CONFIRM_WORD) return
    if (!confirm(
      'Última confirmación: esto borra TODAS las facturas y TODO el historial de balance de ' +
      'TODOS los clientes, y recalcula cada balance como deuda pura por consumo histórico, sin ' +
      'ningún pago aplicado. Se guarda un backup en JSON en el servidor antes de borrar, pero no ' +
      'hay deshacer desde el panel. ¿Continuar?'
    )) return

    setRunning(true); setError(''); setResult(null)
    try {
      const { job_id } = await apiPost('/admin/invoices/reset-module', {})
      const r = await pollJob(job_id)
      setResult(r)
      setConfirmText('')
      setInvoiceCount(0)
    } catch (e: any) { setError(e.message || 'Error al resetear el módulo de facturación') }
    finally { setRunning(false) }
  }

  const card = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-5'

  return (
    <div className="space-y-5 max-w-2xl">
      <div>
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <Trash2 size={20} className="text-red-400" /> Reset facturación
        </h1>
        <p className="text-sm text-[var(--color-text-2)] mt-1">
          Borra por completo el módulo de Facturación — todas las facturas y todo el historial de
          balance de todos los clientes — y arranca de cero. Pensado para limpiar datos de prueba
          o un estado inconsistente (ej. facturas duplicadas del mismo período) en vez de tener que
          reconciliar factura por factura.
        </p>
      </div>

      {error && <ErrorBanner>{error}</ErrorBanner>}

      <div className={`${card} border-red-900/40 bg-red-950/10 space-y-3`}>
        <div className="flex items-start gap-2.5">
          <AlertTriangle size={16} className="text-red-400 flex-shrink-0 mt-0.5" />
          <div className="text-sm text-red-200 space-y-2">
            <p>Esta acción, para <strong>todos los clientes</strong>:</p>
            <ul className="list-disc list-inside space-y-1 text-red-200/90">
              <li>Borra todas las facturas ({invoiceCount === null ? '…' : invoiceCount} hoy) y sus PDFs.</li>
              <li>Borra todo el historial de balance (balance_transactions) — llamadas, ajustes manuales, pagos y recálculos.</li>
              <li>
                Recalcula el balance de cada cliente como <strong>deuda pura</strong>: la suma de todo su
                consumo histórico, en negativo, como si nunca se hubiera acreditado ni un pago ni una recarga.
              </li>
            </ul>
            <p>
              Se guarda un backup en JSON en el servidor (<span className="font-mono text-xs">logs/billing_reset_backups/</span>)
              antes de borrar nada, pero esta pantalla no ofrece un "deshacer" — restaurarlo requeriría acceso directo al servidor.
            </p>
            <p>
              Las facturas de esta plataforma son PDFs internos sin validez tributaria (sin SUNAT) —
              si eso cambia en el futuro, esta acción deja de ser segura tal como está.
            </p>
          </div>
        </div>
      </div>

      {result ? (
        <div className={`${card} border-green-900/40 bg-green-950/10`}>
          <p className="text-sm text-green-200 font-medium">Módulo reseteado.</p>
          <ul className="text-sm text-green-200/80 mt-2 space-y-1">
            <li>{result.invoices_deleted} factura(s) borradas</li>
            <li>{result.balance_transactions_deleted} movimiento(s) de balance borrados</li>
            <li>{result.customers_reset} cliente(s) con balance recalculado</li>
            <li className="font-mono text-xs text-green-200/60 mt-2">Backup: {result.backup_file}</li>
          </ul>
        </div>
      ) : (
        <div className={`${card} space-y-3`}>
          <label className="block text-xs text-[var(--color-text-2)] uppercase tracking-wider">
            Escribí <span className="font-mono text-red-400">{CONFIRM_WORD}</span> para habilitar el botón
          </label>
          <input
            value={confirmText}
            onChange={e => setConfirmText(e.target.value)}
            placeholder={CONFIRM_WORD}
            className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:border-red-500"
          />
          <button
            onClick={run}
            disabled={confirmText !== CONFIRM_WORD || running}
            className="flex items-center gap-2 bg-red-600 hover:bg-red-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
          >
            <Trash2 size={14} />
            {running ? 'Reseteando... (puede tardar varios minutos, no cierres esta pestaña)' : 'Resetear módulo de facturación'}
          </button>
        </div>
      )}
    </div>
  )
}
