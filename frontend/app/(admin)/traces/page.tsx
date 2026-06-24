'use client'
import { Suspense, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { apiGet } from '@/lib/api'

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

interface TraceMsg {
  id: number; ts: string
  src_ip: string; src_port: number | null
  dst_ip: string; dst_port: number | null
  method: string | null; status: number | null
  from_uri: string | null; to_uri: string | null; raw: string
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function today() { return new Date().toISOString().slice(0, 10) }

function statusCls(method: string | null, status: number | null): string {
  if (status) {
    if (status < 200) return 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30'
    if (status < 300) return 'text-green-400  bg-green-500/10  border-green-500/30'
    if (status < 400) return 'text-blue-400   bg-blue-500/10   border-blue-400/30'
    if (status < 500) return 'text-orange-400 bg-orange-500/10 border-orange-400/30'
    return 'text-red-400 bg-red-500/10 border-red-400/30'
  }
  if (method === 'INVITE')  return 'text-brand-400 bg-brand-500/10 border-brand-400/30'
  if (method === 'BYE')     return 'text-purple-400 bg-purple-500/10 border-purple-400/30'
  if (method === 'CANCEL')  return 'text-orange-400 bg-orange-500/10 border-orange-400/30'
  if (method === 'ACK')     return 'text-zinc-300 bg-zinc-700/30 border-zinc-600/30'
  return 'text-zinc-400 bg-zinc-800/60 border-zinc-600/30'
}

function Badge({ method, status }: { method: string | null; status: number | null }) {
  const label = method ?? String(status ?? '?')
  return (
    <span className={`px-1.5 py-0.5 rounded border text-xs font-mono font-bold ${statusCls(method, status)}`}>
      {label}
    </span>
  )
}

function relTime(ref: string, ts: string) {
  const ms = new Date(ts).getTime() - new Date(ref).getTime()
  if (ms <= 0)   return '+0ms'
  if (ms < 1000) return `+${ms}ms`
  return `+${(ms / 1000).toFixed(2)}s`
}

function tsLocal(s: string) {
  return new Date(s).toLocaleTimeString('es-PE', { hour12: false, fractionalSecondDigits: 3 })
}

// ── SIP status text map ────────────────────────────────────────────────────────

const SIP_STATUS: Record<number, string> = {
  100: 'Trying',  180: 'Ringing',  181: 'Call Forwarded',
  182: 'Queued',  183: 'Session Progress',
  200: 'OK',      202: 'Accepted',
  301: 'Moved Permanently',  302: 'Moved Temporarily',
  400: 'Bad Request',        401: 'Unauthorized',
  403: 'Forbidden',          404: 'Not Found',
  405: 'Method Not Allowed', 408: 'Request Timeout',
  480: 'Unavailable',        481: 'No Call Leg',
  486: 'Busy Here',          487: 'Request Terminated',
  488: 'Not Acceptable',     500: 'Server Error',
  503: 'Service Unavailable', 603: 'Decline',
}

function msgLabel(msg: TraceMsg, hasSdp: boolean): string {
  if (msg.method) return msg.method + (hasSdp ? ' (SDP)' : '')
  if (msg.status) {
    const t = SIP_STATUS[msg.status]
    return t ? `${msg.status} ${t}` : String(msg.status)
  }
  return '?'
}

// ── SDP media IP extractor ─────────────────────────────────────────────────────

function parseSdpMedia(raw: string): string | null {
  const sep = raw.indexOf('\r\n\r\n')
  if (sep === -1) return null
  const body = raw.slice(sep + 4)
  if (!body.includes('v=0')) return null
  const c = body.match(/^c=IN IP4 (\d[\d.]+)/m)
  const m = body.match(/^m=audio (\d+)/m)
  if (!c || !m) return null
  const port = parseInt(m[1])
  return port > 0 ? `${c[1]}:${port}` : null
}

// ── Multi-column SIP Ladder ────────────────────────────────────────────────────

function SipLadder({ msgs }: { msgs: TraceMsg[] }) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  if (msgs.length === 0) {
    return <p className="p-8 text-center text-zinc-600 text-sm">Sin mensajes SIP para este Call-ID</p>
  }

  // 1. Recopilar nodos SIP únicos (en orden de aparición)
  const seenNodes = new Map<string, number>()
  msgs.forEach(m => {
    const a = `${m.src_ip}:${m.src_port ?? 5060}`
    const b = `${m.dst_ip}:${m.dst_port ?? 5060}`
    if (!seenNodes.has(a)) seenNodes.set(a, seenNodes.size)
    if (!seenNodes.has(b)) seenNodes.set(b, seenNodes.size)
  })

  // 2. Detectar el SBC: nodo que habla con MÁS nodos distintos (es el hub)
  const peerSets = new Map<string, Set<string>>()
  msgs.forEach(m => {
    const a = `${m.src_ip}:${m.src_port ?? 5060}`
    const b = `${m.dst_ip}:${m.dst_port ?? 5060}`
    if (!peerSets.has(a)) peerSets.set(a, new Set())
    if (!peerSets.has(b)) peerSets.set(b, new Set())
    peerSets.get(a)!.add(b)
    peerSets.get(b)!.add(a)
  })
  const sbcNode = [...peerSets.entries()].sort((a, b) => b[1].size - a[1].size)[0]?.[0] ?? ''

  // 3. Reordenar SIP: SBC en el centro
  let sipNodes = [...seenNodes.keys()]
  if (sipNodes.length >= 3 && sbcNode) {
    const endpoints = sipNodes.filter(n => n !== sbcNode)
    const mid = Math.floor(endpoints.length / 2)
    sipNodes = [...endpoints.slice(0, mid), sbcNode, ...endpoints.slice(mid)]
  }
  const sipCount = sipNodes.length

  // 4. Extraer IPs de media del SDP — solo IPs que NO son ya nodos SIP
  //    (descarta rtpengine/.41 que ya es SBC; agrega .185 del carrier media)
  const seenSipIPs = new Set([...seenNodes.keys()].map(k => k.split(':')[0]))
  const mediaByMsg = new Map<number, string>()
  const mediaSet   = new Set<string>()
  msgs.forEach(m => {
    const key = parseSdpMedia(m.raw)
    if (key && !seenSipIPs.has(key.split(':')[0])) {
      mediaByMsg.set(m.id, key)
      mediaSet.add(key)
    }
  })

  // 5. Columnas finales: nodos SIP + nodos media al final (con borde punteado)
  const nodes   = [...sipNodes, ...[...mediaSet]]
  const nodeMap = new Map(nodes.map((n, i) => [n, i]))
  const nCols   = nodes.length

  const nodeRole = (n: string, i: number): string => {
    if (i >= sipCount) return 'Media'
    if (n === sbcNode) return 'SBC'
    return i < nodeMap.get(sbcNode)! ? 'Origen' : 'Destino'
  }

  const t0 = msgs[0].ts

  return (
    <div className="overflow-x-auto">
      {/* Header de nodos */}
      <div className="flex sticky top-0 z-10 bg-zinc-900 border-b border-zinc-800 px-4 py-2">
        <div className="w-24 flex-shrink-0" />  {/* columna tiempo */}
        {nodes.map((n, i) => {
          const role = nodeRole(n, i)
          return (
            <div key={n} className="flex-1 text-center">
              <div className={`inline-block px-2 py-1 rounded text-xs font-mono border
                ${role === 'Media'  ? 'text-purple-400 bg-purple-500/10 border-purple-500/30 border-dashed'
                : role === 'SBC'    ? 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30'
                : role === 'Origen' ? 'text-green-400  bg-green-500/10  border-green-500/30'
                :                     'text-blue-400   bg-blue-500/10   border-blue-500/30'}`}>
                {n}
              </div>
              <p className="text-xs text-zinc-600 mt-0.5">{role}</p>
            </div>
          )
        })}
      </div>

      {/* Mensajes */}
      {msgs.map(msg => {
        const srcKey  = `${msg.src_ip}:${msg.src_port ?? 5060}`
        const dstKey  = `${msg.dst_ip}:${msg.dst_port ?? 5060}`
        const srcCol  = nodeMap.get(srcKey) ?? 0
        const dstCol  = nodeMap.get(dstKey) ?? sipCount - 1
        const goRight = srcCol < dstCol
        const isOpen  = expanded.has(msg.id)

        // Media: columna destino punteado morado (solo si SDP tiene IP nueva)
        const mediaKey = mediaByMsg.get(msg.id)
        const mediaCol = mediaKey !== undefined ? (nodeMap.get(mediaKey) ?? -1) : -1
        const hasMedia = mediaCol >= 0

        // Label encima de la flecha (sngrep-style)
        const hasSdp   = msg.raw.includes('\r\n\r\nv=0')
        const label    = msgLabel(msg, hasSdp)
        const labelCol = Math.round((srcCol + dstCol) / 2)

        const lineColor = msg.method === 'BYE' || msg.method === 'CANCEL'
          ? 'bg-red-500/70'
          : msg.method === 'INVITE' ? 'bg-brand-500/70'
          : msg.method === 'ACK'    ? 'bg-zinc-400/50'
          : msg.status && msg.status >= 400 ? 'bg-orange-500/60'
          : 'bg-zinc-500/60'

        const arrowColor = msg.method === 'BYE' || msg.method === 'CANCEL'
          ? 'text-red-400'
          : msg.method === 'INVITE' ? 'text-brand-400'
          : msg.method === 'ACK'    ? 'text-zinc-400'
          : 'text-zinc-300'

        return (
          <div key={msg.id} className="border-b border-zinc-800/60">
            <button
              onClick={() => setExpanded(prev => {
                const n = new Set(prev); n.has(msg.id) ? n.delete(msg.id) : n.add(msg.id); return n
              })}
              className="w-full flex items-center hover:bg-zinc-800/30 transition-colors px-4 py-2.5">

              {/* Tiempo */}
              <div className="w-24 flex-shrink-0 text-left">
                <span className="text-xs font-mono text-zinc-500">{relTime(t0, msg.ts)}</span>
              </div>

              {/* Columnas */}
              <div className="flex flex-1 items-center">
                {nodes.map((_, colIdx) => {
                  const isMedia   = colIdx >= sipCount
                  const isFrom    = colIdx === srcCol
                  const isTo      = colIdx === dstCol
                  const isBetween = goRight
                    ? colIdx > srcCol && colIdx < dstCol
                    : colIdx > dstCol && colIdx < srcCol

                  // Extensión media punteada: desde dstCol hacia mediaCol (siempre a la derecha)
                  const isMediaDst     = hasMedia && colIdx === mediaCol
                  const isMediaBetween = hasMedia && colIdx > dstCol && colIdx < mediaCol

                  const labelColor = msg.method === 'INVITE'                           ? 'text-brand-400'
                    : msg.method === 'BYE' || msg.method === 'CANCEL'                  ? 'text-red-400'
                    : msg.status && msg.status >= 200 && msg.status < 300              ? 'text-green-400'
                    : msg.status && msg.status >= 400                                  ? 'text-orange-400'
                    : 'text-zinc-400'

                  return (
                    <div key={colIdx} className="flex-1 flex items-center justify-center relative min-h-[3rem]">
                      {/* Línea vertical del nodo */}
                      <div className={`absolute inset-y-0 left-1/2 w-px -translate-x-1/2
                        ${isMedia ? 'bg-purple-500/25' : 'bg-zinc-700/40'}`} />

                      {/* Etiqueta sobre la flecha — solo en la columna central del tramo */}
                      {colIdx === labelCol && (
                        <span className={`absolute top-1.5 left-0 right-0 text-center
                          text-[10px] font-mono leading-none truncate px-0.5
                          pointer-events-none ${labelColor}`}>
                          {label}
                        </span>
                      )}

                      {/* Origen: punto */}
                      {isFrom && (
                        <div className="relative z-10 w-2 h-2 rounded-full bg-zinc-500 flex-shrink-0" />
                      )}

                      {/* Destino SIP: flecha + badge eliminado (el label reemplaza el badge) */}
                      {isTo && (
                        <div className={`relative z-10 flex items-center
                          ${goRight ? 'justify-start pl-0.5' : 'justify-end pr-0.5'}`}>
                          <span className={`text-base leading-none ${arrowColor}`}>
                            {goRight ? '▶' : '◀'}
                          </span>
                        </div>
                      )}

                      {/* Destino media: círculo morado */}
                      {isMediaDst && (
                        <div className="relative z-10 flex items-center justify-start pl-1">
                          <span className="text-lg leading-none text-purple-400">◉</span>
                        </div>
                      )}

                      {/* Líneas SIP sólidas */}
                      {isFrom    && goRight  && <div className={`absolute top-1/2 left-1/2 right-0   h-px ${lineColor}`} />}
                      {isBetween && goRight  && <div className={`absolute top-1/2 left-0   right-0   h-px ${lineColor}`} />}
                      {isTo      && goRight  && <div className={`absolute top-1/2 left-0   right-1/2 h-px ${lineColor}`} />}
                      {isFrom    && !goRight && <div className={`absolute top-1/2 left-0   right-1/2 h-px ${lineColor}`} />}
                      {isBetween && !goRight && <div className={`absolute top-1/2 left-0   right-0   h-px ${lineColor}`} />}
                      {isTo      && !goRight && <div className={`absolute top-1/2 left-1/2 right-0   h-px ${lineColor}`} />}

                      {/* Extensión media punteada (siempre hacia la derecha desde dstCol) */}
                      {isTo          && hasMedia && <div className="absolute top-[calc(50%+2px)] left-1/2 right-0   h-px border-t border-dashed border-purple-500/60" />}
                      {isMediaBetween            && <div className="absolute top-[calc(50%+2px)] left-0   right-0   h-px border-t border-dashed border-purple-500/60" />}
                      {isMediaDst                && <div className="absolute top-[calc(50%+2px)] left-0   right-1/2 h-px border-t border-dashed border-purple-500/60" />}
                    </div>
                  )
                })}
              </div>

              <span className="text-zinc-600 text-xs w-4 flex-shrink-0">{isOpen ? '▾' : '▸'}</span>
            </button>

            {/* Raw SIP */}
            {isOpen && (
              <pre className="mx-4 mb-3 px-4 py-3 bg-zinc-950 border border-zinc-700/60 rounded
                              text-xs font-mono text-zinc-300 overflow-x-auto whitespace-pre-wrap
                              break-all max-h-96 overflow-y-auto">
                {msg.raw}
              </pre>
            )}
          </div>
        )
      })}
    </div>
  )
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
    const p = new URLSearchParams({ since_id: String(sinceRef.current), limit: '200' })
    const d = await apiGet(`/admin/traces/stream?${p}`)
    if (d.messages.length > 0) {
      sinceRef.current = d.messages[d.messages.length - 1].id
      setMsgs(prev => {
        const next = reset ? d.messages : [...prev, ...d.messages]
        return next.slice(-MAX_ROWS)
      })
    }
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
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800 flex-shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setLive(v => !v)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium border transition-colors
              ${live ? 'bg-red-500/15 text-red-400 border-red-500/40'
                     : 'bg-zinc-800 text-zinc-300 border-zinc-700 hover:border-zinc-500'}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${live ? 'bg-red-400 animate-pulse' : 'bg-zinc-500'}`} />
            {live ? 'Detener' : 'Iniciar stream'}
          </button>
          {!live && (
            <button onClick={() => fetch(true)}
              className="px-3 py-1.5 rounded text-xs bg-zinc-800 text-zinc-300 border border-zinc-700 hover:border-zinc-500">
              Actualizar
            </button>
          )}
          <button onClick={() => setMsgs([])}
            className="px-3 py-1.5 rounded text-xs bg-zinc-800 text-zinc-300 border border-zinc-700 hover:border-zinc-500">
            Limpiar
          </button>
        </div>
        <span className="text-xs text-zinc-500">{msgs.length} mensajes{msgs.length >= MAX_ROWS ? ' (máx)' : ''}</span>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-y-auto">
        {msgs.length === 0 ? (
          <div className="flex items-center justify-center h-full text-zinc-600 text-sm">
            {live ? 'Esperando tráfico SIP…' : 'Presiona "Iniciar stream" para ver tráfico en vivo'}
          </div>
        ) : (
          <table className="w-full text-xs">
            <thead className="sticky top-0 z-10 bg-zinc-900 border-b border-zinc-800">
              <tr className="text-zinc-500 uppercase">
                {['Hora','Origen','Destino','Método','Código','Call-ID','CSeq','Reason'].map(h => (
                  <th key={h} className="px-3 py-2 text-left font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/50">
              {[...msgs].reverse().map(m => (
                <tr key={m.id} className="hover:bg-zinc-800/30 transition-colors">
                  <td className="px-3 py-1.5 font-mono text-zinc-500 whitespace-nowrap">{tsLocal(m.ts)}</td>
                  <td className="px-3 py-1.5 font-mono text-green-400 whitespace-nowrap">{m.from_uri ?? `${m.src_ip}:${m.src_port}`}</td>
                  <td className="px-3 py-1.5 font-mono text-white whitespace-nowrap">{m.to_uri ?? `${m.dst_ip}:${m.dst_port}`}</td>
                  <td className="px-3 py-1.5">
                    {m.method && <Badge method={m.method} status={null} />}
                  </td>
                  <td className="px-3 py-1.5">
                    {m.status && <Badge method={null} status={m.status} />}
                  </td>
                  <td className="px-3 py-1.5 font-mono text-zinc-400 max-w-[180px] truncate">
                    <button onClick={() => onCallId(m.call_id)}
                      className="hover:text-brand-400 transition-colors text-left"
                      title={m.call_id}>
                      {m.call_id}
                    </button>
                  </td>
                  <td className="px-3 py-1.5 font-mono text-zinc-500 whitespace-nowrap">{m.cseq}</td>
                  <td className="px-3 py-1.5 text-orange-300 max-w-[120px] truncate" title={m.reason ?? ''}>
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
  const [loadingTrace, setLoadingTrace] = useState(false)
  const [live, setLive]     = useState(false)
  const liveRef             = useRef(false)
  liveRef.current           = live
  const sinceIdRef          = useRef(0)
  const selectedRef         = useRef<string | null>(null)
  selectedRef.current       = selected

  async function searchCalls(reset = true) {
    setLoadingList(true)
    if (reset) { setSelected(null); setMsgs([]); sinceIdRef.current = 0 }
    try {
      const p = new URLSearchParams({ date })
      if (q) p.set('q', q)
      const d = await apiGet(`/admin/traces/calls?${p}`)
      setCalls(d.calls)
    } finally { setLoadingList(false) }
  }

  async function openTrace(call_id: string, append = false) {
    if (!append) { setLoadingTrace(true); setMsgs([]); sinceIdRef.current = 0 }
    try {
      const p = new URLSearchParams({ call_id })
      if (append && sinceIdRef.current > 0) p.set('since_id', String(sinceIdRef.current))
      const d = await apiGet(`/admin/traces?${p}`)
      if (d.messages.length > 0) {
        sinceIdRef.current = d.messages[d.messages.length - 1].id
        setMsgs(prev => append ? [...prev, ...d.messages] : d.messages)
      }
    } finally { if (!append) setLoadingTrace(false) }
  }

  // Auto-search if initialCallId provided
  useEffect(() => {
    if (initialCallId) { searchCalls(); openTrace(initialCallId) }
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
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-3">
          <div>
            <label className="block text-xs text-zinc-400 mb-1">Fecha</label>
            <input type="date" value={date} onChange={e => setDate(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-sm text-white" />
          </div>
          <div>
            <label className="block text-xs text-zinc-400 mb-1">Número o Call-ID</label>
            <input value={q} onChange={e => setQ(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && searchCalls()}
              placeholder="51987654321 o abc123@…"
              className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-sm text-white placeholder-zinc-600" />
          </div>
          <div className="flex gap-2">
            <button onClick={() => searchCalls()} disabled={loadingList}
              className="flex-1 py-1.5 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-xs font-medium rounded">
              {loadingList ? 'Buscando…' : 'Buscar'}
            </button>
            <button onClick={() => setLive(v => !v)}
              className={`flex items-center gap-1 px-2 py-1.5 rounded text-xs border transition-colors
                ${live ? 'bg-red-500/15 text-red-400 border-red-500/40'
                       : 'bg-zinc-800 text-zinc-400 border-zinc-700 hover:border-zinc-500'}`}>
              <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${live ? 'bg-red-400 animate-pulse' : 'bg-zinc-500'}`} />
              Live
            </button>
          </div>
        </div>

        {calls !== null && (
          <div className="flex-1 overflow-y-auto bg-zinc-900 border border-zinc-800 rounded-xl divide-y divide-zinc-800 min-h-0">
            {calls.length === 0 && <p className="p-6 text-center text-zinc-500 text-sm">Sin trazas</p>}
            {calls.map(c => (
              <button key={c.call_id} onClick={() => { setSelected(c.call_id); openTrace(c.call_id) }}
                className={`w-full text-left px-3 py-2.5 hover:bg-zinc-800 transition-colors border-l-2
                  ${selected === c.call_id ? 'bg-brand-600/10 border-brand-500' : 'border-transparent'}`}>
                {(c.from_uri || c.to_uri) && (
                  <div className="flex items-center gap-1 mb-0.5 font-mono text-xs">
                    <span className="text-green-400 truncate">{c.from_uri ?? '?'}</span>
                    <span className="text-zinc-600">→</span>
                    <span className="text-white truncate">{c.to_uri ?? '?'}</span>
                  </div>
                )}
                <div className="flex items-center justify-between gap-1 mb-0.5">
                  <span className="text-zinc-500 text-xs truncate">{c.call_id}</span>
                  {c.final_status && (
                    <span className={`flex-shrink-0 px-1 rounded text-xs font-mono font-bold border
                      ${statusCls(null, c.final_status)}`}>{c.final_status}</span>
                  )}
                </div>
                <div className="text-xs text-zinc-600">
                  {new Date(c.first_ts).toLocaleTimeString('es-PE')} · {c.msg_count} msg
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Ladder */}
      <div className="flex-1 bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden flex flex-col min-w-0">
        {!selected && !loadingTrace && (
          <div className="flex-1 flex items-center justify-center text-zinc-600 text-sm">
            Selecciona una llamada para ver el diálogo SIP
          </div>
        )}
        {loadingTrace && (
          <div className="flex-1 flex items-center justify-center text-zinc-400 text-sm">Cargando…</div>
        )}
        {selected && !loadingTrace && (
          <>
            <div className="px-5 py-3 border-b border-zinc-800 flex items-center justify-between flex-shrink-0">
              <div className="min-w-0">
                <p className="text-xs text-zinc-500">Call-ID</p>
                <p className="font-mono text-xs text-brand-400 truncate">{selected}</p>
              </div>
              <div className="text-right flex-shrink-0 ml-4">
                <p className="text-xs text-zinc-400">{msgs.length} mensajes</p>
                {live && <span className="text-xs text-red-400 animate-pulse">● live</span>}
              </div>
            </div>
            <div className="flex-1 overflow-y-auto">
              <SipLadder msgs={msgs} />
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
        <h1 className="text-xl font-semibold text-white">Trazas SIP</h1>
        <div className="flex gap-1 bg-zinc-800 p-1 rounded-lg">
          {([['stream', 'Stream en vivo'], ['search', 'Buscar llamada']] as const).map(([t, l]) => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-4 py-1.5 rounded text-sm transition-colors
                ${tab === t ? 'bg-zinc-700 text-white font-medium' : 'text-zinc-400 hover:text-zinc-200'}`}>
              {l}
            </button>
          ))}
        </div>
      </div>

      {tab === 'stream' && (
        <div className="flex-1 bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden flex flex-col min-h-0">
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
    <Suspense fallback={<div className="flex items-center justify-center h-full text-zinc-500 text-sm">Cargando…</div>}>
      <TracesPageInner />
    </Suspense>
  )
}
