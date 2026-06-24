'use client'
import { useEffect, useState } from 'react'
import { apiFetch } from '@/lib/api'

interface CDR {
  call_id: string
  src_number: string
  dst_number: string
  billsec: number
  sessionbill: number
  disposition: string
  start_ts: string
}

const STATUS: Record<string, string> = {
  ANSWERED:  'bg-green-500/15 text-green-400',
  BUSY:      'bg-yellow-500/15 text-yellow-400',
  NO_ANSWER: 'bg-zinc-500/15 text-zinc-400',
  FAILED:    'bg-red-500/15 text-red-400',
}

function fmtSec(s: number) {
  const m = Math.floor(s / 60), sec = s % 60
  return `${m}m ${sec.toString().padStart(2, '0')}s`
}
function fmtMoney(n: number) {
  return `S/ ${Number(n).toFixed(4)}`
}

export default function MyCalls() {
  const [rows, setRows]       = useState<CDR[]>([])
  const [total, setTotal]     = useState(0)
  const [capped, setCapped]   = useState(false)
  const [loading, setLoading] = useState(false)
  const [offset, setOffset]   = useState(0)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo,   setDateTo]   = useState('')
  const LIMIT = 50

  async function load(off = 0) {
    setLoading(true)
    try {
      const params = new URLSearchParams({
        limit:  String(LIMIT),
        offset: String(off),
        ...(dateFrom && { date_from: dateFrom }),
        ...(dateTo   && { date_to:   dateTo }),
      })
      const r = await apiFetch(`/my/calls?${params}`)
      const d = await r.json()
      setRows(d.rows)
      setTotal(d.total)
      setCapped(d.capped)
      setOffset(off)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(0) }, [])

  function handleFilter(e: React.FormEvent) {
    e.preventDefault()
    load(0)
  }

  const totalPages = Math.ceil(total / LIMIT) || 1
  const currentPage = Math.floor(offset / LIMIT) + 1

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-white">Historial de llamadas</h1>
        <p className="text-sm text-zinc-400 mt-0.5">
          Últimos {total} registros mostrados
          {capped && (
            <span className="ml-2 text-amber-400">
              · Hay más de 200 — usa filtros de fecha para acotar
            </span>
          )}
        </p>
      </div>

      {/* Filtros */}
      <form onSubmit={handleFilter} className="flex flex-wrap gap-3 items-end bg-zinc-900 border border-zinc-800 rounded-lg p-4">
        <div>
          <label className="block text-xs text-zinc-400 mb-1">Desde</label>
          <input
            type="date"
            value={dateFrom}
            onChange={e => setDateFrom(e.target.value)}
            className="bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-sm text-white"
          />
        </div>
        <div>
          <label className="block text-xs text-zinc-400 mb-1">Hasta</label>
          <input
            type="date"
            value={dateTo}
            onChange={e => setDateTo(e.target.value)}
            className="bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-sm text-white"
          />
        </div>
        <button
          type="submit"
          className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded"
        >
          Filtrar
        </button>
        <button
          type="button"
          onClick={() => { setDateFrom(''); setDateTo(''); load(0) }}
          className="px-4 py-1.5 bg-zinc-700 hover:bg-zinc-600 text-white text-sm rounded"
        >
          Limpiar
        </button>
      </form>

      {/* Tabla */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-zinc-400 text-sm">Cargando…</div>
        ) : rows.length === 0 ? (
          <div className="p-8 text-center text-zinc-500 text-sm">Sin registros para este período</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800 text-left text-xs text-zinc-400 uppercase tracking-wider">
                <th className="px-4 py-3">Fecha/Hora</th>
                <th className="px-4 py-3">Origen</th>
                <th className="px-4 py-3">Destino</th>
                <th className="px-4 py-3">Duración</th>
                <th className="px-4 py-3">Costo</th>
                <th className="px-4 py-3">Estado</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {rows.map(r => (
                <tr key={r.call_id} className="hover:bg-zinc-800/50">
                  <td className="px-4 py-3 text-zinc-300 font-mono text-xs">
                    {new Date(r.start_ts).toLocaleString('es-PE')}
                  </td>
                  <td className="px-4 py-3 text-zinc-300 font-mono">{r.src_number}</td>
                  <td className="px-4 py-3 text-white font-mono font-medium">{r.dst_number}</td>
                  <td className="px-4 py-3 text-zinc-300">{fmtSec(r.billsec)}</td>
                  <td className="px-4 py-3 text-blue-400 font-mono">{fmtMoney(r.sessionbill)}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS[r.disposition] ?? STATUS.FAILED}`}>
                      {r.disposition}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Paginación */}
      {total > LIMIT && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-zinc-400">
            Página {currentPage} de {totalPages}
            {capped && ' (máx. 200 registros por período)'}
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => load(offset - LIMIT)}
              disabled={offset === 0}
              className="px-3 py-1 bg-zinc-800 hover:bg-zinc-700 text-white rounded disabled:opacity-30 disabled:cursor-not-allowed"
            >
              ← Anterior
            </button>
            <button
              onClick={() => load(offset + LIMIT)}
              disabled={offset + LIMIT >= total}
              className="px-3 py-1 bg-zinc-800 hover:bg-zinc-700 text-white rounded disabled:opacity-30 disabled:cursor-not-allowed"
            >
              Siguiente →
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
