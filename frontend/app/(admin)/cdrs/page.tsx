'use client'
import { useEffect, useState } from 'react'
import { apiFetch } from '@/lib/api'

interface CDR {
  call_id: string; customer_name: string; carrier_name: string
  src_number: string; dst_number: string
  billsec: number; buycost: number; sessionbill: number; lucro: number
  disposition: string; call_state: string | null; start_ts: string
  hangup_cause: string | null; sip_code: number | null
}

interface FailedCDR {
  call_id: string; customer_name: string; carrier_name: string
  src_number: string; dst_number: string
  start_ts: string; sip_code: number | null; call_state: string | null
}

const STATE_STYLE: Record<string, string> = {
  COMPLETED:  'bg-green-500/15 text-green-400',
  BUSY:       'bg-yellow-500/15 text-yellow-400',
  CANCELLED:  'bg-zinc-500/15 text-zinc-400',
  REJECTED:   'bg-red-500/15 text-red-400',
  DIVERTED:   'bg-blue-500/15 text-blue-400',
  'NO ANSWER':'bg-zinc-500/15 text-zinc-400',
}

function sipBadge(code: number | null) {
  if (!code) return <span className="text-zinc-600">—</span>
  const cls =
    code < 300 ? 'bg-green-500/15 text-green-400' :
    code < 400 ? 'bg-blue-500/15 text-blue-400' :
    code < 500 ? 'bg-orange-500/15 text-orange-400' :
                 'bg-red-500/15 text-red-400'
  return <span className={`px-2 py-0.5 rounded font-mono text-xs font-semibold ${cls}`}>{code}</span>
}

function resolveState(row: CDR): string {
  if (row.call_state) return row.call_state
  const map: Record<string, string> = {
    ANSWERED: 'COMPLETED', BUSY: 'BUSY', NO_ANSWER: 'CANCELLED', FAILED: 'REJECTED',
  }
  return map[row.disposition] ?? row.disposition
}

function sec(s: number) { return `${Math.floor(s/60)}m ${s%60}s` }
function money(n: number) { return `S/ ${(+n).toFixed(4)}` }
function dt(s: string) { return new Date(s).toLocaleString('es-PE') }

const LIMIT = 70

export default function CdrsPage() {
  const [tab, setTab] = useState<'ok' | 'failed'>('ok')

  // ── Tab: establecidas ────────────────────────────────────────────────────
  const [rows, setRows]   = useState<CDR[]>([])
  const [total, setTotal] = useState(0)
  const [loadingOk, setLoadingOk] = useState(false)
  const [offsetOk, setOffsetOk]   = useState(0)
  const [fOk, setFOk] = useState({ date_from:'', date_to:'', customer_id:'', carrier_id:'', phone:'' })

  async function loadOk(off = 0, overrides?: Partial<typeof fOk>) {
    setLoadingOk(true)
    try {
      const merged = { ...fOk, ...overrides }
      const p = new URLSearchParams({ limit: String(LIMIT), offset: String(off) })
      Object.entries(merged).forEach(([k, v]) => v && p.set(k, v))
      const r = await apiFetch(`/admin/cdrs?${p}`)
      const d = await r.json()
      setRows(d.rows); setTotal(d.total); setOffsetOk(off)
    } finally { setLoadingOk(false) }
  }

  // ── Tab: fallidas ────────────────────────────────────────────────────────
  const [failed, setFailed]         = useState<FailedCDR[]>([])
  const [totalFailed, setTotalFailed] = useState(0)
  const [loadingFail, setLoadingFail] = useState(false)
  const [offsetFail, setOffsetFail]   = useState(0)
  const [fFail, setFFail] = useState({ date_from:'', date_to:'', sip_code:'', customer_id:'', carrier_id:'', phone:'' })

  async function loadFail(off = 0, overrides?: Partial<typeof fFail>) {
    setLoadingFail(true)
    try {
      const merged = { ...fFail, ...overrides }
      const p = new URLSearchParams({ limit: String(LIMIT), offset: String(off) })
      Object.entries(merged).forEach(([k, v]) => v && p.set(k, v))
      const r = await apiFetch(`/admin/cdrs/failed?${p}`)
      const d = await r.json()
      setFailed(d.rows); setTotalFailed(d.total); setOffsetFail(off)
    } finally { setLoadingFail(false) }
  }

  useEffect(() => { loadOk(0) }, [])
  useEffect(() => { if (tab === 'failed' && failed.length === 0) loadFail(0) }, [tab])

  const pagesOk   = Math.ceil(total / LIMIT) || 1
  const pageOk    = Math.floor(offsetOk / LIMIT) + 1
  const pagesFail = Math.ceil(totalFailed / LIMIT) || 1
  const pageFail  = Math.floor(offsetFail / LIMIT) + 1

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-white">CDRs</h1>
        {/* Tabs */}
        <div className="flex rounded-lg overflow-hidden border border-zinc-700">
          <button
            onClick={() => setTab('ok')}
            className={`px-4 py-1.5 text-sm font-medium transition-colors ${tab === 'ok' ? 'bg-green-600 text-white' : 'bg-zinc-800 text-zinc-400 hover:text-white'}`}
          >
            ✓ Contestadas (200 OK) {tab === 'ok' && total > 0 && <span className="ml-1 text-xs opacity-70">{total.toLocaleString()}</span>}
          </button>
          <button
            onClick={() => setTab('failed')}
            className={`px-4 py-1.5 text-sm font-medium transition-colors ${tab === 'failed' ? 'bg-red-700 text-white' : 'bg-zinc-800 text-zinc-400 hover:text-white'}`}
          >
            ✗ No establecidas {tab === 'failed' && totalFailed > 0 && <span className="ml-1 text-xs opacity-70">{totalFailed.toLocaleString()}</span>}
          </button>
        </div>
      </div>

      {/* ── TAB: ESTABLECIDAS ─────────────────────────────────────────────── */}
      {tab === 'ok' && (
        <>
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
            <div className="flex flex-wrap gap-3 items-end">
              <div>
                <label className="block text-xs text-zinc-400 mb-1">Teléfono (origen o destino)</label>
                <input
                  type="text" placeholder="51999..." value={fOk.phone}
                  onChange={e => setFOk(v => ({...v, phone: e.target.value}))}
                  onKeyDown={e => e.key === 'Enter' && loadOk(0)}
                  className="bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-sm text-white font-mono w-44" />
              </div>
              {[['date_from','Desde','date'],['date_to','Hasta','date']].map(([k,l,t]) => (
                <div key={k}>
                  <label className="block text-xs text-zinc-400 mb-1">{l}</label>
                  <input type={t} value={fOk[k as keyof typeof fOk]}
                    onChange={e => setFOk(v => ({...v, [k]: e.target.value}))}
                    className="bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-sm text-white" />
                </div>
              ))}
              <button onClick={() => loadOk(0)} className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded">Filtrar</button>
              <button onClick={() => { setFOk({ date_from:'',date_to:'',customer_id:'',carrier_id:'',phone:'' }); loadOk(0) }}
                className="px-4 py-1.5 bg-zinc-700 hover:bg-zinc-600 text-white text-sm rounded">Limpiar</button>
            </div>
          </div>

          <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
            {loadingOk ? <p className="p-8 text-center text-zinc-400 text-sm">Cargando…</p> : (
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-zinc-400 uppercase border-b border-zinc-800">
                    {['Fecha','Cliente','Carrier','Origen','Destino','Seg','Compra','Venta','Ganancia','Cortó','Cód SIP','Traza'].map(h => (
                      <th key={h} className="px-4 py-3 text-left">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800">
                  {rows.map(r => {
                    const state = resolveState(r)
                    return (
                      <tr key={r.call_id} className="hover:bg-zinc-800/50">
                        <td className="px-4 py-2 font-mono text-zinc-400">{dt(r.start_ts)}</td>
                        <td className="px-4 py-2 text-white">{r.customer_name}</td>
                        <td className="px-4 py-2 text-zinc-400">{r.carrier_name}</td>
                        <td className="px-4 py-2 font-mono text-zinc-300">{r.src_number}</td>
                        <td className="px-4 py-2 font-mono text-white font-medium">{r.dst_number}</td>
                        <td className="px-4 py-2 font-mono">{sec(r.billsec)}</td>
                        <td className="px-4 py-2 font-mono text-red-400">{money(r.buycost)}</td>
                        <td className="px-4 py-2 font-mono text-blue-400">{money(r.sessionbill)}</td>
                        <td className="px-4 py-2 font-mono text-green-400">{money(r.lucro)}</td>
                        <td className="px-4 py-2">
                          {r.hangup_cause
                            ? <span className={`px-2 py-0.5 rounded text-xs font-medium ${r.hangup_cause === 'CARRIER' ? 'bg-orange-500/15 text-orange-400' : 'bg-blue-500/15 text-blue-400'}`}>{r.hangup_cause}</span>
                            : <span className="text-zinc-600">—</span>}
                        </td>
                        <td className="px-4 py-2">{sipBadge(r.sip_code ?? 200)}</td>
                        <td className="px-4 py-2">
                          <a href={`/traces?call_id=${encodeURIComponent(r.call_id)}`}
                            className="px-2 py-0.5 rounded text-xs font-mono bg-brand-500/10 text-brand-400 hover:bg-brand-500/20">SIP</a>
                        </td>
                      </tr>
                    )
                  })}
                  {rows.length === 0 && <tr><td colSpan={12} className="px-6 py-10 text-center text-zinc-500">Sin registros</td></tr>}
                </tbody>
              </table>
            )}
          </div>

          {total > LIMIT && (
            <div className="flex items-center justify-between text-sm">
              <span className="text-zinc-400">Página {pageOk} de {pagesOk}</span>
              <div className="flex gap-2">
                <button disabled={offsetOk===0} onClick={() => loadOk(offsetOk-LIMIT)}
                  className="px-3 py-1 bg-zinc-800 hover:bg-zinc-700 text-white rounded disabled:opacity-30">← Anterior</button>
                <button disabled={offsetOk+LIMIT>=total} onClick={() => loadOk(offsetOk+LIMIT)}
                  className="px-3 py-1 bg-zinc-800 hover:bg-zinc-700 text-white rounded disabled:opacity-30">Siguiente →</button>
              </div>
            </div>
          )}
        </>
      )}

      {/* ── TAB: FALLIDAS ─────────────────────────────────────────────────── */}
      {tab === 'failed' && (
        <>
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-3">
            <div className="flex flex-wrap gap-3 items-end">
              <div>
                <label className="block text-xs text-zinc-400 mb-1">Teléfono (origen o destino)</label>
                <input
                  type="text" placeholder="51999..." value={fFail.phone}
                  onChange={e => setFFail(v => ({...v, phone: e.target.value}))}
                  onKeyDown={e => e.key === 'Enter' && loadFail(0)}
                  className="bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-sm text-white font-mono w-44" />
              </div>
              {[['date_from','Desde','date'],['date_to','Hasta','date']].map(([k,l,t]) => (
                <div key={k}>
                  <label className="block text-xs text-zinc-400 mb-1">{l}</label>
                  <input type={t} value={fFail[k as keyof typeof fFail]}
                    onChange={e => setFFail(v => ({...v, [k]: e.target.value}))}
                    className="bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-sm text-white" />
                </div>
              ))}
              <div>
                <label className="block text-xs text-zinc-400 mb-1">Código SIP</label>
                <select value={fFail.sip_code} onChange={e => setFFail(v => ({...v, sip_code: e.target.value}))}
                  className="bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-sm text-white">
                  <option value="">Todos</option>
                  <option value="487">487 – Cancelled</option>
                  <option value="486">486 – Busy</option>
                  <option value="404">404 – Not Found</option>
                  <option value="503">503 – Unavailable</option>
                  <option value="408">408 – Timeout</option>
                </select>
              </div>
              <button onClick={() => loadFail(0)} className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded">Filtrar</button>
              <button onClick={() => { setFFail({ date_from:'',date_to:'',sip_code:'',customer_id:'',carrier_id:'',phone:'' }); loadFail(0) }}
                className="px-4 py-1.5 bg-zinc-700 hover:bg-zinc-600 text-white text-sm rounded">Limpiar</button>
            </div>
            {/* Botones rápidos por código */}
            <div className="flex gap-2">
              <span className="text-xs text-zinc-500 self-center">Acceso rápido:</span>
              {[['487','Canceladas'],['486','Ocupado'],['404','No existe'],['503','Sin servicio']].map(([code, label]) => (
                <button key={code}
                  onClick={() => {
                    const next = fFail.sip_code === code ? '' : code
                    setFFail(v => ({...v, sip_code: next}))
                    loadFail(0, { sip_code: next })
                  }}
                  className={`px-3 py-1 text-xs rounded-full border transition-colors ${fFail.sip_code===code ? 'bg-red-700 border-red-600 text-white' : 'border-zinc-700 text-zinc-400 hover:text-white hover:border-zinc-500'}`}
                >{code} {label}</button>
              ))}
            </div>
          </div>

          <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
            {loadingFail ? <p className="p-8 text-center text-zinc-400 text-sm">Cargando…</p> : (
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-zinc-400 uppercase border-b border-zinc-800">
                    {['Fecha','Cliente','Carrier','Origen','Destino','Cód SIP','Estado','Traza'].map(h => (
                      <th key={h} className="px-4 py-3 text-left">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800">
                  {failed.map(r => (
                    <tr key={r.call_id} className="hover:bg-zinc-800/50">
                      <td className="px-4 py-2 font-mono text-zinc-400">{dt(r.start_ts)}</td>
                      <td className="px-4 py-2 text-white">{r.customer_name}</td>
                      <td className="px-4 py-2 text-zinc-400">{r.carrier_name}</td>
                      <td className="px-4 py-2 font-mono text-zinc-300">{r.src_number}</td>
                      <td className="px-4 py-2 font-mono text-white font-medium">{r.dst_number}</td>
                      <td className="px-4 py-2">{sipBadge(r.sip_code)}</td>
                      <td className="px-4 py-2">
                        {r.call_state
                          ? <span className={`px-2 py-0.5 rounded font-semibold text-xs ${STATE_STYLE[r.call_state] ?? STATE_STYLE.REJECTED}`}>{r.call_state}</span>
                          : <span className="text-zinc-600">—</span>}
                      </td>
                      <td className="px-4 py-2">
                        <a href={`/traces?call_id=${encodeURIComponent(r.call_id)}`}
                          className="px-2 py-0.5 rounded text-xs font-mono bg-brand-500/10 text-brand-400 hover:bg-brand-500/20">SIP</a>
                      </td>
                    </tr>
                  ))}
                  {failed.length === 0 && <tr><td colSpan={8} className="px-6 py-10 text-center text-zinc-500">Sin registros</td></tr>}
                </tbody>
              </table>
            )}
          </div>

          {totalFailed > LIMIT && (
            <div className="flex items-center justify-between text-sm">
              <span className="text-zinc-400">Página {pageFail} de {pagesFail}</span>
              <div className="flex gap-2">
                <button disabled={offsetFail===0} onClick={() => loadFail(offsetFail-LIMIT)}
                  className="px-3 py-1 bg-zinc-800 hover:bg-zinc-700 text-white rounded disabled:opacity-30">← Anterior</button>
                <button disabled={offsetFail+LIMIT>=totalFailed} onClick={() => loadFail(offsetFail+LIMIT)}
                  className="px-3 py-1 bg-zinc-800 hover:bg-zinc-700 text-white rounded disabled:opacity-30">Siguiente →</button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
