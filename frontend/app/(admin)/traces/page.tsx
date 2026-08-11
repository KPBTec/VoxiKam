'use client'
import { Suspense, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { apiFetch, apiGet } from '@/lib/api'
import { SipLadder, TraceMsg } from '@/components/SipLadder'
import { StatusBadge, sipCodeVariant, sipMethodVariant } from '@/components/StatusBadge'
import { ErrorBanner } from '@/components/ErrorBanner'

// ── Types ──────────────────────────────────────────────────────────────────────

interface StreamMsg {
  id: number; ts: string; call_id: string
  src_ip: string; src_port: number | null
  dst_ip: string; dst_port: number | null
  method: string | null; status: number | null
  from_uri: string | null; to_uri: string | null
  cseq: string | null; user_agent: string | null; reason: string | null
}

interface CallSummary {
  call_id: string; first_ts: string; last_ts: string; msg_count: number
  has_invite: boolean; final_status: number | null
  from_uri: string | null; to_uri: string | null; methods: string[]
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function today() { return new Date().toISOString().slice(0, 10) }

function Badge({ method, status }: { method: string | null; status: number | null }) {
  const label = method ?? String(status ?? '?')
  const variant = status ? sipCodeVariant(status) : sipMethodVariant(method)
  return (
    <StatusBadge variant={variant} bordered mono rounded="md" tight className="font-bold">
      {label}
    </StatusBadge>
  )
}

function tsLocal(s: string) {
  return new Date(s).toLocaleTimeString('es-PE', { hour12: false, fractionalSecondDigits: 3 })
}

// ── Stream live view ───────────────────────────────────────────────────────────

function StreamView({ onCallId }: { onCallId: (id: string) => void }) {
  const [msgs, setMsgs]   = useState<StreamMsg[]>([])
  const [live, setLive]   = useState(false)
  const sinceRef          = useRef(0)
  const liveRef           = useRef(false)
  liveRef.current         = live
  const MAX_ROWS = 500

  async function fetch(reset = false) {
    if (reset) { sinceRef.current = 0 }
    try {
      const p = new URLSearchParams({ since_id: String(sinceRef.current), limit: '200' })
      const d = await apiGet(`/admin/traces/stream?${p}`)
      if (d.messages.length > 0) {
        sinceRef.current = d.messages[d.messages.length - 1].id
        setMsgs(prev => {
          const next = reset ? d.messages : [...prev, ...d.messages]
          return next.slice(-MAX_ROWS)
        })
      }
    } catch { /* fallo transitorio del polling — se reintenta en el próximo tick */ }
  }

  useEffect(() => {
    if (!live) return
    fetch(true)
    const t = setInterval(() => { if (liveRef.current) fetch() }, 1000)
    return () => clearInterval(t)
  }, [live]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="flex flex-col h-full">
      {/* Controls */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-border)] flex-shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setLive(v => !v)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium border transition-colors focus-ring
              ${live ? 'bg-danger/15 text-danger border-danger/40'
                     : 'bg-[var(--color-card-2)] text-[var(--color-text)] border-[var(--color-border)] hover:border-[var(--color-border-2)]'}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${live ? 'bg-danger animate-pulse' : 'bg-[var(--color-muted)]'}`} />
            {live ? 'Detener' : 'Iniciar stream'}
          </button>
          {!live && (
            <button onClick={() => fetch(true)}
              className="px-3 py-1.5 rounded text-xs bg-[var(--color-card-2)] text-[var(--color-text)] border border-[var(--color-border)] hover:border-[var(--color-border-2)] focus-ring">
              Actualizar
            </button>
          )}
          <button onClick={() => setMsgs([])}
            className="px-3 py-1.5 rounded text-xs bg-[var(--color-card-2)] text-[var(--color-text)] border border-[var(--color-border)] hover:border-[var(--color-border-2)] focus-ring">
            Limpiar
          </button>
        </div>
        <span className="text-xs text-[var(--color-muted)]">{msgs.length} mensajes{msgs.length >= MAX_ROWS ? ' (máx)' : ''}</span>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-y-auto">
        {msgs.length === 0 ? (
          <div className="flex items-center justify-center h-full text-[var(--color-muted)] text-sm">
            {live ? 'Esperando tráfico SIP…' : 'Presiona "Iniciar stream" para ver tráfico en vivo'}
          </div>
        ) : (
          <table className="w-full text-xs">
            <thead className="sticky top-0 z-10 bg-[var(--color-card)] border-b border-[var(--color-border)]">
              <tr className="text-[var(--color-muted)] uppercase">
                {['Hora','Origen','Destino','Método','Código','Call-ID','CSeq','Reason'].map(h => (
                  <th key={h} className="px-3 py-2 text-left font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]/50">
              {[...msgs].reverse().map(m => (
                <tr key={m.id} className="hover:bg-white/2 transition-colors">
                  <td className="px-3 py-1.5 font-mono text-[var(--color-muted)] whitespace-nowrap">{tsLocal(m.ts)}</td>
                  <td className="px-3 py-1.5 font-mono text-success whitespace-nowrap">{m.from_uri ?? `${m.src_ip}:${m.src_port}`}</td>
                  <td className="px-3 py-1.5 font-mono text-[var(--color-text)] whitespace-nowrap">{m.to_uri ?? `${m.dst_ip}:${m.dst_port}`}</td>
                  <td className="px-3 py-1.5">
                    {m.method && <Badge method={m.method} status={null} />}
                  </td>
                  <td className="px-3 py-1.5">
                    {m.status && <Badge method={null} status={m.status} />}
                  </td>
                  <td className="px-3 py-1.5 font-mono text-[var(--color-text-2)] max-w-[180px] truncate">
                    <button onClick={() => onCallId(m.call_id)}
                      className="hover:text-brand-400 transition-colors text-left focus-ring"
                      title={m.call_id}>
                      {m.call_id}
                    </button>
                  </td>
                  <td className="px-3 py-1.5 font-mono text-[var(--color-muted)] whitespace-nowrap">{m.cseq}</td>
                  <td className="px-3 py-1.5 text-warning max-w-[120px] truncate" title={m.reason ?? ''}>
                    {m.reason}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

// ── Search + Ladder view ───────────────────────────────────────────────────────

function SearchView({ initialCallId }: { initialCallId: string }) {
  const [date, setDate]     = useState(today())
  const [q, setQ]           = useState(initialCallId)
  const [calls, setCalls]   = useState<CallSummary[] | null>(null)
  const [loadingList, setLoadingList] = useState(false)
  const [selected, setSelected]       = useState<string | null>(null)
  const [msgs, setMsgs]               = useState<TraceMsg[]>([])
  const [sbcIps, setSbcIps]           = useState<{ priv: string; pub: string }>({ priv: '', pub: '' })
  const [loadingTrace, setLoadingTrace] = useState(false)
  const [live, setLive]     = useState(false)
  const liveRef             = useRef(false)
  liveRef.current           = live
  const sinceIdRef          = useRef(0)
  const selectedRef         = useRef<string | null>(null)
  selectedRef.current       = selected
  const [error, setError]   = useState('')

  async function searchCalls(reset = true) {
    setLoadingList(true)
    if (reset) { setSelected(null); setMsgs([]); sinceIdRef.current = 0 }
    try {
      const p = new URLSearchParams({ date })
      if (q) p.set('q', q)
      const d = await apiGet(`/admin/traces/calls?${p}`)
      setCalls(d.calls); setError('')
    } catch (e: any) { setError(e.message || 'Error buscando llamadas') }
    finally { setLoadingList(false) }
  }

  async function openTrace(call_id: string, append = false) {
    if (!append) { setLoadingTrace(true); setMsgs([]); sinceIdRef.current = 0 }
    try {
      const p = new URLSearchParams({ call_id })
      if (append && sinceIdRef.current > 0) p.set('since_id', String(sinceIdRef.current))
      const d = await apiGet(`/admin/traces?${p}`)
      setSbcIps({ priv: d.sbc_private_ip ?? '', pub: d.sbc_public_ip ?? '' })
      if (d.messages.length > 0) {
        sinceIdRef.current = d.messages[d.messages.length - 1].id
        setMsgs(prev => append ? [...prev, ...d.messages] : d.messages)
      }
    } catch (e: any) { if (!append) setError(e.message || 'Error cargando la traza') }
    finally { if (!append) setLoadingTrace(false) }
  }

  async function downloadPcap(call_id: string) {
    try {
      const res = await apiFetch(`/admin/traces/pcap?${new URLSearchParams({ call_id })}`)
      if (!res.ok) { alert('No se pudo generar el PCAP'); return }
      const blob = await res.blob()
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href     = url
      a.download = `trace-${call_id.slice(0, 40)}.pcap`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      alert('Error al descargar PCAP')
    }
  }

  // Alternativa al PCAP para quien no tiene Wireshark/tshark a mano — mismos
  // mensajes que ya están cargados en el ladder, en texto plano legible.
  function downloadTraceTxt(call_id: string) {
    const lines = msgs.map(m => {
      const label = m.method ?? (m.status ? `SIP/2.0 ${m.status}` : '?')
      return [
        `[${new Date(m.ts).toLocaleString('es-PE')}] ${label}`,
        `${m.src_ip}:${m.src_port ?? '?'} → ${m.dst_ip}:${m.dst_port ?? '?'}`,
        m.raw,
        '',
      ].join('\n')
    })
    const blob = new Blob(
      [`Traza SIP — call_id ${call_id}\n${'='.repeat(60)}\n\n${lines.join('\n')}`],
      { type: 'text/plain;charset=utf-8' },
    )
    const url = URL.createObjectURL(blob)
    const a   = document.createElement('a')
    a.href     = url
    a.download = `trace-${call_id.slice(0, 40)}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  // Auto-search if initialCallId provided (p.ej. desde el link "SIP" de /cdrs) —
  // sin el setSelected acá, el ladder nunca se renderizaba: quedaba cargado en
  // `msgs` pero la vista seguía mostrando "Selecciona una llamada" porque esa
  // rama solo depende de `selected`, que antes solo se seteaba al hacer click
  // en la lista.
  useEffect(() => {
    if (initialCallId) { setSelected(initialCallId); searchCalls(); openTrace(initialCallId) }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!live) return
    searchCalls(false)
    const lt = setInterval(() => { if (liveRef.current) searchCalls(false) }, 3000)
    const tt = setInterval(() => {
      if (liveRef.current && selectedRef.current) openTrace(selectedRef.current, true)
    }, 2000)
    return () => { clearInterval(lt); clearInterval(tt) }
  }, [live]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="flex gap-4 flex-1 min-h-0">
      {/* Lista */}
      <div className="w-72 flex-shrink-0 flex flex-col gap-3">
        {error && <ErrorBanner>{error}</ErrorBanner>}
        <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-4 space-y-3">
          <div>
            <label className="block text-xs text-[var(--color-text-2)] mb-1">Fecha</label>
            <input type="date" value={date} onChange={e => setDate(e.target.value)}
              className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-3 py-1.5 text-sm text-[var(--color-text)] focus-ring" />
          </div>
          <div>
            <label className="block text-xs text-[var(--color-text-2)] mb-1">Número o Call-ID</label>
            <input value={q} onChange={e => setQ(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && searchCalls()}
              placeholder="51987654321 o abc123@…"
              className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-3 py-1.5 text-sm text-[var(--color-text)] placeholder-[var(--color-muted)] focus-ring" />
          </div>
          <div className="flex gap-2">
            <button onClick={() => searchCalls()} disabled={loadingList}
              className="flex-1 py-1.5 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-xs font-medium rounded focus-ring">
              {loadingList ? 'Buscando…' : 'Buscar'}
            </button>
            <button onClick={() => setLive(v => !v)}
              className={`flex items-center gap-1 px-2 py-1.5 rounded text-xs border transition-colors focus-ring
                ${live ? 'bg-danger/15 text-danger border-danger/40'
                       : 'bg-[var(--color-card-2)] text-[var(--color-text-2)] border-[var(--color-border)] hover:border-[var(--color-border-2)]'}`}>
              <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${live ? 'bg-danger animate-pulse' : 'bg-[var(--color-muted)]'}`} />
              Live
            </button>
          </div>
        </div>

        {calls !== null && (
          <div className="flex-1 overflow-y-auto bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl divide-y divide-[var(--color-border)] min-h-0">
            {calls.length === 0 && <p className="p-6 text-center text-[var(--color-muted)] text-sm">Sin trazas</p>}
            {calls.map(c => (
              <button key={c.call_id} onClick={() => { setSelected(c.call_id); openTrace(c.call_id) }}
                className={`w-full text-left px-3 py-2.5 hover:bg-white/2 transition-colors border-l-2 focus-ring
                  ${selected === c.call_id ? 'bg-brand-600/10 border-brand-500' : 'border-transparent'}`}>
                {(c.from_uri || c.to_uri) && (
                  <div className="flex items-center gap-1 mb-0.5 font-mono text-xs">
                    <span className="text-success truncate">{c.from_uri ?? '?'}</span>
                    <span className="text-[var(--color-muted)]">→</span>
                    <span className="text-[var(--color-text)] truncate">{c.to_uri ?? '?'}</span>
                  </div>
                )}
                <div className="flex items-center justify-between gap-1 mb-0.5">
                  <span className="text-[var(--color-muted)] text-xs truncate">{c.call_id}</span>
                  {c.final_status && (
                    <StatusBadge variant={sipCodeVariant(c.final_status)} bordered mono rounded="md" tight
                      className="flex-shrink-0 font-bold">
                      {c.final_status}
                    </StatusBadge>
                  )}
                </div>
                <div className="text-xs text-[var(--color-muted)]">
                  {new Date(c.first_ts).toLocaleTimeString('es-PE')} · {c.msg_count} msg
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Ladder */}
      <div className="flex-1 bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl overflow-hidden flex flex-col min-w-0">
        {!selected && !loadingTrace && (
          <div className="flex-1 flex items-center justify-center text-[var(--color-muted)] text-sm">
            Selecciona una llamada para ver el diálogo SIP
          </div>
        )}
        {loadingTrace && (
          <div className="flex-1 flex items-center justify-center text-[var(--color-text-2)] text-sm">Cargando…</div>
        )}
        {selected && !loadingTrace && (
          <>
            <div className="px-5 py-3 border-b border-[var(--color-border)] flex items-center justify-between flex-shrink-0">
              <div className="min-w-0">
                <p className="text-xs text-[var(--color-muted)]">Call-ID</p>
                <p className="font-mono text-xs text-brand-400 truncate">{selected}</p>
              </div>
              <div className="flex items-center gap-3 flex-shrink-0 ml-4">
                <button onClick={() => downloadTraceTxt(selected)}
                  title="Los mensajes SIP crudos en texto plano — no requiere Wireshark ni ningún visor de PCAP"
                  className="px-2.5 py-1 rounded text-xs bg-[var(--color-card-2)] text-[var(--color-text)] border border-[var(--color-border)] hover:border-brand-500 hover:text-brand-400 transition-colors focus-ring">
                  Descargar TXT
                </button>
                <button onClick={() => downloadPcap(selected)}
                  title="Descargar como .pcap para abrir en Wireshark"
                  className="px-2.5 py-1 rounded text-xs bg-[var(--color-card-2)] text-[var(--color-text)] border border-[var(--color-border)] hover:border-brand-500 hover:text-brand-400 transition-colors focus-ring">
                  Descargar PCAP
                </button>
                <div className="text-right">
                  <p className="text-xs text-[var(--color-text-2)]">{msgs.length} mensajes</p>
                  {live && <span className="text-xs text-danger animate-pulse">● live</span>}
                </div>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto">
              <SipLadder msgs={msgs} sbcPrivateIp={sbcIps.priv} sbcPublicIp={sbcIps.pub} />
            </div>
          </>
        )}
      </div>
    </div>
  )
}

// ── Root page ──────────────────────────────────────────────────────────────────

function TracesPageInner() {
  const params    = useSearchParams()
  const urlCallId = params.get('call_id') ?? ''

  const [tab, setTab]               = useState<'stream' | 'search'>(urlCallId ? 'search' : 'stream')
  const [jumpCallId, setJumpCallId] = useState(urlCallId)

  function goToCall(call_id: string) {
    setJumpCallId(call_id)
    setTab('search')
  }

  return (
    <div className="flex flex-col h-[calc(100vh-4.5rem)] gap-3">
      <div className="flex items-center justify-between flex-shrink-0">
        <h1 className="text-xl font-semibold text-[var(--color-text)]">Trazas SIP</h1>
        <div className="flex gap-1 bg-[var(--color-card-2)] p-1 rounded-lg">
          {([['stream', 'Stream en vivo'], ['search', 'Buscar llamada']] as const).map(([t, l]) => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-4 py-1.5 rounded text-sm transition-colors focus-ring
                ${tab === t ? 'bg-[var(--color-border-2)] text-[var(--color-text)] font-medium' : 'text-[var(--color-text-2)] hover:text-[var(--color-text)]'}`}>
              {l}
            </button>
          ))}
        </div>
      </div>

      {tab === 'stream' && (
        <div className="flex-1 bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl overflow-hidden flex flex-col min-h-0">
          <StreamView onCallId={goToCall} />
        </div>
      )}

      {tab === 'search' && (
        <SearchView key={jumpCallId} initialCallId={jumpCallId} />
      )}
    </div>
  )
}

export default function TracesPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center h-full text-[var(--color-muted)] text-sm">Cargando…</div>}>
      <TracesPageInner />
    </Suspense>
  )
}
