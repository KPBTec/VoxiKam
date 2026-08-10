'use client'
import { useState } from 'react'

export interface TraceMsg {
  id: number; ts: string
  src_ip: string; src_port: number | null
  dst_ip: string; dst_port: number | null
  method: string | null; status: number | null
  from_uri: string | null; to_uri: string | null; raw: string
}

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

function relTime(ref: string, ts: string) {
  const ms = new Date(ts).getTime() - new Date(ref).getTime()
  if (ms <= 0)   return '+0ms'
  if (ms < 1000) return `+${ms}ms`
  return `+${(ms / 1000).toFixed(2)}s`
}

// ── Multi-column SIP Ladder ────────────────────────────────────────────────────
// Extraído de app/(admin)/traces/page.tsx (v2.24.17) para reusar tal cual en el
// modal de detalle de CDRs — mismo componente, sin duplicar lógica.

interface SipLadderProps {
  msgs: TraceMsg[]
  sbcPrivateIp?: string  // LAN — lado Asterisk/cliente (backend/routers/traces.py::get_trace())
  sbcPublicIp?: string   // WAN — lado carrier
}

export function SipLadder({ msgs, sbcPrivateIp, sbcPublicIp }: SipLadderProps) {
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

  // 2. Peers de cada nodo — se usa para clasificar "lado LAN" vs "lado WAN"
  //    de los nodos que NO son el propio SBC (paso 3).
  const peerSets = new Map<string, Set<string>>()
  msgs.forEach(m => {
    const a = `${m.src_ip}:${m.src_port ?? 5060}`
    const b = `${m.dst_ip}:${m.dst_port ?? 5060}`
    if (!peerSets.has(a)) peerSets.set(a, new Set())
    if (!peerSets.has(b)) peerSets.set(b, new Set())
    peerSets.get(a)!.add(b)
    peerSets.get(b)!.add(a)
  })

  // 3. Orden de columnas — Origen a la izquierda, Destino a la derecha,
  //    como en un PCAP/Wireshark. Antes se ordenaba con "el nodo que habla
  //    con más nodos distintos es el SBC, va al centro" — esa heurística
  //    servía cuando solo se capturaba UN tramo por mensaje (el SBC era el
  //    único con varios peers). Con trace_mode capturando los dos tramos
  //    completos (v2.34.0), TODOS los nodos de una llamada simple tienen
  //    exactamente 1 peer — la heurística queda ciega y puede elegir
  //    cualquiera como "el hub", incluido el origen real (bug reportado:
  //    "10.100.10.3" — el cliente — apareciendo etiquetado "SBC").
  //    Ahora se usan las IPs reales del SBC (ya confirmadas, no adivinadas
  //    — ver sbcPrivateIp/sbcPublicIp) para armar el orden directamente:
  //    [lado LAN] → SBC(LAN) → SBC(WAN) → [lado WAN], sin heurística.
  const allSipNodes = [...seenNodes.keys()]
  const sbcLanNode = sbcPrivateIp ? allSipNodes.find(n => n.split(':')[0] === sbcPrivateIp) : undefined
  const sbcWanNode = sbcPublicIp  ? allSipNodes.find(n => n.split(':')[0] === sbcPublicIp)  : undefined

  // sbcNode: solo se usa en el fallback (abajo) cuando no se pudieron
  // confirmar las dos IPs reales del SBC — se mantiene fuera del if/else
  // para que nodeRole() (más abajo) lo pueda seguir usando en ese caso.
  let sbcNode = ''
  let sipNodes: string[]
  if (sbcLanNode && sbcWanNode) {
    const lanSide: string[] = []
    const wanSide: string[] = []
    const unclassified: string[] = []
    allSipNodes.forEach(n => {
      if (n === sbcLanNode || n === sbcWanNode) return
      const peers = peerSets.get(n) ?? new Set<string>()
      if (peers.has(sbcLanNode)) lanSide.push(n)
      else if (peers.has(sbcWanNode)) wanSide.push(n)
      else unclassified.push(n)
    })
    sipNodes = [...lanSide, sbcLanNode, sbcWanNode, ...wanSide, ...unclassified]
  } else {
    // Fallback: no se pudo confirmar alguna de las dos IPs del SBC (ej. .env
    // sin PRIVATE_IP/PUBLIC_IP) — misma heurística de antes, mejor que nada.
    sbcNode = [...peerSets.entries()].sort((a, b) => b[1].size - a[1].size)[0]?.[0] ?? ''
    sipNodes = allSipNodes
    if (sipNodes.length >= 3 && sbcNode) {
      const endpoints = sipNodes.filter(n => n !== sbcNode)
      const mid = Math.floor(endpoints.length / 2)
      sipNodes = [...endpoints.slice(0, mid), sbcNode, ...endpoints.slice(mid)]
    }
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

  // Con dual-NIC el SBC aparece DOS VECES en la traza — una IP hablando con
  // el cliente (LAN), otra con el carrier (WAN). Match directo contra las
  // IPs reales del SBC (vía .env, ver traces.py::get_trace()) para las dos
  // columnas del propio SBC; el resto de nodos se clasifica por posición
  // relativa a sbcLanNode (todo lo que está antes = Origen, todo lo que
  // está después = Destino) — ya no por comparar contra un único "hub"
  // heurístico, que con los dos tramos capturados (v2.34.0) deja de ser
  // confiable (ver comentario en el paso 3, más arriba).
  const sbcLanIdx = sbcLanNode ? nodeMap.get(sbcLanNode) : undefined
  const nodeRole = (n: string, i: number): string => {
    if (i >= sipCount) return 'Media'
    const ip = n.split(':')[0]
    if (sbcPrivateIp && ip === sbcPrivateIp) return 'SBC (LAN)'
    if (sbcPublicIp && ip === sbcPublicIp) return 'SBC (WAN)'
    if (n === sbcNode) return 'SBC'
    if (sbcLanIdx !== undefined) return i < sbcLanIdx ? 'Origen' : 'Destino'
    return i < Math.floor(sipCount / 2) ? 'Origen' : 'Destino'
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
                ${role === 'Media'        ? 'text-purple-400 bg-purple-500/10 border-purple-500/30 border-dashed'
                : role.startsWith('SBC')  ? 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30'
                : role === 'Origen'       ? 'text-green-400  bg-green-500/10  border-green-500/30'
                :                           'text-info-400   bg-info-100/40   border-info-400/30'}`}>
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
