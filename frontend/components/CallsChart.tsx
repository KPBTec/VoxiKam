'use client'
import { useState, useRef } from 'react'

export interface ChartSeries { name: string; color: string; data: number[] }

interface Props {
  labels: string[]
  series: ChartSeries[]
  height?: number
  title?: string
}

export function CallsChart({ labels, series, height = 220, title }: Props) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)

  const W = 900, H = height
  const PAD = { top: 12, right: 16, bottom: 28, left: 40 }
  const cW = W - PAD.left - PAD.right
  const cH = H - PAD.top - PAD.bottom

  const allVals = series.flatMap(s => s.data)
  const maxY    = Math.max(...allVals, 1)
  const n       = labels.length

  const xp = (i: number) => PAD.left + (i / Math.max(n - 1, 1)) * cW
  const yp = (v: number) => PAD.top + cH - (v / maxY) * cH

  // < GAP_THRESHOLD ceros seguidos → saltar (fluctuación puntual, conectar directo)
  // ≥ GAP_THRESHOLD ceros seguidos → bajar a 0 (corte real de tráfico)
  const GAP_THRESHOLD = 5

  const buildLinePath = (data: number[]): string => {
    if (!data.some(v => v > 0)) return ''
    const cmds: string[] = []
    let penDown = false
    let i = 0
    while (i < data.length) {
      if (data[i] > 0) {
        cmds.push(`${penDown ? 'L' : 'M'} ${xp(i)},${yp(data[i])}`)
        penDown = true
        i++
      } else {
        // Contar la racha de ceros
        let j = i
        while (j < data.length && data[j] === 0) j++
        const runLen = j - i
        if (runLen >= GAP_THRESHOLD && penDown) {
          // Racha larga: bajar a 0 explícitamente, levantar pluma
          cmds.push(`L ${xp(i)},${yp(0)} L ${xp(j - 1)},${yp(0)}`)
          penDown = false
        }
        // Racha corta: ignorar, la próxima L conecta directo
        i = j
      }
    }
    return cmds.join(' ')
  }

  const buildAreaPath = (data: number[]): string => {
    if (!data.some(v => v > 0)) return ''
    const bot = PAD.top + cH
    const pts = data.map((v, i) => `${xp(i)},${yp(v)}`).join(' ')
    return `M ${xp(0)},${bot} L ${pts} L ${xp(n - 1)},${bot} Z`
  }

  const stride = Math.max(1, Math.ceil(n / 8))
  const yTicks = [0, 0.25, 0.5, 0.75, 1]

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const ratio = (e.clientX - rect.left) / rect.width
    const idx   = Math.max(0, Math.min(n - 1, Math.round(ratio * (n - 1))))
    setHoverIdx(idx)
  }

  if (!n || !series.length) return (
    <div style={{ height }} className="flex items-center justify-center text-[var(--color-muted)] text-sm">
      Sin datos en el rango seleccionado
    </div>
  )

  return (
    <div className="relative select-none">
      {title && <p className="text-xs text-[var(--color-text-2)] mb-2">{title}</p>}
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="w-full"
        style={{ height }}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setHoverIdx(null)}>

        {/* Grid horizontal */}
        {yTicks.map(f => {
          const y   = PAD.top + cH * (1 - f)
          const val = Math.round(maxY * f)
          return (
            <g key={f}>
              <line x1={PAD.left} y1={y} x2={W - PAD.right} y2={y}
                stroke="rgba(255,255,255,0.05)" strokeWidth="1" />
              <text x={PAD.left - 6} y={y + 4} textAnchor="end"
                fill="rgba(255,255,255,0.3)" fontSize="10" fontFamily="monospace">{val}</text>
            </g>
          )
        })}

        {/* Etiquetas X */}
        {labels.map((l, i) => i % stride === 0 && (
          <text key={i} x={xp(i)} y={H - 4} textAnchor="middle"
            fill="rgba(255,255,255,0.3)" fontSize="10" fontFamily="monospace">{l}</text>
        ))}

        {/* Áreas rellenas — solo bajo puntos con valor > 0 */}
        {series.map((s, si) => {
          const d = buildAreaPath(s.data)
          return d ? <path key={`area-${si}`} d={d} fill={s.color} fillOpacity="0.08" /> : null
        })}

        {/* Líneas — conecta solo puntos con valor > 0, salta los ceros */}
        {series.map((s, si) => {
          const d = buildLinePath(s.data)
          return d ? (
            <path key={`line-${si}`} d={d}
              fill="none" stroke={s.color} strokeWidth="2"
              strokeLinejoin="round" strokeLinecap="round" />
          ) : null
        })}

        {/* Línea vertical de hover */}
        {hoverIdx !== null && (
          <line x1={xp(hoverIdx)} y1={PAD.top} x2={xp(hoverIdx)} y2={PAD.top + cH}
            stroke="rgba(255,255,255,0.15)" strokeWidth="1" strokeDasharray="4,3" />
        )}

        {/* Puntos en hover — solo si el valor es > 0 */}
        {hoverIdx !== null && series.map((s, si) => s.data[hoverIdx] > 0 ? (
          <circle key={`dot-${si}`}
            cx={xp(hoverIdx)} cy={yp(s.data[hoverIdx])} r="4"
            fill={s.color} stroke="rgba(0,0,0,0.6)" strokeWidth="1.5" />
        ) : null)}
      </svg>

      {/* Tooltip flotante */}
      {hoverIdx !== null && (
        <div className="absolute pointer-events-none z-20"
          style={{ left: `${Math.min((hoverIdx / Math.max(n - 1, 1)) * 100, 78)}%`, top: 0 }}>
          <div className="bg-zinc-900 border border-zinc-700 rounded-lg shadow-2xl p-2.5 text-xs min-w-[120px]">
            <p className="text-zinc-400 font-mono mb-1.5">{labels[hoverIdx]}</p>
            {series.map((s, si) => (
              <div key={si} className="flex items-center gap-1.5 py-0.5">
                <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: s.color }} />
                <span className="text-zinc-300 truncate max-w-[100px]">{s.name}</span>
                <span className="ml-auto font-bold text-white">{s.data[hoverIdx]}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Leyenda — siempre visible para identificar carrier/cliente */}
      {series.length > 0 && (
        <div className="flex flex-wrap gap-4 mt-2 px-1">
          {series.map((s, si) => (
            <div key={si} className="flex items-center gap-1.5 text-xs text-zinc-400">
              <span className="w-6 h-0.5 rounded-full" style={{ background: s.color }} />
              <span className="truncate max-w-[160px]">{s.name}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
