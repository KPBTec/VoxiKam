'use client'
import { useEffect, useRef, useState } from 'react'
import { apiGet } from '@/lib/api'
import { RefreshCw } from 'lucide-react'
import { ErrorBanner } from '@/components/ErrorBanner'
import { LiveIndicator } from '@/components/LiveIndicator'

interface Source { id: string; label: string }

export default function SystemLogsPage() {
  const [sources, setSources] = useState<Source[]>([])
  const [source, setSource]   = useState('')
  const [lines, setLines]     = useState(100)
  const [content, setContent] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [live, setLive]       = useState(false)
  const [error, setError]     = useState('')
  const liveRef = useRef(false)
  liveRef.current = live
  const boxRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    apiGet('/admin/system/logs/sources')
      .then((s: Source[]) => { setSources(s); if (s.length) setSource(s[0].id) })
      .catch((e: any) => setError(e.message || 'Error cargando fuentes'))
  }, [])

  async function load() {
    if (!source) return
    setLoading(true); setError('')
    try {
      const r = await apiGet(`/admin/system/logs?source=${encodeURIComponent(source)}&lines=${lines}`)
      setContent(r.lines ?? [])
    } catch (e: any) { setError(e.message || 'Error cargando logs') }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [source]) // eslint-disable-line react-hooks/exhaustive-deps

  // Mismo patrón de "streaming" que ya usa traces/page.tsx — polling con
  // toggle, no WebSocket/SSE nuevo, consistente con el resto de la app.
  useEffect(() => {
    const t = setInterval(() => { if (liveRef.current) load() }, 2000)
    return () => clearInterval(t)
  }, [source, lines]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight
  }, [content])

  const card = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'
  const sel  = 'bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-500 cursor-pointer'

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Logs</h1>
        <p className="text-sm text-[var(--color-text-2)] mt-1">
          Últimas líneas de cada servicio o cron, sin entrar por SSH — solo lectura. Para reiniciar
          un servicio o seguir un log en vivo por consola seguí usando <code className="text-xs">voxikam -r|-l</code>.
        </p>
      </div>

      {error && <ErrorBanner>{error}</ErrorBanner>}

      <div className={`${card} p-4 flex items-center gap-3 flex-wrap`}>
        <select value={source} onChange={e => setSource(e.target.value)} className={sel}>
          {sources.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
        </select>
        <select value={lines} onChange={e => setLines(Number(e.target.value))} className={sel}>
          {[50, 100, 200, 500, 1000].map(n => <option key={n} value={n}>{n} líneas</option>)}
        </select>
        <button onClick={load} disabled={loading}
          className="focus-ring flex items-center gap-1.5 px-3 py-2 bg-[var(--color-surface)] border border-[var(--color-border)] hover:border-brand-500 text-sm rounded-lg transition-colors disabled:opacity-50">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Actualizar
        </button>
        <button onClick={() => setLive(l => !l)}
          className={`focus-ring flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg transition-colors ${
            live ? 'bg-brand-600 text-white' : 'bg-[var(--color-surface)] border border-[var(--color-border)] text-[var(--color-text-2)]'
          }`}>
          <LiveIndicator active={live} onColoredBg={live} label={live ? 'Auto-actualizando (2s)' : 'Auto-actualizar'} />
        </button>
      </div>

      <div className={`${card} overflow-hidden`}>
        <div ref={boxRef} className="p-4 font-mono text-xs leading-relaxed overflow-auto max-h-[70vh] whitespace-pre-wrap break-all">
          {content.length === 0 ? (
            <p className="text-[var(--color-muted)]">{loading ? 'Cargando...' : 'Sin líneas para mostrar'}</p>
          ) : content.map((l, i) => (
            <div key={i} className="text-[var(--color-text-2)] hover:text-[var(--color-text)] hover:bg-white/3">{l}</div>
          ))}
        </div>
      </div>
    </div>
  )
}
