'use client'
import { useEffect, useState } from 'react'
import { apiFetch, apiGet } from '@/lib/api'
import { SipLadder, TraceMsg } from '@/components/SipLadder'
import { StatusBadge, callStateVariant, sipCodeVariant, type BadgeVariant } from '@/components/StatusBadge'
import { ErrorBanner } from '@/components/ErrorBanner'
import { ClickableRow } from '@/components/ClickableRow'

interface CDR {
  call_id: string; customer_name: string; carrier_name: string
  src_number: string; dst_number: string
  sessiontime: number; billsec: number; buycost: number; sessionbill: number; lucro: number
  disposition: string; call_state: string | null; start_ts: string
  hangup_cause: string | null; sip_code: number | null
  max_jitter_ms: number | null; max_packet_loss_pct: number | null
  packets_lost: number | null; report_count: number | null
  avg_jitter_ms: number | null; avg_packet_loss_pct: number | null
}

interface FailedCDR {
  call_id: string; customer_name: string; carrier_name: string
  src_number: string; dst_number: string
  start_ts: string; sip_code: number | null; call_state: string | null
}

function StateBadge({ state }: { state: string }) {
  return <StatusBadge variant={callStateVariant(state)} mono className="font-semibold">{state}</StatusBadge>
}

function sipBadge(code: number | null) {
  if (!code) return <span className="text-[var(--color-muted)]">—</span>
  return <StatusBadge variant={sipCodeVariant(code)} mono className="font-semibold">{code}</StatusBadge>
}

// Quién cortó la llamada — CARRIER (proveedor) es la señal "atenta pero no
// alarmante" (warning); cualquier otra cosa es corte por el cliente (info).
function hangupCauseVariant(cause: string): BadgeVariant {
  return cause === 'CARRIER' ? 'warning' : 'info'
}

// Semáforo de calidad — umbrales típicos de VoIP: jitter y pérdida de
// paquetes, se toma el peor de los dos. La idea es que alguien que no sabe
// qué es "jitter" igual entienda de un vistazo si la llamada estuvo bien.
type QualityLevel = 'buena' | 'regular' | 'mala'
const QUALITY_VARIANT: Record<QualityLevel, BadgeVariant> = {
  buena: 'success', regular: 'warning', mala: 'danger',
}
function qualityLevel(jitterMs: number, lossPct: number): QualityLevel {
  if (jitterMs > 60 || lossPct > 3) return 'mala'
  if (jitterMs > 30 || lossPct > 1) return 'regular'
  return 'buena'
}
function QualityBadge({ jitterMs, lossPct }: { jitterMs: number; lossPct: number }) {
  const level = qualityLevel(jitterMs, lossPct)
  return (
    <StatusBadge variant={QUALITY_VARIANT[level]} dot className="font-semibold">
      {level === 'buena' ? 'Buena' : level === 'regular' ? 'Regular' : 'Mala'}
    </StatusBadge>
  )
}

function CdrDetailPanel({ row, onClose }: { row: CDR; onClose: () => void }) {
  const state = resolveState(row)
  const hasQuality = row.max_jitter_ms != null || row.max_packet_loss_pct != null

  const [msgs, setMsgs] = useState<TraceMsg[]>([])
  const [loadingTrace, setLoadingTrace] = useState(true)
  const [sbcIps, setSbcIps] = useState<{ priv: string; pub: string }>({ priv: '', pub: '' })

  useEffect(() => {
    let cancelled = false
    setLoadingTrace(true)
    apiGet(`/admin/traces?${new URLSearchParams({ call_id: row.call_id })}`)
      .then(d => {
        if (cancelled) return
        setMsgs(d.messages ?? [])
        setSbcIps({ priv: d.sbc_private_ip ?? '', pub: d.sbc_public_ip ?? '' })
      })
      .catch(() => { /* silencioso — la traza es un detalle opcional del panel, no bloquea el resto */ })
      .finally(() => { if (!cancelled) setLoadingTrace(false) })
    return () => { cancelled = true }
  }, [row.call_id])

  async function downloadPcap() {
    try {
      const res = await apiFetch(`/admin/traces/pcap?${new URLSearchParams({ call_id: row.call_id })}`)
      if (!res.ok) { alert('No se pudo generar el PCAP'); return }
      const blob = await res.blob()
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href     = url
      a.download = `trace-${row.call_id.slice(0, 40)}.pcap`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      alert('Error al descargar PCAP')
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--color-border)]">
        <button onClick={onClose} className="flex items-center gap-1.5 text-sm text-[var(--color-text-2)] hover:text-[var(--color-text)] focus-ring rounded">
          ← Volver a resultados
        </button>
        <button onClick={onClose} className="text-[var(--color-muted)] hover:text-[var(--color-text)] text-lg leading-none focus-ring rounded">✕</button>
      </div>

      <div className="p-5 space-y-5">
        <table className="w-full text-sm border border-[var(--color-border)] rounded-lg overflow-hidden">
          <tbody className="divide-y divide-[var(--color-border)]">
            <tr className="bg-[var(--color-surface)]/40">
              <td colSpan={2} className="px-4 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Llamada</td>
            </tr>
            <tr><td className="w-40 px-4 py-2 text-[var(--color-muted)]">Fecha</td><td className="px-4 py-2 font-mono text-[var(--color-text)]">{dt(row.start_ts)}</td></tr>
            <tr><td className="px-4 py-2 text-[var(--color-muted)]">Duración total</td><td className="px-4 py-2 font-mono text-[var(--color-text)]">{sec(row.sessiontime)}</td></tr>
            <tr><td className="px-4 py-2 text-[var(--color-muted)]">Tiempo hablado</td><td className="px-4 py-2 font-mono text-[var(--color-text)]">{sec(row.billsec)}{row.sessiontime > row.billsec && (
              <span className="ml-2 text-xs text-[var(--color-muted)]">(timbró {sec(row.sessiontime - row.billsec)} antes de contestar)</span>
            )}</td></tr>
            <tr><td className="px-4 py-2 text-[var(--color-muted)]">Origen</td><td className="px-4 py-2 font-mono text-[var(--color-text)]">{row.src_number}</td></tr>
            <tr><td className="px-4 py-2 text-[var(--color-muted)]">Destino</td><td className="px-4 py-2 font-mono text-[var(--color-text)]">{row.dst_number}</td></tr>
            <tr><td className="px-4 py-2 text-[var(--color-muted)]">Cliente</td><td className="px-4 py-2 text-[var(--color-text)]">{row.customer_name}</td></tr>
            <tr><td className="px-4 py-2 text-[var(--color-muted)]">Carrier</td><td className="px-4 py-2 text-[var(--color-text-2)]">{row.carrier_name}</td></tr>

            <tr className="bg-[var(--color-surface)]/40">
              <td colSpan={2} className="px-4 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Facturación</td>
            </tr>
            <tr><td className="px-4 py-2 text-[var(--color-muted)]">Compra</td><td className="px-4 py-2 font-mono text-[var(--color-text-2)]">{money(row.buycost)}</td></tr>
            <tr><td className="px-4 py-2 text-[var(--color-muted)]">Venta</td><td className="px-4 py-2 font-mono text-[var(--color-text)]">{money(row.sessionbill)}</td></tr>
            <tr><td className="px-4 py-2 text-[var(--color-muted)]">Ganancia</td><td className="px-4 py-2 font-mono text-success">{money(row.lucro)}</td></tr>

            <tr className="bg-[var(--color-surface)]/40">
              <td colSpan={2} className="px-4 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Estado</td>
            </tr>
            <tr>
              <td className="px-4 py-2.5 text-[var(--color-muted)]">Resultado</td>
              <td className="px-4 py-2.5"><StateBadge state={state} /></td>
            </tr>
            <tr>
              <td className="px-4 py-2.5 text-[var(--color-muted)]">Código SIP</td>
              <td className="px-4 py-2.5">{sipBadge(row.sip_code ?? 200)}</td>
            </tr>
            <tr>
              <td className="px-4 py-2.5 text-[var(--color-muted)]">Colgó</td>
              <td className="px-4 py-2.5">
                {row.hangup_cause ? (
                  <StatusBadge variant={hangupCauseVariant(row.hangup_cause)} className="font-medium">
                    {row.hangup_cause === 'CARRIER' ? 'Proveedor' : 'Cliente'}
                  </StatusBadge>
                ) : <span className="text-[var(--color-muted)] text-xs">Sin dato de quién cortó</span>}
              </td>
            </tr>

            <tr className="bg-[var(--color-surface)]/40">
              <td colSpan={2} className="px-4 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Calidad (RTP)</td>
            </tr>
            {hasQuality ? (
              <>
                <tr>
                  <td className="px-4 py-2.5 text-[var(--color-muted)]">Calidad</td>
                  <td className="px-4 py-2.5">
                    <QualityBadge jitterMs={row.avg_jitter_ms ?? row.max_jitter_ms ?? 0} lossPct={row.avg_packet_loss_pct ?? row.max_packet_loss_pct ?? 0} />
                  </td>
                </tr>
                <tr><td className="px-4 py-2 text-[var(--color-muted)]">Jitter (promedio)</td><td className="px-4 py-2 font-mono text-[var(--color-text-2)]">{(row.avg_jitter_ms ?? 0).toFixed(3)}ms</td></tr>
                <tr><td className="px-4 py-2 text-[var(--color-muted)]">Pérdida (promedio)</td><td className="px-4 py-2 font-mono text-[var(--color-text-2)]">{(row.avg_packet_loss_pct ?? 0).toFixed(2)}%</td></tr>
                <tr><td className="px-4 py-2 text-[var(--color-muted)]">Jitter (peor)</td><td className="px-4 py-2 font-mono text-[var(--color-muted)]">{(row.max_jitter_ms ?? 0).toFixed(0)}ms</td></tr>
                <tr><td className="px-4 py-2 text-[var(--color-muted)]">Pérdida (peor)</td><td className="px-4 py-2 font-mono text-[var(--color-muted)]">{(row.max_packet_loss_pct ?? 0).toFixed(1)}%</td></tr>
                <tr><td className="px-4 py-2 text-[var(--color-muted)]">Paquetes perdidos</td><td className="px-4 py-2 font-mono text-[var(--color-text-2)]">{row.packets_lost ?? 0}</td></tr>
                <tr><td className="px-4 py-2 text-[var(--color-muted)]">Reportes RTCP</td><td className="px-4 py-2 font-mono text-[var(--color-text-2)]">{row.report_count ?? 0}</td></tr>
              </>
            ) : (
              <tr><td colSpan={2} className="px-4 py-3 text-xs text-[var(--color-muted)]">Sin datos de calidad — la llamada no alcanzó a generar ningún reporte RTCP antes de terminar.</td></tr>
            )}
          </tbody>
        </table>

        <div>
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs text-[var(--color-muted)] uppercase tracking-wider">Traza SIP</p>
            <button onClick={downloadPcap} disabled={loadingTrace || msgs.length === 0}
              className="px-2 py-1 rounded text-xs font-mono bg-brand-500/10 text-brand-400 hover:bg-brand-500/20 disabled:opacity-30 disabled:cursor-not-allowed focus-ring">
              ⬇ Descargar PCAP
            </button>
          </div>
          <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg">
            {loadingTrace ? (
              <p className="p-8 text-center text-[var(--color-muted)] text-sm">Cargando traza…</p>
            ) : (
              <SipLadder msgs={msgs} sbcPrivateIp={sbcIps.priv} sbcPublicIp={sbcIps.pub} />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function resolveState(row: CDR): string {
  if (row.call_state) return row.call_state
  const map: Record<string, string> = {
    ANSWERED: 'COMPLETED', BUSY: 'BUSY', NO_ANSWER: 'CANCELLED', FAILED: 'REJECTED',
    RESTART_ORPHANED: 'INTERRUMPIDA POR REINICIO',
  }
  return map[row.disposition] ?? row.disposition
}

function sec(s: number) { return `${Math.floor(s/60)}m ${s%60}s` }
function money(n: number) { return `S/ ${(+n).toFixed(4)}` }
function dt(s: string) { return new Date(s).toLocaleString('es-PE') }

const LIMIT = 70
function todayStr() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export default function CdrsPage() {
  const [tab, setTab] = useState<'ok' | 'failed'>('ok')
  const [selected, setSelected] = useState<CDR | null>(null)

  // ── Tab: establecidas ────────────────────────────────────────────────────
  const [rows, setRows]   = useState<CDR[]>([])
  const [total, setTotal] = useState(0)
  const [error, setError] = useState('')
  const [loadingOk, setLoadingOk] = useState(false)
  const [offsetOk, setOffsetOk]   = useState(0)
  const [fOk, setFOk] = useState({ date_from: todayStr(), date_to: todayStr(), customer_id:'', carrier_id:'', phone:'' })
  const [hasSearchedOk, setHasSearchedOk] = useState(false)

  async function loadOk(off = 0, overrides?: Partial<typeof fOk>) {
    setLoadingOk(true)
    setSelected(null)   // una búsqueda o cambio de página nueva vuelve a mostrar la tabla
    setError('')
    try {
      const merged = { ...fOk, ...overrides }
      const p = new URLSearchParams({ limit: String(LIMIT), offset: String(off) })
      Object.entries(merged).forEach(([k, v]) => v && p.set(k, v))
      const r = await apiFetch(`/admin/cdrs?${p}`)
      if (!r.ok) throw new Error(`Error ${r.status} buscando CDRs`)
      const d = await r.json()
      setRows(d.rows); setTotal(d.total); setOffsetOk(off)
      setHasSearchedOk(true)
    } catch (e: any) { setError(e.message || 'Error cargando CDRs') }
    finally { setLoadingOk(false) }
  }

  // ── Tab: fallidas ────────────────────────────────────────────────────────
  const [failed, setFailed]         = useState<FailedCDR[]>([])
  const [totalFailed, setTotalFailed] = useState(0)
  const [loadingFail, setLoadingFail] = useState(false)
  const [offsetFail, setOffsetFail]   = useState(0)
  const [fFail, setFFail] = useState({ date_from: todayStr(), date_to: todayStr(), sip_code:'', customer_id:'', carrier_id:'', phone:'' })
  const [hasSearchedFail, setHasSearchedFail] = useState(false)

  async function loadFail(off = 0, overrides?: Partial<typeof fFail>) {
    setLoadingFail(true); setError('')
    try {
      const merged = { ...fFail, ...overrides }
      const p = new URLSearchParams({ limit: String(LIMIT), offset: String(off) })
      Object.entries(merged).forEach(([k, v]) => v && p.set(k, v))
      const r = await apiFetch(`/admin/cdrs/failed?${p}`)
      if (!r.ok) throw new Error(`Error ${r.status} buscando CDRs fallidas`)
      const d = await r.json()
      setFailed(d.rows); setTotalFailed(d.total); setOffsetFail(off)
      setHasSearchedFail(true)
    } catch (e: any) { setError(e.message || 'Error cargando CDRs fallidas') }
    finally { setLoadingFail(false) }
  }

  const pagesOk   = Math.ceil(total / LIMIT) || 1
  const pageOk    = Math.floor(offsetOk / LIMIT) + 1
  const pagesFail = Math.ceil(totalFailed / LIMIT) || 1
  const pageFail  = Math.floor(offsetFail / LIMIT) + 1

  return (
    <div className="space-y-4">
      {error && <ErrorBanner>{error}</ErrorBanner>}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-[var(--color-text)]">CDRs</h1>
        {/* Tabs */}
        <div className="flex rounded-lg overflow-hidden border border-[var(--color-border)]">
          <button
            onClick={() => { setTab('ok'); setSelected(null) }}
            className={`px-4 py-1.5 text-sm font-medium transition-colors focus-ring ${tab === 'ok' ? 'bg-success text-white' : 'bg-[var(--color-card-2)] text-[var(--color-text-2)] hover:text-[var(--color-text)]'}`}
          >
            ✓ Contestadas (200 OK) {tab === 'ok' && total > 0 && <span className="ml-1 text-xs opacity-70">{total.toLocaleString()}</span>}
          </button>
          <button
            onClick={() => { setTab('failed'); setSelected(null) }}
            className={`px-4 py-1.5 text-sm font-medium transition-colors focus-ring ${tab === 'failed' ? 'bg-danger text-white' : 'bg-[var(--color-card-2)] text-[var(--color-text-2)] hover:text-[var(--color-text)]'}`}
          >
            ✗ No establecidas {tab === 'failed' && totalFailed > 0 && <span className="ml-1 text-xs opacity-70">{totalFailed.toLocaleString()}</span>}
          </button>
        </div>
      </div>

      {/* ── TAB: ESTABLECIDAS ─────────────────────────────────────────────── */}
      {tab === 'ok' && (
        <>
          <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-4">
            <div className="flex flex-wrap gap-3 items-end">
              <div>
                <label className="block text-xs text-[var(--color-text-2)] mb-1">Teléfono (origen o destino)</label>
                <input
                  type="text" placeholder="51999..." value={fOk.phone}
                  onChange={e => setFOk(v => ({...v, phone: e.target.value}))}
                  onKeyDown={e => e.key === 'Enter' && fOk.phone.trim() && loadOk(0)}
                  className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-3 py-1.5 text-sm text-[var(--color-text)] font-mono w-44 focus-ring" />
              </div>
              {[['date_from','Desde','date'],['date_to','Hasta','date']].map(([k,l,t]) => (
                <div key={k}>
                  <label className="block text-xs text-[var(--color-text-2)] mb-1">{l}</label>
                  <input type={t} value={fOk[k as keyof typeof fOk]}
                    onChange={e => setFOk(v => ({...v, [k]: e.target.value}))}
                    className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-3 py-1.5 text-sm text-[var(--color-text)] focus-ring" />
                </div>
              ))}
              <button onClick={() => loadOk(0)} disabled={!fOk.phone.trim()}
                title={!fOk.phone.trim() ? 'Ingresá un teléfono para buscar' : ''}
                className="px-4 py-1.5 bg-brand-600 hover:bg-brand-500 disabled:opacity-30 disabled:cursor-not-allowed text-white text-sm rounded focus-ring">Buscar</button>
              <button onClick={() => { setFOk({ date_from: todayStr(), date_to: todayStr(), customer_id:'',carrier_id:'',phone:'' }); setRows([]); setTotal(0); setHasSearchedOk(false) }}
                className="px-4 py-1.5 bg-[var(--color-card-2)] hover:bg-[var(--color-border-2)] text-[var(--color-text)] text-sm rounded focus-ring">Limpiar</button>
            </div>
          </div>

          <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl overflow-x-auto">
            {selected ? (
              <CdrDetailPanel row={selected} onClose={() => setSelected(null)} />
            ) : !hasSearchedOk ? (
              <p className="p-10 text-center text-[var(--color-muted)] text-sm">Ingresá un teléfono (origen o destino) y hacé clic en Buscar.</p>
            ) : loadingOk ? <p className="p-8 text-center text-[var(--color-text-2)] text-sm">Cargando…</p> : (
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-[var(--color-text-2)] uppercase border-b border-[var(--color-border)]">
                    {['Fecha','Origen','Destino','Cliente','Tiempo'].map(h => (
                      <th key={h} className="px-4 py-3 text-left">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--color-border)]">
                  {rows.map(r => (
                    <ClickableRow key={r.call_id} onActivate={() => setSelected(r)} className="hover:bg-white/2 cursor-pointer">
                      <td className="px-4 py-2 font-mono text-[var(--color-text-2)]">{dt(r.start_ts)}</td>
                      <td className="px-4 py-2 font-mono text-[var(--color-text)]">{r.src_number}</td>
                      <td className="px-4 py-2 font-mono text-[var(--color-text)] font-medium">{r.dst_number}</td>
                      <td className="px-4 py-2 text-[var(--color-text)]">{r.customer_name}</td>
                      <td className="px-4 py-2 font-mono">{sec(r.billsec)}</td>
                    </ClickableRow>
                  ))}
                  {rows.length === 0 && <tr><td colSpan={5} className="px-6 py-10 text-center text-[var(--color-muted)]">Sin registros</td></tr>}
                </tbody>
              </table>
            )}
          </div>

          {total > LIMIT && !selected && (
            <div className="flex items-center justify-between text-sm">
              <span className="text-[var(--color-text-2)]">Página {pageOk} de {pagesOk}</span>
              <div className="flex gap-2">
                <button disabled={offsetOk===0} onClick={() => loadOk(offsetOk-LIMIT)}
                  className="px-3 py-1 bg-[var(--color-card-2)] hover:bg-[var(--color-border-2)] text-[var(--color-text)] rounded disabled:opacity-30 focus-ring">← Anterior</button>
                <button disabled={offsetOk+LIMIT>=total} onClick={() => loadOk(offsetOk+LIMIT)}
                  className="px-3 py-1 bg-[var(--color-card-2)] hover:bg-[var(--color-border-2)] text-[var(--color-text)] rounded disabled:opacity-30 focus-ring">Siguiente →</button>
              </div>
            </div>
          )}
        </>
      )}

      {/* ── TAB: FALLIDAS ─────────────────────────────────────────────────── */}
      {tab === 'failed' && (
        <>
          <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-4 space-y-3">
            <div className="flex flex-wrap gap-3 items-end">
              <div>
                <label className="block text-xs text-[var(--color-text-2)] mb-1">Teléfono (origen o destino)</label>
                <input
                  type="text" placeholder="51999..." value={fFail.phone}
                  onChange={e => setFFail(v => ({...v, phone: e.target.value}))}
                  onKeyDown={e => e.key === 'Enter' && loadFail(0)}
                  className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-3 py-1.5 text-sm text-[var(--color-text)] font-mono w-44 focus-ring" />
              </div>
              {[['date_from','Desde','date'],['date_to','Hasta','date']].map(([k,l,t]) => (
                <div key={k}>
                  <label className="block text-xs text-[var(--color-text-2)] mb-1">{l}</label>
                  <input type={t} value={fFail[k as keyof typeof fFail]}
                    onChange={e => setFFail(v => ({...v, [k]: e.target.value}))}
                    className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-3 py-1.5 text-sm text-[var(--color-text)] focus-ring" />
                </div>
              ))}
              <div>
                <label className="block text-xs text-[var(--color-text-2)] mb-1">Código SIP</label>
                <select value={fFail.sip_code} onChange={e => setFFail(v => ({...v, sip_code: e.target.value}))}
                  className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-3 py-1.5 text-sm text-[var(--color-text)] focus-ring">
                  <option value="">Todos</option>
                  <option value="487">487 – Cancelled</option>
                  <option value="486">486 – Busy</option>
                  <option value="404">404 – Not Found</option>
                  <option value="503">503 – Unavailable</option>
                  <option value="408">408 – Timeout</option>
                </select>
              </div>
              <button onClick={() => loadFail(0)} className="px-4 py-1.5 bg-brand-600 hover:bg-brand-500 text-white text-sm rounded focus-ring">Buscar</button>
              <button onClick={() => { setFFail({ date_from: todayStr(), date_to: todayStr(), sip_code:'',customer_id:'',carrier_id:'',phone:'' }); setFailed([]); setTotalFailed(0); setHasSearchedFail(false) }}
                className="px-4 py-1.5 bg-[var(--color-card-2)] hover:bg-[var(--color-border-2)] text-[var(--color-text)] text-sm rounded focus-ring">Limpiar</button>
            </div>
            {/* Botones rápidos por código */}
            <div className="flex gap-2">
              <span className="text-xs text-[var(--color-muted)] self-center">Acceso rápido:</span>
              {[['487','Canceladas'],['486','Ocupado'],['404','No existe'],['503','Sin servicio']].map(([code, label]) => (
                <button key={code}
                  onClick={() => {
                    const next = fFail.sip_code === code ? '' : code
                    setFFail(v => ({...v, sip_code: next}))
                    loadFail(0, { sip_code: next })
                  }}
                  className={`px-3 py-1 text-xs rounded-full border transition-colors focus-ring ${fFail.sip_code===code ? 'bg-danger border-danger text-white' : 'border-[var(--color-border)] text-[var(--color-text-2)] hover:text-[var(--color-text)] hover:border-[var(--color-border-2)]'}`}
                >{code} {label}</button>
              ))}
            </div>
          </div>

          <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl overflow-x-auto">
            {!hasSearchedFail ? (
              <p className="p-10 text-center text-[var(--color-muted)] text-sm">Buscá por teléfono, fecha o código SIP para ver resultados.</p>
            ) : loadingFail ? <p className="p-8 text-center text-[var(--color-text-2)] text-sm">Cargando…</p> : (
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-[var(--color-text-2)] uppercase border-b border-[var(--color-border)]">
                    {['Fecha','Cliente','Carrier','Origen','Destino','Cód SIP','Estado','Traza'].map(h => (
                      <th key={h} className="px-4 py-3 text-left">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--color-border)]">
                  {failed.map(r => (
                    <tr key={r.call_id} className="hover:bg-white/2">
                      <td className="px-4 py-2 font-mono text-[var(--color-text-2)]">{dt(r.start_ts)}</td>
                      <td className="px-4 py-2 text-[var(--color-text)]">{r.customer_name}</td>
                      <td className="px-4 py-2 text-[var(--color-text-2)]">{r.carrier_name}</td>
                      <td className="px-4 py-2 font-mono text-[var(--color-text)]">{r.src_number}</td>
                      <td className="px-4 py-2 font-mono text-[var(--color-text)] font-medium">{r.dst_number}</td>
                      <td className="px-4 py-2">{sipBadge(r.sip_code)}</td>
                      <td className="px-4 py-2">
                        {r.call_state
                          ? <StateBadge state={r.call_state} />
                          : <span className="text-[var(--color-muted)]">—</span>}
                      </td>
                      <td className="px-4 py-2">
                        <a href={`/traces?call_id=${encodeURIComponent(r.call_id)}`}
                          className="px-2 py-0.5 rounded text-xs font-mono bg-brand-500/10 text-brand-400 hover:bg-brand-500/20 focus-ring">SIP</a>
                      </td>
                    </tr>
                  ))}
                  {failed.length === 0 && <tr><td colSpan={8} className="px-6 py-10 text-center text-[var(--color-muted)]">Sin registros</td></tr>}
                </tbody>
              </table>
            )}
          </div>

          {totalFailed > LIMIT && (
            <div className="flex items-center justify-between text-sm">
              <span className="text-[var(--color-text-2)]">Página {pageFail} de {pagesFail}</span>
              <div className="flex gap-2">
                <button disabled={offsetFail===0} onClick={() => loadFail(offsetFail-LIMIT)}
                  className="px-3 py-1 bg-[var(--color-card-2)] hover:bg-[var(--color-border-2)] text-[var(--color-text)] rounded disabled:opacity-30 focus-ring">← Anterior</button>
                <button disabled={offsetFail+LIMIT>=totalFailed} onClick={() => loadFail(offsetFail+LIMIT)}
                  className="px-3 py-1 bg-[var(--color-card-2)] hover:bg-[var(--color-border-2)] text-[var(--color-text)] rounded disabled:opacity-30 focus-ring">Siguiente →</button>
              </div>
            </div>
          )}
        </>
      )}

    </div>
  )
}
